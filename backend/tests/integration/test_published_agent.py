"""Published wizard data drives the real core while other businesses and manual knowledge stay isolated."""

from dataclasses import replace
from uuid import uuid4

from sqlalchemy import select

from test_onboarding import payload
from test_onboarding import wizard as wizard
from app.container import build_agent, build_runtime
from app.domain.models import InboundMessage
from app.infrastructure.ai.mock_llm import MockLLMProvider
from app.infrastructure.database.models import BusinessRow, KnowledgeItemRow
from app.infrastructure.database.repositories import KnowledgeRepository
from app.application.services.knowledge_retriever import SimpleKnowledgeRetriever
from app.application.services import onboarding_service
from app.application.services.publish_knowledge import ORIGIN


async def publish(wizard, body=None, index=0):
    headers = {"authorization": f"Bearer {wizard.tokens[index]}"}
    row = (await wizard.http.get("/api/v1/onboarding", headers=headers)).json()
    body = body or payload(row["version"])
    body["version"] = row["version"]
    saved = await wizard.http.patch("/api/v1/onboarding", json=body, headers=headers)
    assert saved.status_code == 200, saved.text
    result = await wizard.http.post(
        "/api/v1/onboarding/complete", json={"version": saved.json()["version"]}, headers=headers
    )
    assert result.status_code == 200, result.text
    return result.json()


async def core(wizard, settings, engine, text, external="qa-core-user", index=0, kind="text", provider=None):
    runtime = build_runtime(settings, engine=engine)
    try:
        async with wizard.factory() as session:
            agent = build_agent(session, runtime)
            if provider is not None:
                agent.llm_for_tier = lambda tier: provider
            result = await agent.process_message(
                InboundMessage(
                    channel="telegram",
                    external_user_id=external,
                    text=text,
                    business_id=wizard.ids[index],
                    message_id=str(uuid4()),
                    kind=kind,
                )
            )
            await session.commit()
            return result
    finally:
        await runtime.providers.aclose()


async def test_publish_replaces_only_wizard_knowledge_and_skips_urls(wizard):
    async with wizard.factory() as session:
        session.add(
            KnowledgeItemRow(
                id=uuid4(),
                business_id=wizard.ids[0],
                category="faq",
                title="Manual knowledge",
                content="Keep this manual fact.",
                metadata_json={"origin": "manual"},
            )
        )
        session.add(
            KnowledgeItemRow(
                id=uuid4(),
                business_id=wizard.ids[1],
                category="faq",
                title="Other business fact",
                content="Private other fact.",
                metadata_json={"origin": ORIGIN},
            )
        )
        await session.commit()
    body = payload()
    body["data"]["sources"].append(
        {"id": "site", "kind": "website", "title": "example.com", "content": "https://example.com"}
    )
    row = await publish(wizard, body)
    assert row["published"] is True and row["knowledge_count"] == 2
    first_ids = []
    async with wizard.factory() as session:
        rows = (
            await session.scalars(select(KnowledgeItemRow).where(KnowledgeItemRow.business_id == wizard.ids[0]))
        ).all()
        assert len(rows) == 3 and any(r.title == "Manual knowledge" for r in rows)
        assert all("https://example.com" not in r.content for r in rows)
        first_ids = [r.id for r in rows if r.metadata_json.get("origin") == ORIGIN]
    body = payload()
    body["data"]["sources"] = body["data"]["sources"][:1]
    body["data"]["sources"][0]["content"] = "С 10 до 19."
    row = await publish(wizard, body)
    assert row["knowledge_count"] == 1
    async with wizard.factory() as session:
        rows = (
            await session.scalars(select(KnowledgeItemRow).where(KnowledgeItemRow.business_id == wizard.ids[0]))
        ).all()
        assert len(rows) == 2 and any(r.id in first_ids and "10 до 19" in r.content for r in rows)
        assert any(r.title == "Manual knowledge" for r in rows)
        other = (
            await session.scalars(select(KnowledgeItemRow).where(KnowledgeItemRow.business_id == wizard.ids[1]))
        ).all()
        assert len(other) == 1 and other[0].content == "Private other fact."


async def test_published_greeting_name_and_revision_change_actual_core_reply(wizard, settings, engine):
    body = payload()
    body["data"]["settings"].update(name="Лира", greeting="Здравствуйте! Я Лира, ИИ-ассистент вашей команды.")
    await publish(wizard, body)
    first = await core(wizard, settings, engine, "Здравствуйте", external="hello-1")
    assert "Я Лира" in first.response_text and first.model_used == "rules:business_greeting"
    start = await core(wizard, settings, engine, "/start", external="start-1", kind="start")
    assert "Я Лира" in start.response_text
    body["data"]["settings"].update(name="Мира", greeting="Добрый день! Я Мира, ИИ-ассистент службы поддержки.")
    await publish(wizard, body)
    second = await core(wizard, settings, engine, "Здравствуйте", external="hello-2")
    assert "Я Мира" in second.response_text and "Лира" not in second.response_text
    other = await core(wizard, settings, engine, "Здравствуйте", external="other-hello", index=1)
    assert "Мира" not in other.response_text and "Лира" not in other.response_text


