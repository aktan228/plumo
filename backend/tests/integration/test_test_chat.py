"""Real core through authenticated sandbox API; Postgres and two independent tenants."""

import asyncio
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import func, select

from test_onboarding import payload, wizard as wizard
from test_published_agent import publish
from app.domain.errors import ProviderUnavailable
from app.domain.models import utcnow
from app.infrastructure.ai.mock_llm import MockLLMProvider
from app.infrastructure.database.models import (
    ConversationRow,
    CustomerRow,
    HandoffRequestRow,
    InteractionLogRow,
    MeetingRow,
    MessageRow,
    TestBudgetRow as SandboxBudgetRow,
    TestSessionRow as SandboxSessionRow,
    TestTurnRow as SandboxTurnRow,
    UsageLogRow,
)


async def start(wizard):
    body = payload()
    body["data"]["sources"] = [
        {
            "id": "hours",
            "kind": "faq",
            "title": "График работы",
            "question": "Когда вы работаете?",
            "content": "Работаем с 9 до 18.",
        }
    ]
    await publish(wizard, body)
    response = await wizard.http.post("/api/v1/testing/sessions", json={"id": str(uuid4())})
    assert response.status_code == 200, response.text
    return response.json()["id"]


async def send(wizard, ident, text="Когда вы работаете?", request_id=None):
    return await wizard.http.post(
        f"/api/v1/testing/sessions/{ident}/messages", json={"request_id": request_id or str(uuid4()), "text": text}
    )


async def test_real_core_history_replay_and_no_live_side_effects(wizard):
    ident = await start(wizard)
    request = str(uuid4())
    response = await send(wizard, ident, request_id=request)
    assert response.status_code == 200, response.text
    turn = response.json()
    assert turn["status"] == "succeeded" and "9 до 18" in turn["result"]["text"]
    assert turn["result"]["sources"] and turn["result"]["mock"] is True
    replay = await send(wizard, ident, request_id=request)
    assert replay.json() == turn
    mismatch = await send(wizard, ident, "Другой текст", request)
    assert mismatch.status_code == 409
    history = await wizard.http.get(f"/api/v1/testing/sessions/{ident}")
    assert len(history.json()["turns"]) == 1
    handoff = await send(wizard, ident, "Позовите менеджера")
    assert handoff.json()["result"]["handoff"] is True
    assert (await send(wizard, ident)).json()["code"] == "test_paused"
    async with wizard.factory() as db:
        for table in [
            CustomerRow,
            ConversationRow,
            MessageRow,
            MeetingRow,
            HandoffRequestRow,
            InteractionLogRow,
            UsageLogRow,
        ]:
            assert await db.scalar(select(func.count()).select_from(table)) == 0, table.__tablename__
        budget = await db.get(SandboxBudgetRow, wizard.ids[0])
        assert budget.attempts == 2 and budget.charged == Decimal(str(turn["result"]["estimated_cost"]))


async def test_tenant_auth_and_payload_boundaries(wizard):
    ident = await start(wizard)
    other = {"authorization": f"Bearer {wizard.tokens[1]}"}
    assert (await wizard.http.get("/api/v1/testing/sessions", headers=other)).json()["sessions"] == []
    assert (await wizard.http.get(f"/api/v1/testing/sessions/{ident}", headers=other)).status_code == 404
    assert (
        await wizard.http.post(
            f"/api/v1/testing/sessions/{ident}/messages",
            headers=other,
            json={"request_id": str(uuid4()), "text": "test"},
        )
    ).status_code == 404
    assert (await wizard.http.get("/api/v1/testing/sessions", headers={"authorization": ""})).status_code == 401
    for text in [" ", "x" * 1001, "a\0b"]:
        assert (await send(wizard, ident, text)).status_code == 422
    assert (
        await wizard.http.post(
            f"/api/v1/testing/sessions/{ident}/messages",
            json={"request_id": str(uuid4()), "text": "test", "business_id": str(wizard.ids[1])},
        )
    ).status_code == 422


