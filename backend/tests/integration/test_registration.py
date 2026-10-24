"""Real PostgreSQL registration: transaction rollback, duplicate races and tenant isolation."""

import asyncio
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.application.services.auth_service import LoginLimiter, verify_password
from app.application.services import registration_service
from app.container import build_runtime
from app.infrastructure.database.channel_repositories import OperatorRepository
from app.infrastructure.database.repositories import BusinessRepository
from app.domain.errors import InvalidState
from app.main import create_app

BODY = {
    "name": "  Айжан  ",
    "email": "  New.Owner@Example.com  ",
    "password": "registration-qa-password",
    "locale": "ru",
}


@pytest.fixture
async def signup(engine, settings, monkeypatch):
    monkeypatch.setenv("PLUMO_API_KEY", "registration-test-service-key")
    monkeypatch.setattr(registration_service, "REGISTRATION_LIMITER", LoginLimiter(limit=20, window_s=3600))
    runtime = build_runtime(settings, engine=engine)
    app = create_app(settings=settings, runtime=runtime)
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
            headers={"x-api-key": "registration-test-service-key"},
        ) as client:
            yield SimpleNamespace(client=client, factory=runtime.session_factory)


async def counts(signup):
    async with signup.factory() as session:
        return {
            table: await session.scalar(text(f"SELECT count(*) FROM {table}"))
            for table in (
                "businesses",
                "operators",
                "onboarding_drafts",
                "operator_sessions",
                "knowledge_items",
                "customers",
            )
        }


async def test_signup_creates_empty_workspace_draft_and_live_session(signup):
    response = await signup.client.post("/api/v1/auth/register", json=BODY)
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["operator"]["email"] == "new.owner@example.com"
    assert data["operator"]["display_name"] == "Айжан"
    assert data["operator"]["business"]["name"] == "Мой бизнес"
    assert await counts(signup) == dict(
        businesses=1, operators=1, onboarding_drafts=1, operator_sessions=1, knowledge_items=0, customers=0
    )
    async with signup.factory() as session:
        stored = await session.scalar(text("SELECT password_hash FROM operators"))
        assert stored != BODY["password"] and verify_password(BODY["password"], stored)
        draft = (await session.execute(text("SELECT business_id, step, data FROM onboarding_drafts"))).one()
        assert str(draft.business_id) == data["operator"]["business"]["id"] and draft.step == 0 and draft.data == {}
    headers = {"authorization": f"Bearer {data['token']}"}
    me = await signup.client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200 and me.json()["operator"] == data["operator"]
    assert (await signup.client.post("/api/v1/auth/logout", headers=headers)).status_code == 204
    assert (await signup.client.get("/api/v1/auth/me", headers=headers)).status_code == 401
    assert (
        await signup.client.post("/api/v1/auth/login", json={"email": BODY["email"], "password": BODY["password"]})
    ).status_code == 200


async def test_duplicate_and_concurrent_submissions_create_one_account(signup):
    responses = await asyncio.gather(
        *(
            signup.client.post("/api/v1/auth/register", json={**BODY, "email": email})
            for email in ["New.Owner@example.com", "new.owner@example.com", "  NEW.OWNER@EXAMPLE.COM "] * 2
        )
    )
    assert sorted(r.status_code for r in responses) == [201, 409, 409, 409, 409, 409]
    assert await counts(signup) == dict(
        businesses=1, operators=1, onboarding_drafts=1, operator_sessions=1, knowledge_items=0, customers=0
    )


async def test_different_accounts_with_same_workspace_name_stay_isolated(signup):
    first = (await signup.client.post("/api/v1/auth/register", json=BODY)).json()
    second = (await signup.client.post("/api/v1/auth/register", json={**BODY, "email": "second@example.com"})).json()
    assert first["operator"]["business"]["id"] != second["operator"]["business"]["id"]
    for data in (first, second):
        response = await signup.client.get("/api/v1/auth/me", headers={"authorization": f"Bearer {data['token']}"})
        assert response.json()["operator"]["business"] == data["operator"]["business"]
    async with signup.factory() as session:
        with pytest.raises(InvalidState, match="business-id"):
            await BusinessRepository(session).get_by_name("Мой бизнес")


@pytest.mark.parametrize(
    "change",
    [
        {"name": "   "},
        {"name": "a" * 101},
        {"name": "bad\x00name"},
        {"email": "broken"},
        {"email": None},
        {"password": "short"},
        {"password": " " * 12},
        {"password": "x" * 129},
        {"locale": "other"},
        {"business_id": "00000000-0000-0000-0000-000000000000"},
    ],
)
async def test_invalid_signup_does_not_write_data(signup, change):
    response = await signup.client.post("/api/v1/auth/register", json={**BODY, **change})
    assert response.status_code == 422
    assert BODY["password"] not in response.text
    assert all(value == 0 for value in (await counts(signup)).values())


async def test_session_failure_rolls_back_account_workspace_and_draft(signup, monkeypatch):
    async def fail(*args, **kwargs):
        raise RuntimeError("simulated session insert failure")

    monkeypatch.setattr(OperatorRepository, "add_session", fail)
    response = await signup.client.post("/api/v1/auth/register", json=BODY)
    assert response.status_code == 500
    assert all(value == 0 for value in (await counts(signup)).values())


async def test_signup_service_key_and_rate_limit(signup, monkeypatch):
    denied = await signup.client.post("/api/v1/auth/register", json=BODY, headers={"x-api-key": "wrong"})
    assert denied.status_code == 401
    monkeypatch.setattr(registration_service, "REGISTRATION_LIMITER", LoginLimiter(limit=2, window_s=3600))
    for email in ["one@example.com", "two@example.com"]:
        assert (await signup.client.post("/api/v1/auth/register", json={**BODY, "email": email})).status_code == 201
    assert (
        await signup.client.post("/api/v1/auth/register", json={**BODY, "email": "three@example.com"})
    ).status_code == 429
    assert (await counts(signup))["businesses"] == 2


async def test_english_workspace_and_unicode_password(signup):
    body = {**BODY, "locale": "en", "password": "🔑" * 10}
    response = await signup.client.post("/api/v1/auth/register", json=body)
    assert response.status_code == 201 and response.json()["operator"]["business"]["name"] == "My business"
    assert (
        await signup.client.post("/api/v1/auth/login", json={"email": BODY["email"], "password": body["password"]})
    ).status_code == 200