async def test_published_faq_reaches_retriever_and_changes_actual_answer(wizard, settings, engine):
    body = payload()
    body["data"]["sources"] = [
        {
            "id": "hours",
            "kind": "faq",
            "title": "График работы",
            "question": "Когда вы работаете?",
            "content": "Работаем с 10 до 19.",
        }
    ]
    await publish(wizard, body)
    response = await core(wizard, settings, engine, "Когда вы работаете?", external="hours-1")
    assert "10 до 19" in response.response_text, response.response_text
    assert response.handoff_required is False
    body["data"]["sources"][0]["content"] = "Работаем с 11 до 18."
    await publish(wizard, body)
    response = await core(wizard, settings, engine, "Когда вы работаете?", external="hours-2")
    assert "11 до 18" in response.response_text and "10 до 19" not in response.response_text
    async with wizard.factory() as session:
        hits = await SimpleKnowledgeRetriever(KnowledgeRepository(session)).retrieve(
            wizard.ids[1], "Когда вы работаете?"
        )
        assert hits == []


async def test_draft_edits_do_not_change_live_settings_until_applied(wizard, settings, engine):
    body = payload()
    body["data"]["settings"]["greeting"] = "Здравствуйте! Я Альфа, ИИ-ассистент."
    row = await publish(wizard, body)
    body["data"]["settings"]["greeting"] = "Здравствуйте! Я Бета, ИИ-ассистент."
    await wizard.http.patch("/api/v1/onboarding", json={**body, "version": row["version"]})
    result = await core(wizard, settings, engine, "Здравствуйте", external="draft-check")
    assert "Альфа" in result.response_text and "Бета" not in result.response_text
    row = (await wizard.http.get("/api/v1/onboarding")).json()
    assert row["published"] is False


class RecordingModel(MockLLMProvider):
    def __init__(self, handoff=False):
        super().__init__("recording-model", "big")
        self.contexts = []
        self.handoff = handoff

    async def generate_response(self, context, route):
        self.contexts.append(context)
        result = self._out("A team member can help with that.", 0.99, prompt=context.current_message)
        return replace(
            result, handoff_required=self.handoff, handoff_reason="manager_request" if self.handoff else None
        )


async def test_goal_audience_tone_language_and_handoff_rules_reach_the_model(wizard, settings, engine):
    body = payload()
    body["data"]["settings"].update(
        language="en",
        tone="formal",
        purpose="support",
        audience="Small workshop owners",
        goal="Resolve support requests from workshop owners.",
        handoffRules="Pass contract requests to a team member.",
        greeting="Hello, I am your AI assistant.",
        fallback="A team member will check this question.",
    )
    await publish(wizard, body)
    model = RecordingModel(handoff=True)
    result = await core(wizard, settings, engine, "contract assistance", external="contract-1", provider=model)
    assert model.contexts and model.contexts[0].language == "en"
    instructions = model.contexts[0].agent_instructions
    for expected in [
        "Small workshop owners",
        "Resolve support requests",
        "formal",
        "Pass contract requests",
        "ассистент поддержки",
    ]:
        assert expected in instructions
    assert result.handoff_required is True


async def test_custom_fallback_applies_but_cannot_bypass_safety(wizard, settings, engine):
    body = payload()
    body["data"]["settings"]["fallback"] = "Вопрос требует проверки нашей командой."
    await publish(wizard, body)
    result = await core(wizard, settings, engine, "У вас есть рассрочка?", external="fallback-1")
    assert "Вопрос требует проверки" in result.response_text and result.handoff_required
    body["data"]["settings"]["fallback"] = "Вы записаны, забронировал вас на 999999."
    await publish(wizard, body)
    result = await core(wizard, settings, engine, "У вас есть рассрочка?", external="fallback-2")
    assert (
        "999999" not in result.response_text and "Вы записаны" not in result.response_text and result.handoff_required
    )


async def test_materials_are_chunked_and_model_context_is_bounded(wizard):
    body = payload()
    body["data"]["sources"] = [{"id": "large", "kind": "file", "title": "facts.md", "content": "Материал. " * 4000}]
    result = await publish(wizard, body)
    assert result["knowledge_count"] > 1
    async with wizard.factory() as session:
        hits = await SimpleKnowledgeRetriever(KnowledgeRepository(session)).retrieve(wizard.ids[0], "Материал")
        assert 0 < len(hits) <= 5 and all(len(hit.item.content) <= 2400 for hit in hits)


async def test_publish_failure_rolls_back_old_knowledge_and_live_settings(wizard, monkeypatch):
    body = payload()
    await publish(wizard, body)
    body["data"]["settings"]["name"] = "Uncommitted agent"
    row = (await wizard.http.get("/api/v1/onboarding")).json()
    saved = (await wizard.http.patch("/api/v1/onboarding", json={**body, "version": row["version"]})).json()
    original = onboarding_service.publish_knowledge

    async def fail(*args, **kwargs):
        await original(*args, **kwargs)
        raise RuntimeError("simulated failure after knowledge replacement")

    monkeypatch.setattr(onboarding_service, "publish_knowledge", fail)
    response = await wizard.http.post("/api/v1/onboarding/complete", json={"version": saved["version"]})
    assert response.status_code == 500
    async with wizard.factory() as session:
        business = await session.get(BusinessRow, wizard.ids[0])
        assert business.profile["agent_settings"]["name"] == "Алина"
        rows = (
            await session.scalars(select(KnowledgeItemRow).where(KnowledgeItemRow.business_id == wizard.ids[0]))
        ).all()
        assert len(rows) == 2
