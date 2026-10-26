"""Resumable setup: real Postgres, independent tenants, optimistic writes and atomic completion."""

import asyncio
import base64
import copy
from types import SimpleNamespace
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, func

from conftest import operator_token
from app.container import build_runtime
from app.infrastructure.database.models import BusinessRow, OnboardingDraftRow, KnowledgeItemRow
from app.infrastructure.database.session import create_session_factory
from app.main import create_app

DATA = {
    "settings": {
        "company": "QA Мастер",
        "description": "Тестовые услуги",
        "audience": "Компании",
        "name": "Алина",
        "purpose": "support",
        "greeting": "Здравствуйте, я ИИ-ассистент.",
        "goal": "Ответить по фактам и передать вопрос менеджеру.",
        "fallback": "Уточним у сотрудника.",
    },
    "sources": [
        {"id": "qa-faq", "kind": "faq", "title": "График", "question": "Когда открыты?", "content": "С 9 до 18."},
        {"id": "qa-file", "kind": "file", "title": "facts.md", "content": "Тестовый материал о компании."},
    ],
    "entry": {"kind": "text", "value": "", "question": ""},
    "channel": 2,
    "pricing": {"choice": "start", "volume": 1000, "billing": "month", "voice": False},
}


def payload(version=0, step=4, **changes):
    result = {"version": version, "step": step, "data": copy.deepcopy(DATA)}
    result.update(changes)
    return result


@pytest.fixture
async def wizard(engine, settings, monkeypatch):
    monkeypatch.setenv("PLUMO_API_KEY", "wizard-test-service-key")
    factory = create_session_factory(engine)
    ids, tokens = [], []
    async with factory() as session:
        for index in range(2):
            ident = uuid4()
            session.add(
                BusinessRow(
                    id=ident,
                    name=f"Before {index}",
                    contacts={"phone": "fictional"},
                    profile={"offering": "Existing offering"},
                )
            )
            await session.flush()
            ids.append(ident)
            tokens.append(await operator_token(session, ident, f"wizard{index}@example.com"))
        await session.commit()
    runtime = build_runtime(settings, engine=engine)
    app = create_app(settings=settings, runtime=runtime)
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
            headers={"x-api-key": "wizard-test-service-key", "authorization": f"Bearer {tokens[0]}"},
        ) as http:
            yield SimpleNamespace(http=http, factory=factory, ids=ids, tokens=tokens)


async def test_legacy_account_get_creates_one_empty_draft(wizard):
    responses = await asyncio.gather(*(wizard.http.get("/api/v1/onboarding") for _ in range(3)))
    for response in responses:
        assert response.status_code == 200
        assert response.json()["data"] is None and response.json()["version"] == 0
        assert response.json()["business_id"] == str(wizard.ids[0])
    async with wizard.factory() as session:
        assert await session.scalar(select(func.count()).select_from(OnboardingDraftRow)) == 1


async def test_all_fields_sources_logo_and_step_survive_readback(wizard):
    body = payload()
    body["data"]["settings"]["logo"] = "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\nfixture").decode()
    body["data"]["settings"]["logoName"] = "logo.png"
    body["data"]["entry"] = {"kind": "faq", "value": "Незаконченный ответ", "question": "Черновой вопрос?"}
    response = await wizard.http.patch("/api/v1/onboarding", json=body)
    assert response.status_code == 200, response.text
    restored = (await wizard.http.get("/api/v1/onboarding")).json()
    assert restored["step"] == 4 and restored["version"] == 1 and restored["completed_at"] is None
    assert restored["data"]["sources"][1]["content"] == DATA["sources"][1]["content"]
    assert restored["data"]["settings"]["logo"] == body["data"]["settings"]["logo"]
    assert restored["data"]["entry"] == body["data"]["entry"]
    async with wizard.factory() as session:
        assert (await session.get(BusinessRow, wizard.ids[0])).name == "Before 0"


async def test_business_identity_comes_from_session_and_extra_ids_rejected(wizard):
    await wizard.http.patch("/api/v1/onboarding", json=payload())
    other = await wizard.http.get("/api/v1/onboarding", headers={"authorization": f"Bearer {wizard.tokens[1]}"})
    assert other.json()["data"] is None and other.json()["business_id"] == str(wizard.ids[1])
    own = await wizard.http.get("/api/v1/onboarding", params={"business_id": str(wizard.ids[1])})
    assert own.json()["business_id"] == str(wizard.ids[0])
    for path, body in [
        ("/api/v1/onboarding", {**payload(1), "business_id": str(wizard.ids[1])}),
        ("/api/v1/onboarding/complete", {"version": 1, "business_id": str(wizard.ids[1])}),
    ]:
        response = await (
            wizard.http.patch(path, json=body) if path.endswith("onboarding") else wizard.http.post(path, json=body)
        )
        assert response.status_code == 422


