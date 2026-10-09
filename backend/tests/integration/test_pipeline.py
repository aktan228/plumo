"""Pipeline tests against PostgreSQL."""

from app.application.services.knowledge_retriever import SimpleKnowledgeRetriever
from app.container import build_voice
from app.domain.models import InboundMessage
from app.domain.scheduling import BUSINESS_TZ
from app.infrastructure.database.models import InteractionLogRow, UsageLogRow
from app.infrastructure.database.repositories import (
    ConversationRepository,
    CustomerRepository,
    HandoffRepository,
    KnowledgeRepository,
    MeetingRepository,
    MessageRepository,
    SummaryRepository,
)
from app.seed import seed
from sqlalchemy import select
from uuid import uuid4


def _msg(text: str, channel: str = "whatsapp", external: str = "+996555900001", **kwargs) -> InboundMessage:
    return InboundMessage(channel=channel, external_user_id=external, text=text, **kwargs)


async def test_new_customer_created(agent):
    response = await agent.process_message(_msg("Здравствуйте", channel="telegram", external="tg-new-1"))
    again = await agent.process_message(_msg("добрый день", channel="telegram", external="tg-new-1"))
    assert response.customer_id == again.customer_id
    assert response.handoff_required is False


async def test_existing_phone_is_reused(agent):
    first = await agent.process_message(_msg("Здравствуйте", external="+996555900101"))
    second = await agent.process_message(_msg("Еще продается квартира за 85000?", external="+996555900101"))
    assert first.customer_id == second.customer_id


async def test_whatsapp_and_voice_share_phone(agent, session):
    whatsapp = await agent.process_message(_msg("Здравствуйте", external="+996555900202"))
    voice = await agent.process_message(_msg("Здравствуйте", channel="voice", external="+996555900202"))
    assert whatsapp.customer_id == voice.customer_id
    customers = CustomerRepository(session)
    business = (await customers.get(whatsapp.customer_id)).business_id
    assert (await customers.get_by_channel(business, "whatsapp", "+996555900202")).id == whatsapp.customer_id
    assert (await customers.get_by_channel(business, "voice", "+996555900202")).id == whatsapp.customer_id


async def test_typed_phone_does_not_merge_or_leak_history(agent, session):
    """Anyone can type someone else's number. It is kept for a callback, not merged."""

    whatsapp = await agent.process_message(_msg("Ищу квартиру на Чуй для семьи", external="+996555900303"))
    instagram = await agent.process_message(_msg("Здравствуйте", channel="instagram", external="ig_900303"))
    assert whatsapp.customer_id != instagram.customer_id
    typed = await agent.process_message(
        _msg("мой номер +996555900303", channel="instagram", external="ig_900303")
    )
    assert typed.customer_id == instagram.customer_id
    card = await CustomerRepository(session).get(instagram.customer_id)
    assert card.contact_phone == "+996555900303"
    assert card.phone is None
    history = await MessageRepository(session).list_for_customer(instagram.customer_id)
    assert all("Чуй для семьи" not in item.text for item in history)
    conversations = await ConversationRepository(session).list_for_customer(whatsapp.customer_id)
    assert {item.channel for item in conversations} == {"whatsapp"}


async def test_same_phone_in_two_businesses_is_two_customers(agent, session):
    from app.domain.models import Business, utcnow
    from app.infrastructure.database.repositories import BusinessRepository

    await seed(session)
    demo = await BusinessRepository(session).get_by_name("Demo Realty")
    now = utcnow()
    other = await BusinessRepository(session).add(
        Business(uuid4(), "Other Realty", "Другое агентство", "10:00-19:00", {}, "", now, now)
    )
    first = await agent.process_message(_msg("Ищу квартиру на Чуй", external="+996555900404", business_id=demo.id))
    second = await agent.process_message(_msg("Здравствуйте", external="+996555900404", business_id=other.id))
    assert first.customer_id != second.customer_id
    history = await MessageRepository(session).list_for_customer(second.customer_id)
    assert all("Чуй" not in item.text for item in history)


async def test_knowledge_returns_the_matching_listing(session):
    from app.infrastructure.database.repositories import BusinessRepository

    await seed(session)
    found = await BusinessRepository(session).get_by_name("Demo Realty")
    hits = await SimpleKnowledgeRetriever(KnowledgeRepository(session)).retrieve(found.id, "квартира за 85000")
    assert hits
    assert hits[0].item.title == "Квартира на Чуй"
    assert "85000" in hits[0].item.content
    assert "110000" not in hits[0].item.content


async def test_agent_does_not_invent_a_missing_price(agent):
    response = await agent.process_message(_msg("есть квартира за 50000?", external="+996555900404"))
    assert response.handoff_required is True
    assert response.handoff_reason == "no_knowledge"
    assert "50000" not in response.response_text
    assert "50 000" not in response.response_text
    assert "85 000" not in response.response_text
    assert "90000" not in response.response_text


