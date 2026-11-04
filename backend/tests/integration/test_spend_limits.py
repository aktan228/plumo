"""J-04: rate and spend limits on channel traffic. Messages are kept; paid calls stop; the reason is visible."""

import asyncio
from datetime import date, timedelta

from sqlalchemy import select

from app.application.services.spend_limits import SpendLimits, business_scope, today
from app.infrastructure.database.models import (
    HandoffRequestRow,
    InboundEventRow,
    MessageRow,
    OutboundMessageRow,
    SpendBudgetRow,
    SpendReservationRow,
)


def _limits(stand, **values) -> None:
    stand.runtime.settings = stand.runtime.settings.model_copy(update=values)


async def _rows(stand, model, *where):
    async with stand.factory() as session:
        return list((await session.scalars(select(model).where(*where))).all())


async def _events(stand, connection, count: int, *, start: int = 1, chat_id: int = 5550001) -> list:
    for number in range(start, start + count):
        assert (await stand.tg_update(connection, number, f"Сколько стоит квартира? {number}", chat_id=chat_id)).status_code == 200
    return await _rows(stand, InboundEventRow, InboundEventRow.connection_id == connection.id)


async def test_spent_budget_stops_paid_calls_but_keeps_the_message(stand):
    # Mock replies cost $0.01; the reserve is $0.01: one turn fits in $0.015, the second does not.
    _limits(stand, limit_business_daily_usd=0.015)
    connection = await stand.telegram()
    await _events(stand, connection, 3)
    await stand.worker.drain()

    customer_messages = await _rows(stand, MessageRow, MessageRow.role == "user")
    assert len(customer_messages) == 3
    replies = await _rows(stand, OutboundMessageRow)
    assert len(replies) == 1
    handoffs = await _rows(stand, HandoffRequestRow, HandoffRequestRow.reason == "business_budget")
    assert len(handoffs) == 1  # one per dialog, not one per message
    usage = (await stand.client.get("/api/v1/limits")).json()
    assert usage["calls"] == 1 and 0 < usage["spent_usd"] <= 0.015


async def test_a_sender_writing_too_often_is_paused(stand):
    _limits(stand, limit_sender_messages=2)
    connection = await stand.telegram()
    await _events(stand, connection, 4)
    await stand.worker.drain()

    assert len(await _rows(stand, OutboundMessageRow)) == 2
    assert len(await _rows(stand, HandoffRequestRow, HandoffRequestRow.reason == "sender_rate_limit")) == 1
    # Another customer of the same bot is answered.
    await _events(stand, connection, 1, start=10, chat_id=5550002)
    await stand.worker.drain()
    assert len(await _rows(stand, OutboundMessageRow)) == 3


async def test_concurrent_reservations_do_not_pass_the_limit(stand):
    _limits(stand, limit_business_daily_calls=3)
    connection = await stand.telegram(agent_enabled=False)
    events = await _events(stand, connection, 8)

    async def reserve(event):
        async with stand.factory() as session:
            allowance = await SpendLimits(session, stand.runtime.settings).reserve(event.id, stand.business.id)
            await (session.commit() if allowance.ok else session.rollback())
            return allowance.ok

    results = await asyncio.gather(*(reserve(event) for event in events))
    assert sum(results) == 3
    budget = (await _rows(stand, SpendBudgetRow, SpendBudgetRow.scope == business_scope(stand.business.id)))[0]
    assert budget.calls == 3


async def test_the_same_event_is_charged_once_and_a_crash_keeps_the_hold(stand):
    connection = await stand.telegram(agent_enabled=False)
    event = (await _events(stand, connection, 1))[0]
    for _ in range(3):  # redelivered job, restarted worker: a fresh service object each time
        async with stand.factory() as session:
            assert (await SpendLimits(session, stand.runtime.settings).reserve(event.id, stand.business.id)).ok
            await session.commit()
    budget = (await _rows(stand, SpendBudgetRow, SpendBudgetRow.scope == business_scope(stand.business.id)))[0]
    assert budget.calls == 1
    # Never settled (the worker died mid-turn): the hold still counts; nothing gives it back.
    hold = (await _rows(stand, SpendReservationRow))[0]
    assert hold.status == "reserved" and float(budget.reserved) == float(hold.amount)


