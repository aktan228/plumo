"""Strict marathon: catalog talks, phone identity, concurrent load."""

from app.domain.models import InboundMessage
from app.infrastructure.database.repositories import BusinessRepository, CustomerRepository
from app.marathon import run_dialogues, run_identity, run_load, run_persistence_sql
from app.seed import seed


async def test_marathon_dialogues(agent):
    failures = await run_dialogues(agent)
    assert failures == []


async def test_marathon_identity_and_sql(agent, session):
    failures = await run_identity(agent, session)
    probe = await agent.process_message(
        InboundMessage(channel="whatsapp", external_user_id="+996700200001", text="ок")
    )
    failures.extend(await run_persistence_sql(session, probe.customer_id, "+996700200001"))
    assert failures == []


async def test_seed_phone_is_stable(agent, session):
    customers = CustomerRepository(session)
    business = await BusinessRepository(session).get_by_name("Demo Realty")
    aigul = await customers.get_by_phone(business.id, "+996555111222")
    assert aigul is not None
    first = await agent.process_message(
        InboundMessage(channel="whatsapp", external_user_id="+996555111222", text="Здравствуйте")
    )
    second = await agent.process_message(
        InboundMessage(channel="whatsapp", external_user_id="+996555111222", text="ваш телефон какой?")
    )
    assert first.customer_id == aigul.id == second.customer_id


async def test_marathon_load(session, runtime):
    await seed(session)
    await session.commit()
    failures = await run_load(runtime, count=24)
    assert failures == []
