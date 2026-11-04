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
