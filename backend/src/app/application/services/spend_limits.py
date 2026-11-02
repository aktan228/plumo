"""Rate and spend limits for customer turns from the channels (J-04).

Before a turn may call a paid model, the worker reserves `TURN_RESERVE_USD` and one call
on the business's and the service's budget for today (UTC) in a short transaction of its
own, committed before the model is called. The check-and-add is one UPDATE with the limit
in its WHERE, so two workers cannot both take the last place. After the turn the
reservation is settled with the logged cost. A turn that crashed keeps its reservation:
the call may have been billed, so the money is not given back automatically.

A reservation is unique per inbound event: a redelivered event or a retried job reuses it.
The test chat has its own allowance (`test_chat_*`); this one applies only to channel traffic.
"""

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert

from app.domain.enums import JobStatus
from app.domain.models import utcnow
from app.infrastructure.database.models import InboundEventRow, JobRow, SpendBudgetRow, SpendReservationRow

SERVICE = "service"


def business_scope(business_id) -> str:
    return f"business:{business_id}"


def today() -> str:
    return utcnow().date().isoformat()


@dataclass(frozen=True)
class Allowance:
    ok: bool
    reason: str | None = None  # sender_rate_limit | business_budget | service_budget


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

    async def settle(self, event_id, actual: float) -> None:
        """Replace the hold with what the turn cost. Idempotent: a settled reservation stays as it is."""

        row = await self.session.scalar(
            select(SpendReservationRow).where(SpendReservationRow.inbound_event_id == event_id).with_for_update()
        )
        if row is None or row.status != "reserved":
            return
        cost = Decimal(str(max(actual, 0.0))).quantize(Decimal("0.000001"))
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
        return {
            "day": today(),
            "calls": row.calls if row else 0,
            "calls_limit": self.settings.limit_business_daily_calls,
            "spent_usd": float((row.spent + row.reserved) if row else 0),
            "limit_usd": self.settings.limit_business_daily_usd,
        }

