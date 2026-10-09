"""Webhook retries that arrive at the same time, each in its own transaction."""

import asyncio

from sqlalchemy import func, select

from app.container import build_agent
from app.domain.errors import CustomerConflict
from app.domain.models import InboundMessage
from app.infrastructure.database.models import CustomerRow, InteractionLogRow, MessageRow
from app.infrastructure.database.repositories import CustomerRepository
from app.infrastructure.database.session import create_session_factory
from app.seed import seed


class _SlowModel:
    """Keeps the first transaction open so the retry really collides with it."""

    def __init__(self, inner) -> None:
        self.inner = inner

    async def generate_response(self, context, route):
        await asyncio.sleep(0.3)
        return await self.inner.generate_response(context, route)

    def __getattr__(self, name):
        return getattr(self.inner, name)


async def test_concurrent_retry_of_a_new_customer_runs_the_agent_once(session, runtime, engine, monkeypatch):
    conflicts = []
    original = CustomerRepository.create_with_channel

    async def spy(self, customer, channel, external_id):
        try:
            return await original(self, customer, channel, external_id)
        except CustomerConflict:
            conflicts.append(channel)
            raise

    monkeypatch.setattr(CustomerRepository, "create_with_channel", spy)
    await seed(session)
    await session.commit()
    factory = create_session_factory(engine)
    slow = {tier: _SlowModel(runtime.providers.llm(tier)) for tier in ("small", "big")}

    async def deliver():
        async with factory() as own:
            agent = build_agent(own, runtime)
            agent.llm_for_tier = slow.__getitem__
            response = await agent.process_message(
                InboundMessage(
                    channel="whatsapp",
                    external_user_id="+996555880001",
                    text="Еще продается квартира за 85000?",
                    message_id="wamid.race",
                )
            )
            await own.commit()
            return response

    first, second = await asyncio.gather(deliver(), deliver())

    assert first.customer_id == second.customer_id
    assert sorted([first.duplicate, second.duplicate]) == [False, True]
    customers = await session.scalar(select(func.count()).select_from(CustomerRow).where(CustomerRow.phone == "+996555880001"))
    stored = await session.scalar(select(func.count()).select_from(MessageRow).where(MessageRow.external_id == "wamid.race"))
    runs = await session.scalar(select(func.count()).select_from(InteractionLogRow))
    assert (customers, stored, runs) == (1, 1, 1)
    assert conflicts == ["whatsapp"], "the retry must actually collide with the first request"