async def test_concurrent_edits_conflict_and_retry_is_idempotent(wizard):
    first, second = payload(), payload()
    second["data"]["settings"]["company"] = "Another tab"
    responses = await asyncio.gather(
        wizard.http.patch("/api/v1/onboarding", json=first), wizard.http.patch("/api/v1/onboarding", json=second)
    )
    assert sorted(r.status_code for r in responses) == [200, 409]
    saved = next(r.json() for r in responses if r.status_code == 200)
    retry = {"version": 0, "step": saved["step"], "data": saved["data"]}
    response = await wizard.http.patch("/api/v1/onboarding", json=retry)
    assert response.status_code == 200 and response.json()["version"] == 1
    stale = await wizard.http.patch("/api/v1/onboarding", json={**payload(), "step": 1})
    assert stale.status_code == 409 and stale.json()["code"] == "version_conflict"


async def test_completion_is_explicit_atomic_and_preserves_existing_business_data(wizard):
    saved = (await wizard.http.patch("/api/v1/onboarding", json=payload())).json()
    response = await wizard.http.post("/api/v1/onboarding/complete", json={"version": saved["version"]})
    assert response.status_code == 200, response.text
    completed = response.json()
    assert completed["step"] == 5 and completed["completed_at"] and completed["version"] == 2
    repeated = await wizard.http.post("/api/v1/onboarding/complete", json={"version": 1})
    assert repeated.status_code == 200 and repeated.json()["version"] == 2
    async with wizard.factory() as session:
        business = await session.get(BusinessRow, wizard.ids[0])
        assert business.name == "QA Мастер" and business.description == "Тестовые услуги"
        assert business.contacts == {"phone": "fictional", "assistant_name": "Алина"}
        assert business.profile["offering"] == "Existing offering"
        assert business.profile["onboarding"]["sources"][0]["question"] == "Когда открыты?"
        assert "logo" not in business.profile["onboarding"]["settings"]
        assert (await session.get(BusinessRow, wizard.ids[1])).name == "Before 1"
        assert await session.scalar(select(func.count()).select_from(KnowledgeItemRow)) == 2
    changed = payload(2, 5)
    changed["data"]["settings"]["company"] = "Unpublished change"
    response = await wizard.http.patch("/api/v1/onboarding", json=changed)
    assert response.json()["completed_at"] is None
    async with wizard.factory() as session:
        assert (await session.get(BusinessRow, wizard.ids[0])).name == "QA Мастер"


async def test_incomplete_setup_and_stale_completion_are_rejected(wizard):
    assert (await wizard.http.post("/api/v1/onboarding/complete", json={"version": 0})).status_code == 422
    await wizard.http.patch("/api/v1/onboarding", json=payload())
    assert (await wizard.http.post("/api/v1/onboarding/complete", json={"version": 0})).status_code == 409
    body = payload(1)
    body["data"]["entry"] = {"kind": "text", "value": "Pending material", "question": ""}
    await wizard.http.patch("/api/v1/onboarding", json=body)
    assert (await wizard.http.post("/api/v1/onboarding/complete", json={"version": 2})).status_code == 422


@pytest.mark.parametrize(
    "bad",
    [
        "step",
        "version",
        "bool-channel",
        "duplicate-source",
        "too-many-sources",
        "utf8-source",
        "total-sources",
        "url",
        "instagram",
        "remote-logo",
        "svg-logo",
        "oversize-logo",
        "unknown-field",
        "nul",
    ],
)
async def test_invalid_snapshots_write_nothing(wizard, bad):
    body = payload()
    if bad == "step":
        body["step"] = 6
    elif bad == "version":
        body["version"] = -1
    elif bad == "bool-channel":
        body["data"]["channel"] = True
    elif bad == "duplicate-source":
        body["data"]["sources"] *= 2
    elif bad == "too-many-sources":
        body["data"]["sources"] = [{**DATA["sources"][0], "id": str(i)} for i in range(11)]
    elif bad == "utf8-source":
        body["data"]["sources"][0]["content"] = "я" * 50001
    elif bad == "total-sources":
        body["data"]["sources"] = [
            {"id": str(i), "kind": "text", "title": "Text", "content": "a" * 70000} for i in range(3)
        ]
    elif bad == "url":
        body["data"]["sources"] = [{"id": "url", "kind": "website", "title": "URL", "content": "javascript:alert(1)"}]
    elif bad == "instagram":
        body["data"]["sources"] = [
            {"id": "url", "kind": "instagram", "title": "URL", "content": "https://instagram.com.evil.example"}
        ]
    elif bad == "remote-logo":
        body["data"]["settings"]["logo"] = "https://evil.example/track.png"
    elif bad == "svg-logo":
        body["data"]["settings"]["logo"] = "data:image/svg+xml;base64,PHN2Zz4="
    elif bad == "oversize-logo":
        body["data"]["settings"]["logo"] = (
            "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"x" * 1_000_000).decode()
        )
    elif bad == "unknown-field":
        body["data"]["settings"]["business_id"] = str(wizard.ids[1])
    elif bad == "nul":
        body["data"]["settings"]["company"] = "test\0name"
    response = await wizard.http.patch("/api/v1/onboarding", json=body)
    assert response.status_code == 422, response.text[:200]
    assert (await wizard.http.get("/api/v1/onboarding")).json()["version"] == 0


async def test_anonymous_and_wrong_service_key_cannot_access(wizard):
    assert (await wizard.http.get("/api/v1/onboarding", headers={"authorization": ""})).status_code == 401
    assert (
        await wizard.http.patch("/api/v1/onboarding", json=payload(), headers={"x-api-key": "wrong"})
    ).status_code == 401