async def test_daily_reserve_shared_across_sessions_and_failure_is_idempotent(wizard, monkeypatch):
    ident = await start(wizard)
    calls = 0

    async def broken(self, context, route):
        nonlocal calls
        calls += 1
        raise ProviderUnavailable("fake-secret-must-not-leak")

    monkeypatch.setattr(MockLLMProvider, "generate_response", broken)
    request = str(uuid4())
    first = await send(wizard, ident, request_id=request)
    assert first.json()["status"] == "failed" and first.json()["error"] == "test_provider_unavailable"
    assert "fake-secret" not in first.text
    assert (await send(wizard, ident, request_id=request)).json() == first.json()
    assert calls == 1
    async with wizard.factory() as db:
        row = await db.get(SandboxBudgetRow, wizard.ids[0])
        row.charged = Decimal("1.0")
        await db.commit()
    new = (await wizard.http.post("/api/v1/testing/sessions", json={"id": str(uuid4())})).json()["id"]
    limited = await send(wizard, new)
    assert limited.status_code == 429 and limited.json()["code"] == "test_limit"
    assert calls == 1


async def test_concurrent_replay_runs_model_once_and_preserves_context(wizard, monkeypatch):
    ident = await start(wizard)
    original = MockLLMProvider.generate_response
    calls, history = [], []
    started, release = asyncio.Event(), asyncio.Event()

    async def slow(self, context, route):
        calls.append(context.current_message)
        history.append([message.text for message in context.recent_messages])
        started.set()
        await release.wait()
        return await original(self, context, route)

    monkeypatch.setattr(MockLLMProvider, "generate_response", slow)
    request = str(uuid4())
    first = asyncio.create_task(send(wizard, ident, request_id=request))
    await asyncio.wait_for(started.wait(), timeout=10)
    duplicate = await send(wizard, ident, request_id=request)
    assert duplicate.json()["status"] == "pending"
    assert (await send(wizard, ident, "Ещё вопрос")).json()["code"] == "test_busy"
    release.set()
    assert (await first).json()["status"] == "succeeded"
    assert len(calls) == 1
    assert (await send(wizard, ident, "Здравствуйте")).status_code == 200
    assert "Когда вы работаете?" in history[-1]


async def test_stale_pending_recovery_and_published_version(wizard):
    ident = await start(wizard)
    request = uuid4()
    async with wizard.factory() as db:
        row = await db.get(SandboxSessionRow, ident)
        row.pending_id = request
        db.add(
            SandboxTurnRow(
                session_id=row.id,
                request_id=request,
                text="lost",
                status="pending",
                result={},
                day="2026-01-01",
                created_at=utcnow() - timedelta(seconds=100),
            )
        )
        await db.commit()
    recovered = await wizard.http.get(f"/api/v1/testing/sessions/{ident}")
    assert recovered.json()["turns"][0]["error"] == "test_interrupted"
    assert (await send(wizard, ident)).json()["status"] == "succeeded"
    await publish(wizard, payload())
    assert (await send(wizard, ident)).json()["code"] == "test_settings_changed"


async def test_model_receives_only_own_published_context_and_reloaded_history(wizard, monkeypatch):
    ident = await start(wizard)
    other_body = payload()
    other_body["data"]["sources"][0]["content"] = "Private tenant B fact."
    await publish(wizard, other_body, index=1)
    captured = []
    original = MockLLMProvider.generate_response

    async def capture(self, context, route):
        captured.append(context)
        return await original(self, context, route)

    monkeypatch.setattr(MockLLMProvider, "generate_response", capture)
    assert (await send(wizard, ident)).json()["status"] == "succeeded"
    assert (await send(wizard, ident, "Расскажите о работе компании")).json()["status"] == "succeeded"
    assert len(captured) >= 2
    for context in captured:
        assert context.business.id == wizard.ids[0]
        assert all(hit.item.business_id == wizard.ids[0] for hit in context.knowledge)
        assert "Private tenant B fact" not in str(context)
    assert any(message.text == "Когда вы работаете?" for message in captured[-1].recent_messages)


async def test_message_caps_reset_daily_but_session_cap_does_not(wizard):
    ident = await start(wizard)
    async with wizard.factory() as db:
        row = await db.get(SandboxBudgetRow, wizard.ids[0])
        row.attempts = 50
        await db.commit()
    assert (await send(wizard, ident)).json()["code"] == "test_limit"
    async with wizard.factory() as db:
        row = await db.get(SandboxBudgetRow, wizard.ids[0])
        row.day = "2000-01-01"
        row.charged = Decimal("1.0")
        await db.commit()
    assert (await send(wizard, ident)).json()["status"] == "succeeded"
    async with wizard.factory() as db:
        row = await db.get(SandboxSessionRow, ident)
        row.attempts = 20
        await db.commit()
    assert (await send(wizard, ident)).json()["code"] == "test_limit"
    fresh = (await wizard.http.post("/api/v1/testing/sessions", json={"id": str(uuid4())})).json()["id"]
    assert (await send(wizard, fresh)).json()["status"] == "succeeded"
