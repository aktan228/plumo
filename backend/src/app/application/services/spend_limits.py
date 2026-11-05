"""Rate and spend limits for customer turns from the channels (J-04).

Before a turn may call a paid model, the worker reserves `TURN_RESERVE_USD` and one call
on the business's and the service's budget for today (UTC) in a short transaction of its
own, committed before the model is called. The check-and-add is one UPDATE with the limit
in its WHERE, so two workers cannot both take the last place. After the turn the
reservation is settled with the logged cost. A turn that crashed keeps its reservation:
the call may have been billed, so the money is not given back automatically.

Before the daily budgets the turn takes a place in two short fixed windows (PJ-01): the
business's and the whole service's paid turns per `LIMIT_RATE_WINDOW_S`. A full window is
not a refusal: the job waits for the next window. The counters live in `rate_windows`, so
every API and worker process shares them and a restart does not reset them.

A reservation is unique per inbound event: a redelivered event or a retried job reuses it.
The test chat has its own allowance (`test_chat_*`); this one applies only to channel traffic.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert

from app.domain.enums import JobStatus
from app.domain.models import utcnow
from app.infrastructure.database.models import (
    InboundEventRow,
    JobRow,
    RateWindowRow,
    SpendBudgetRow,
    SpendReservationRow,
)

logger = logging.getLogger("plumo.limits")

SERVICE = "service"
# Over these the turn waits for the next window; over the daily ones it is not answered.
RATE_REASONS = frozenset({"business_rate_limit", "service_rate_limit"})


def business_scope(business_id) -> str:
    return f"business:{business_id}"


def today() -> str:
    return utcnow().date().isoformat()


def window_start(now: datetime, seconds: int) -> datetime:
    """Start of the fixed window holding `now`. Windows are aligned to the Unix epoch."""

    epoch = int(now.timestamp())
    return datetime.fromtimestamp(epoch - epoch % seconds, tz=UTC)


@dataclass(frozen=True)
class Allowance:
    ok: bool
    # sender_rate_limit | business_rate_limit | service_rate_limit | business_budget | service_budget
    reason: str | None = None
    retry_at: datetime | None = None  # set for a full window: when the next one starts


class SpendLimits:
    def __init__(self, session, settings) -> None:
        self.session, self.settings = session, settings

    async def sender_over_rate(self, event) -> bool:
        """More messages from this sender on this connection in the window than allowed."""

        since = utcnow() - timedelta(seconds=self.settings.limit_sender_window_s)
        count = await self.session.scalar(
            select(func.count())
            .select_from(InboundEventRow)
            .where(
                InboundEventRow.connection_id == event.connection_id,
                InboundEventRow.sender_id == event.sender_id,
                InboundEventRow.received_at >= since,
                InboundEventRow.received_at <= event.received_at,
            )
        )
        return (count or 0) > self.settings.limit_sender_messages

    async def queue_full(self, business_id) -> bool:
        """Whether the business already has as many waiting jobs as allowed.

        Takes the business's queue lock until the caller's transaction ends, so the count and
        the enqueue after it are one step: concurrent webhooks of one business wait for each
        other instead of all seeing the same free place. Nothing slow runs under the lock.
        """

        await self.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": f"queue:{business_id}"}
        )
        waiting = await self.session.scalar(
            select(func.count())
            .select_from(JobRow)
            .where(JobRow.business_id == business_id, JobRow.status.in_((JobStatus.queued, JobStatus.running)))
        )
        return (waiting or 0) >= self.settings.limit_queue_per_business

    async def reserve(self, event_id, business_id) -> Allowance:
        """Hold one turn's cost for this event. Call in its own transaction and commit it."""

        existing = await self.session.get(SpendReservationRow, event_id)
        if existing is not None:
            return Allowance(True)
        # Windows first, then budgets, business before service: one lock order in every process.
        full = await self._take_window_places(business_id)
        if full is not None:
            return full
        day = today()
        amount = Decimal(str(self.settings.turn_reserve_usd))
        scopes = (
            (business_scope(business_id), Decimal(str(self.settings.limit_business_daily_usd)), self.settings.limit_business_daily_calls, "business_budget"),
            (SERVICE, Decimal(str(self.settings.limit_service_daily_usd)), None, "service_budget"),
        )
        # Always business first, then service: the same lock order in every worker, no deadlock.
        for scope, usd, calls, reason in scopes:
            await self.session.execute(
                insert(SpendBudgetRow).values(scope=scope, day=day).on_conflict_do_nothing()
            )
            condition = [SpendBudgetRow.scope == scope, SpendBudgetRow.day == day, SpendBudgetRow.spent + SpendBudgetRow.reserved + amount <= usd]
            if calls is not None:
                condition.append(SpendBudgetRow.calls < calls)
            taken = await self.session.execute(
                update(SpendBudgetRow)
                .where(*condition)
                .values(calls=SpendBudgetRow.calls + 1, reserved=SpendBudgetRow.reserved + amount, updated_at=utcnow())
            )
            if (taken.rowcount or 0) != 1:
                # The caller rolls back: a business place taken before a full service budget is returned.
                return Allowance(False, reason)
        self.session.add(
            SpendReservationRow(
                inbound_event_id=event_id, business_id=business_id, day=day, amount=amount,
                status="reserved", cost_version=self.settings.cost_version,
            )
        )
        await self.session.flush()
        return Allowance(True)

    async def _take_window_places(self, business_id) -> Allowance | None:
        """One place in the business's and the service's current window, or why not.

        Each is one INSERT .. ON CONFLICT DO UPDATE with the limit in its WHERE: Postgres
        re-checks the limit on the locked row, so concurrent turns cannot pass it together.
        """

        seconds = self.settings.limit_rate_window_s
        start = window_start(utcnow(), seconds)
        windows = (
            (business_scope(business_id), self.settings.limit_business_window_turns, "business_rate_limit"),
            (SERVICE, self.settings.limit_service_window_turns, "service_rate_limit"),
        )
        for scope, limit, reason in windows:
            statement = (
                insert(RateWindowRow)
                .values(scope=scope, window_start=start, count=1)
                .on_conflict_do_update(
                    index_elements=[RateWindowRow.scope, RateWindowRow.window_start],
                    set_={"count": RateWindowRow.count + 1},
                    where=RateWindowRow.count < limit,
                )
                .returning(RateWindowRow.count)
            )
            if await self.session.scalar(statement) is None:
                # The caller rolls back: a business place taken before a full service window is returned.
                return Allowance(False, reason, retry_at=start + timedelta(seconds=seconds))
        return None

    async def settle(self, event_id, actual: float) -> None:
        """Replace the hold with what the turn cost. Idempotent: a settled reservation stays as it is."""

        row = await self.session.scalar(
            select(SpendReservationRow).where(SpendReservationRow.inbound_event_id == event_id).with_for_update()
        )
        if row is None or row.status != "reserved":
            return
        cost = Decimal(str(max(actual, 0.0))).quantize(Decimal("0.000001"))
        if cost > row.amount:
            # The budget check counted the reserve, not this: TURN_RESERVE_USD is too small for the model.
            logger.warning(
                "turn_cost_over_reserve",
                extra={"business_id": str(row.business_id), "reserve_usd": float(row.amount), "cost_usd": float(cost)},
            )
        for scope in (business_scope(row.business_id), SERVICE):
            await self.session.execute(
                update(SpendBudgetRow)
                .where(SpendBudgetRow.scope == scope, SpendBudgetRow.day == row.day)
                .values(
                    reserved=func.greatest(SpendBudgetRow.reserved - row.amount, 0),
                    spent=SpendBudgetRow.spent + cost,
                    updated_at=utcnow(),
                )
            )
        row.actual, row.status, row.settled_at = cost, "settled", utcnow()
        await self.session.flush()

    async def usage(self, business_id) -> dict:
        row = await self.session.get(SpendBudgetRow, (business_scope(business_id), today()))
        start = window_start(utcnow(), self.settings.limit_rate_window_s)
        window = await self.session.get(RateWindowRow, (business_scope(business_id), start))
        return {
            "window_s": self.settings.limit_rate_window_s,
            "window_turns": window.count if window else 0,
            "window_turns_limit": self.settings.limit_business_window_turns,
            "day": today(),
            "calls": row.calls if row else 0,
            "calls_limit": self.settings.limit_business_daily_calls,
            "spent_usd": float((row.spent + row.reserved) if row else 0),
            "limit_usd": self.settings.limit_business_daily_usd,
        }