async def test_yesterdays_spend_does_not_block_today(stand):
    _limits(stand, limit_business_daily_usd=0.02)
    yesterday = (date.fromisoformat(today()) - timedelta(days=1)).isoformat()
    async with stand.factory() as session:
        session.add(SpendBudgetRow(scope=business_scope(stand.business.id), day=yesterday, calls=999, reserved=0, spent=50))
        await session.commit()
    connection = await stand.telegram()
    await _events(stand, connection, 1)
    await stand.worker.drain()
    assert len(await _rows(stand, OutboundMessageRow)) == 1


async def test_one_business_spending_everything_does_not_stop_another(stand):
    _limits(stand, limit_business_daily_calls=1)
    own = await stand.telegram()
    other = await stand.telegram(business_id=stand.tokens["other_business"])
    await _events(stand, own, 3)
    await _events(stand, other, 1, start=100, chat_id=7770001)
    await stand.worker.drain()

    replies = await _rows(stand, OutboundMessageRow)
    by_business = {}
    for reply in replies:
        by_business[reply.business_id] = by_business.get(reply.business_id, 0) + 1
    assert by_business == {stand.business.id: 1, stand.tokens["other_business"]: 1}
    other_usage = (await stand.client.get("/api/v1/limits", headers={"Authorization": f"Bearer {stand.tokens['other']}"})).json()
    assert other_usage["calls"] == 1


async def test_service_budget_stops_every_business(stand):
    _limits(stand, limit_service_daily_usd=0.015)
    own = await stand.telegram()
    other = await stand.telegram(business_id=stand.tokens["other_business"])
    await _events(stand, own, 1)
    await stand.worker.drain()
    await _events(stand, other, 1, start=100, chat_id=7770001)
    await stand.worker.drain()
    assert len(await _rows(stand, OutboundMessageRow)) == 1
    assert len(await _rows(stand, HandoffRequestRow, HandoffRequestRow.reason == "service_budget")) == 1
    # The other business's own counter got nothing: the failed reservation rolled back whole.
    other_budget = await _rows(stand, SpendBudgetRow, SpendBudgetRow.scope == business_scope(stand.tokens["other_business"]))
    assert all(row.calls == 0 for row in other_budget)


async def test_full_queue_keeps_the_message_without_growing(stand):
    _limits(stand, limit_queue_per_business=1)
    connection = await stand.telegram()
    events = await _events(stand, connection, 3)
    states = sorted((event.status, event.error_code or "") for event in events)
    assert states == [("failed", "queue_full"), ("failed", "queue_full"), ("queued", "")]


async def test_concurrent_webhooks_do_not_pass_the_queue_limit(stand):
    """Each webhook counted the waiting jobs and enqueued in separate statements: all saw room."""

    from app.infrastructure.database.models import JobRow

    _limits(stand, limit_queue_per_business=2)
    connection = await stand.telegram()
    sent = await asyncio.gather(
        *(stand.tg_update(connection, number, f"Сколько стоит квартира? {number}", chat_id=5550000 + number) for number in range(1, 9))
    )
    assert all(response.status_code == 200 for response in sent)
    events = await _rows(stand, InboundEventRow, InboundEventRow.connection_id == connection.id)
    assert len(events) == 8  # every message is kept
    assert len(await _rows(stand, JobRow, JobRow.business_id == stand.business.id)) == 2
    assert sum(event.error_code == "queue_full" for event in events) == 6


class _Clock:
    """The limits' clock, frozen mid-test: a test run must not cross a real window boundary."""

    def __init__(self, monkeypatch) -> None:
        from app.application.services import spend_limits
        from app.domain.models import utcnow

        self.now = utcnow()
        monkeypatch.setattr(spend_limits, "utcnow", lambda: self.now)

    def next_window(self, stand) -> None:
        self.now += timedelta(seconds=stand.runtime.settings.limit_rate_window_s)


async def _jobs_due_now(stand) -> None:
    """The deferred jobs wait on the database clock; the test moved only the limits' clock."""

    from sqlalchemy import text

    async with stand.factory() as session:
        await session.execute(text("UPDATE jobs SET run_at = now() WHERE status = 'queued'"))
        await session.commit()


async def _senders(stand, connection, count: int, *, first_chat: int, start: int) -> None:
    # One message per customer: the per-sender limit stays out of the way.
    for offset in range(count):
        response = await stand.tg_update(connection, start + offset, "Сколько стоит квартира?", chat_id=first_chat + offset)
        assert response.status_code == 200