async def test_simple_question_uses_small_model(agent):
    response = await agent.process_message(_msg("Еще продается квартира за 85000?", external="+996555900505"))
    assert response.route == "small"
    assert response.route_reason == "knowledge_base_simple_question"
    assert response.model_used == "mock_small"
    assert response.handoff_required is False
    assert "85 000" in response.response_text
    assert response.usage.estimated_cost == 0.001
    assert response.knowledge_sources[0].title == "Квартира на Чуй"


async def test_complex_question_uses_big_model(agent):
    response = await agent.process_message(_msg("А рассрочка есть?", external="+996555900606"))
    assert response.route == "big"
    assert response.route_reason == "money_or_installment"
    assert response.model_used == "mock_big"
    assert response.handoff_required is True
    assert response.handoff_reason == "no_knowledge"
    assert "рассрочк" in response.response_text.lower() and "уточню" in response.response_text
    assert response.usage.estimated_cost == 0.01


async def test_low_confidence_falls_back_to_big(agent):
    response = await agent.process_message(_msg("ну", channel="telegram", external="tg-unclear"))
    assert response.route == "big"
    assert response.route_reason == "low_confidence_fallback"
    assert response.model_used == "mock_big"


async def test_human_request_creates_handoff(agent, session):
    response = await agent.process_message(_msg("Позовите менеджера", external="+996555900707"))
    assert response.handoff_required is True
    assert response.handoff_reason == "user_requested_human"
    assert response.handoff_id is not None
    stored = await HandoffRepository(session).get(response.handoff_id)
    assert stored is not None
    assert stored.status == "PENDING"
    assert stored.priority == "high"


async def test_meeting_request_creates_action(agent, session):
    response = await agent.process_message(
        _msg("Хочу записаться на встречу завтра в 15:00", external="+996555900808")
    )
    assert any(item.type == "schedule_meeting" for item in response.actions)
    meetings = await MeetingRepository(session).list_for_customer(response.customer_id)
    assert len(meetings) == 1
    assert meetings[0].status == "PROPOSED"
    assert meetings[0].scheduled_at.astimezone(BUSINESS_TZ).hour == 15


async def test_summary_is_updated(agent, session):
    response = await agent.process_message(_msg("Еще продается квартира за 85000?", external="+996555900909"))
    summary = await SummaryRepository(session).get(response.customer_id)
    assert summary is not None
    assert "85000" in summary.summary
    assert summary.language == "ru"
    assert "interest: property" in summary.important_facts


async def test_history_survives_channels(agent, session):
    whatsapp = await agent.process_message(_msg("Здравствуйте", external="+996555901010"))
    await agent.process_message(_msg("Еще продается квартира за 85000?", channel="voice", external="+996555901010"))
    messages = await MessageRepository(session).list_for_customer(whatsapp.customer_id)
    assert len(messages) >= 4
    conversations = await ConversationRepository(session).list_for_customer(whatsapp.customer_id)
    assert {item.channel for item in conversations} >= {"whatsapp", "voice"}


async def test_voice_pipeline_uses_mock_speech(session, runtime):
    await seed(session)
    voice = build_voice(session, runtime)
    transcript, response, audio = await voice.respond(
        audio_id="mock_audio_apt",
        external_user_id="+996555901111",
    )
    assert "85000" in transcript.text
    assert response.route == "small"
    assert audio.audio_id.startswith("mock_audio_")
    assert audio.text == response.response_text


async def test_every_turn_is_logged(agent, session):
    response = await agent.process_message(_msg("Здравствуйте", external="+996555901212"))
    interaction = await session.scalar(
        select(InteractionLogRow).where(InteractionLogRow.customer_id == response.customer_id)
    )
    usage = await session.scalar(select(UsageLogRow).where(UsageLogRow.request_id == interaction.request_id))
    assert interaction is not None
    assert interaction.input_text == "Здравствуйте"
    assert interaction.response_text == response.response_text
    assert interaction.model == response.model_used
    assert usage is not None
    assert usage.model == "mock_small"


async def test_knowledge_import_updates_adds_and_switches_off(session):
    from app.import_knowledge import apply_rows, parse_rows
    from app.infrastructure.database.repositories import BusinessRepository, KnowledgeRepository
    from app.seed import seed

    await seed(session)
    business = await BusinessRepository(session).get_by_name("Demo Realty")
    before = {item.title for item in await KnowledgeRepository(session).list_active(business.id)}
    kept = sorted(before)[0]
    rows = parse_rows(f"category,title,content\nproperty,{kept},Новый текст 1 USD\nfaq,Новая строка,Текст\n")
    report = await apply_rows(session, business.id, rows, deactivate_missing=True)
    assert report.updated == [kept] and report.added == ["Новая строка"]
    assert set(report.deactivated) == before - {kept}
    active = {item.title: item.content for item in await KnowledgeRepository(session).list_active(business.id)}
    assert active == {kept: "Новый текст 1 USD", "Новая строка": "Текст"}
    again = await apply_rows(session, business.id, rows, deactivate_missing=True)
    assert again.unchanged == [kept, "Новая строка"] and not again.added and not again.updated
