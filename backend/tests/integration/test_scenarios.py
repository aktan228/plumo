"""DB-11: actual execution, shared atomic publication and tenant-scoped revision evidence."""
from dataclasses import replace

from sqlalchemy import select

from test_onboarding import payload, wizard as wizard
from test_published_agent import core, publish, RecordingModel
from app.infrastructure.database.models import BusinessRow, ScenarioRevisionRow


async def test_opening_question_draft_publication_history_and_tenant(wizard, settings, engine):
    body = payload()
    body["data"]["settings"]["openingQuestion"] = "Как к вам обращаться?"
    first = await publish(wizard, body)
    answer = await core(wizard, settings, engine, "Здравствуйте", external="scenario-first")
    assert "Как к вам обращаться?" in answer.response_text
    again = await core(wizard, settings, engine, "Здравствуйте", external="scenario-first")
    assert "Как к вам обращаться?" not in again.response_text
    body["data"]["settings"]["openingQuestion"] = "Чем вам помочь сегодня?"
    saved = await wizard.http.patch("/api/v1/onboarding", json={**body, "version": first["version"]})
    assert saved.status_code == 200
    old = await core(wizard, settings, engine, "Здравствуйте", external="scenario-draft")
    assert "Как к вам обращаться?" in old.response_text and "Чем вам помочь сегодня?" not in old.response_text
    second = await wizard.http.post("/api/v1/onboarding/complete", json={"version": saved.json()["version"]})
    assert second.status_code == 200
    changed = await core(wizard, settings, engine, "/start", external="scenario-start", kind="start")
    assert "Чем вам помочь сегодня?" in changed.response_text
    history = await wizard.http.get("/api/v1/scenarios")
    assert history.status_code == 200, history.text
    data = history.json()
    assert [r["publication_version"] for r in data["items"]] == [second.json()["version"], first["version"]]
    assert data["items"][1]["settings"]["openingQuestion"] == "Как к вам обращаться?"
    assert all(r["published_at"] for r in data["items"])
    retry = await wizard.http.post("/api/v1/onboarding/complete", json={"version": second.json()["version"] - 1})
    assert retry.status_code == 200
    assert len((await wizard.http.get("/api/v1/scenarios")).json()["items"]) == 2
    other = await wizard.http.get("/api/v1/scenarios", headers={"authorization": f"Bearer {wizard.tokens[1]}"})
    assert other.json()["items"] == [] and other.json()["publication_version"] is None
    page = await wizard.http.get(f'/api/v1/scenarios?before={second.json()["version"]}')
    assert len(page.json()["items"]) == 1


async def test_literal_handoff_rule_executes_and_does_not_disable_human_request(wizard, settings, engine):
    body = payload()
    body["data"]["settings"]["handoffKeywords"] = "хочу возврат\nатайын суроо"
    await publish(wizard, body)
    result = await core(wizard, settings, engine, "ХОЧУ, ВОЗВРАТ!", external="scenario-handoff", provider=RecordingModel())
    assert result.handoff_required and result.handoff_reason == "scenario_rule"
    assert any(a.type == "handoff" for a in result.actions)
    taken = await wizard.http.post(f"/api/v1/conversations/{result.conversation_id}/takeover")
    assert taken.status_code == 200
    paused = await core(wizard, settings, engine, "Когда открыты?", external="scenario-handoff")
    assert paused.response_text == ""
    other = await core(wizard, settings, engine, "ХОЧУ, ВОЗВРАТ!", external="scenario-other", index=1, provider=RecordingModel())
    assert other.handoff_reason != "scenario_rule"
    human = await core(wizard, settings, engine, "Позовите менеджера", external="scenario-human")
    assert human.handoff_required and human.handoff_reason == "user_requested_human"


class QualifyingModel(RecordingModel):
    async def generate_response(self, context, route):
        self.contexts.append(context)
        text = "Какой район вас интересует?" if "Сначала выясни район" in context.agent_instructions else "Как к вам обращаться?"
        return replace(self._out(text, 0.99, prompt=context.current_message), handoff_required=False)


async def test_clarification_instruction_reaches_actual_generation(wizard, settings, engine):
    body = payload()
    body["data"]["settings"]["qualificationPrompt"] = "Сначала выясни район"
    await publish(wizard, body)
    provider = QualifyingModel()
    result = await core(wizard, settings, engine, "Подскажите пожалуйста", external="qualification", provider=provider)
    assert provider.contexts and "Сначала выясни район" in provider.contexts[0].agent_instructions
    assert "Какой район" in result.response_text
    body["data"]["settings"]["qualificationPrompt"] = "Сначала узнай имя"
    await publish(wizard, body)
    changed = await core(wizard, settings, engine, "Подскажите пожалуйста", external="qualification-next", provider=QualifyingModel())
    assert "Как к вам обращаться?" in changed.response_text


async def test_invalid_scenario_is_rejected_without_changing_publication(wizard):
    first = await publish(wizard)
    for field, value in [("openingQuestion", "x" * 301), ("qualificationPrompt", "x" * 1501),
                         ("handoffKeywords", "a"), ("handoffKeywords", "ab\n" * 11)]:
        body = payload(first["version"])
        body["data"]["settings"][field] = value
        result = await wizard.http.patch("/api/v1/onboarding", json=body)
        assert result.status_code == 422, result.text
    async with wizard.factory() as session:
        rows = (await session.scalars(select(ScenarioRevisionRow))).all()
        assert len(rows) == 1 and rows[0].publication_version == first["version"]


async def test_legacy_snapshot_time_is_unknown_and_publication_failure_is_atomic(wizard, monkeypatch):
    from app.application.services import onboarding_service

    async with wizard.factory() as session:
        business = await session.get(BusinessRow, wizard.ids[0])
        business.profile = {"agent_settings": {"goal": "Legacy goal"}, "onboarding_publication": {"draft_version": 1}}
        await session.commit()
    first = await publish(wizard)
    items = (await wizard.http.get("/api/v1/scenarios")).json()["items"]
    assert items[-1]["publication_version"] == 1 and items[-1]["published_at"] is None
    assert items[-1]["settings"]["goal"] == "Legacy goal"
    body = payload(first["version"])
    body["data"]["settings"]["goal"] = "Must not be published"
    saved = await wizard.http.patch("/api/v1/onboarding", json=body)

    async def fail(*args):
        raise RuntimeError("publication failure")

    monkeypatch.setattr(onboarding_service, "publish_knowledge", fail)
    result = await wizard.http.post("/api/v1/onboarding/complete", json={"version": saved.json()["version"]})
    assert result.status_code == 500
    after = (await wizard.http.get("/api/v1/scenarios")).json()
    assert after["items"] == items and after["publication_version"] == first["version"]