async def test_a_full_service_window_delays_turns_to_the_next_window(stand, monkeypatch):
    from app.infrastructure.database.models import JobRow

    clock = _Clock(monkeypatch)
    _limits(stand, limit_service_window_turns=2)
    connection = await stand.telegram()
    await _senders(stand, connection, 4, first_chat=5560001, start=1)
    await stand.worker.drain()

    assert len(await _rows(stand, OutboundMessageRow)) == 2
    waiting = await _rows(stand, JobRow, JobRow.status == "queued", JobRow.kind == "process_inbound")
    assert len(waiting) == 2
    # Waiting is not failing: no attempt used, the reason is on the job for the operator.
    assert all(job.attempts == 0 and job.last_error == "service_rate_limit" for job in waiting)
    events = await _rows(stand, InboundEventRow, InboundEventRow.connection_id == connection.id)
    assert sorted(event.status for event in events) == ["processed", "processed", "queued", "queued"]
    assert await _rows(stand, HandoffRequestRow) == []  # a short wait does not call a manager
    assert (await _rows(stand, SpendBudgetRow, SpendBudgetRow.scope == "service"))[0].calls == 2

    await stand.worker.drain()  # still the same window and not due: nothing moves
    assert len(await _rows(stand, OutboundMessageRow)) == 2

    clock.next_window(stand)
    await _jobs_due_now(stand)
    await stand.worker.drain()
    assert len(await _rows(stand, OutboundMessageRow)) == 4
    assert await _rows(stand, HandoffRequestRow) == []


async def test_one_busy_business_takes_only_its_share_of_the_service_window(stand, monkeypatch):
    _Clock(monkeypatch)
    _limits(stand, limit_business_window_turns=2, limit_service_window_turns=3)
    own = await stand.telegram()
    other = await stand.telegram(business_id=stand.tokens["other_business"])
    await _senders(stand, own, 5, first_chat=5570001, start=1)
    await stand.worker.drain()
    await _senders(stand, other, 1, first_chat=7780001, start=100)
    await stand.worker.drain()

    replies = await _rows(stand, OutboundMessageRow)
    by_business: dict = {}
    for reply in replies:
        by_business[reply.business_id] = by_business.get(reply.business_id, 0) + 1
    assert by_business == {stand.business.id: 2, stand.tokens["other_business"]: 1}
    # Each business sees only its own window.
    own_usage = (await stand.client.get("/api/v1/limits")).json()
    other_usage = (await stand.client.get("/api/v1/limits", headers={"Authorization": f"Bearer {stand.tokens['other']}"})).json()
    assert (own_usage["window_turns"], own_usage["window_turns_limit"]) == (2, 2)
    assert other_usage["window_turns"] == 1


async def test_window_places_are_shared_by_processes_and_survive_a_restart(stand, monkeypatch):
    """Every reservation below is a fresh session, as in another worker or after a restart."""

    from app.infrastructure.database.models import RateWindowRow

    _Clock(monkeypatch)
    _limits(stand, limit_business_window_turns=3)
    connection = await stand.telegram(agent_enabled=False)
    events = await _events(stand, connection, 8)

    async def reserve(event):
        async with stand.factory() as session:
            allowance = await SpendLimits(session, stand.runtime.settings).reserve(event.id, stand.business.id)
            await (session.commit() if allowance.ok else session.rollback())
            return allowance

    results = await asyncio.gather(*(reserve(event) for event in events))
    granted = [event for event, result in zip(events, results, strict=True) if result.ok]
    refused = [event for event, result in zip(events, results, strict=True) if not result.ok]
    assert len(granted) == 3
    assert {result.reason for result in results if not result.ok} == {"business_rate_limit"}
    assert all(result.retry_at is not None for result in results if not result.ok)

    # Same event again (redelivered job): its reservation is reused, no second place taken.
    assert (await reserve(granted[0])).ok
    # A refused event tried again after a "restart": the count is in the database, still full.
    assert not (await reserve(refused[0])).ok
    window = (await _rows(stand, RateWindowRow, RateWindowRow.scope == business_scope(stand.business.id)))[0]
    assert window.count == 3
    # Refused turns rolled back whole: the service window and the day budget counted only the three.
    assert (await _rows(stand, RateWindowRow, RateWindowRow.scope == "service"))[0].count == 3
    assert (await _rows(stand, SpendBudgetRow, SpendBudgetRow.scope == business_scope(stand.business.id)))[0].calls == 3
