"""Public account lifecycle on real PostgreSQL; the mail transport is captured in memory."""

import asyncio
from datetime import timedelta
from types import SimpleNamespace
from urllib.parse import urlsplit, parse_qs

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.application.services.auth_service import LoginLimiter, verify_password
from app.application.services import registration_service, account_email_service
from app.container import build_runtime
from app.domain.errors import InvalidState, ProviderUnavailable
from app.domain.models import utcnow
from app.infrastructure.auth_mail import ResendAuthMailer
from app.infrastructure.database.channel_repositories import OperatorRepository
from app.infrastructure.database.models import AuthEmailTokenRow
from app.infrastructure.database.repositories import BusinessRepository
from app.main import create_app

BODY = {
    "name": "  Айжан  ",
    "email": "  New.Owner@Example.com  ",
    "password": "registration-qa-password",
    "locale": "ru",
}


class Mailbox:
    def __init__(self):
        self.messages = []
        self.fail = False

    def check_config(self):
        pass

    async def send(self, mail):
        if self.fail:
            raise ProviderUnavailable("simulated mail outage")
        self.messages.append(mail)


@pytest.fixture
async def signup(engine, settings, monkeypatch):
    monkeypatch.setenv("PLUMO_API_KEY", "registration-test-service-key")
    for module, key, limit in [
        (registration_service, "REGISTRATION_LIMITER", 20),
        (account_email_service, "EMAIL_LIMITER", 30),
        (account_email_service, "TOKEN_LIMITER", 60),
    ]:
        monkeypatch.setattr(module, key, LoginLimiter(limit=limit, window_s=3600))
    settings = settings.model_copy(
        update={"auth_public_url": "https://app.plumo.example", "auth_email_from": "Plumo <account@plumo.example>"}
    )
    runtime = build_runtime(settings, engine=engine)
    mailbox = Mailbox()
    runtime.auth_mailer = mailbox
    app = create_app(settings=settings, runtime=runtime)
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
            headers={"x-api-key": "registration-test-service-key"},
        ) as client:
            yield SimpleNamespace(client=client, factory=runtime.session_factory, mailbox=mailbox, runtime=runtime)


def link_token(mail):
    return parse_qs(urlsplit(mail.link).fragment)["token"][0]


async def counts(signup):
    async with signup.factory() as session:
        return {
            table: await session.scalar(text(f"SELECT count(*) FROM {table}"))
            for table in (
                "businesses",
                "operators",
                "onboarding_drafts",
                "operator_sessions",
                "auth_email_tokens",
                "knowledge_items",
                "customers",
            )
        }


async def register(signup, **changes):
    response = await signup.client.post("/api/v1/auth/register", json={**BODY, **changes})
    assert response.status_code == 201, response.text
    return response


async def verified(signup, **changes):
    await register(signup, **changes)
    mail = signup.mailbox.messages[-1]
    response = await signup.client.post("/api/v1/auth/verify-email", json={"token": link_token(mail)})
    assert response.status_code == 200, response.text
    return response.json()


async def age_mail(signup):
    async with signup.factory() as session:
        await session.execute(text("UPDATE auth_email_tokens SET created_at = created_at - interval '2 minutes'"))
        await session.commit()


async def test_signup_creates_atomic_empty_workspace_and_requires_verification(signup):
    response = await register(signup)
    assert response.json() == {
        "status": "verification_required",
        "email": "new.owner@example.com",
        "email_delivery": "sent",
    }
    assert "token" not in response.json()
    assert await counts(signup) == dict(
        businesses=1,
        operators=1,
        onboarding_drafts=1,
        operator_sessions=0,
        auth_email_tokens=1,
        knowledge_items=0,
        customers=0,
    )
    async with signup.factory() as session:
        operator = (
            await session.execute(text("SELECT email, display_name, password_hash, email_verified_at FROM operators"))
        ).one()
        assert operator.email == "new.owner@example.com" and operator.display_name == "Айжан"
        assert verify_password(BODY["password"], operator.password_hash) and operator.email_verified_at is None
        assert (await session.execute(text("SELECT step, data FROM onboarding_drafts"))).one() == (0, {})
        digest = await session.scalar(text("SELECT token_hash FROM auth_email_tokens"))
        assert len(digest) == 64 and link_token(signup.mailbox.messages[0]) not in digest
    login = await signup.client.post("/api/v1/auth/login", json={"email": BODY["email"], "password": BODY["password"]})
    assert login.status_code == 403 and login.json()["code"] == "email_not_verified"
    assert (await signup.client.get("/api/v1/auth/me")).status_code == 401


async def test_verification_is_single_use_and_creates_live_session(signup):
    account = await verified(signup)
    token = link_token(signup.mailbox.messages[0])
    assert account["operator"]["business"]["name"] == "Мой бизнес"
    headers = {"authorization": f"Bearer {account['token']}"}
    assert (await signup.client.get("/api/v1/auth/me", headers=headers)).status_code == 200
    assert (await signup.client.post("/api/v1/auth/verify-email", json={"token": token})).status_code == 400
    assert (await counts(signup))["operator_sessions"] == 1
    assert (await signup.client.post("/api/v1/auth/logout", headers=headers)).status_code == 204
    assert (await signup.client.get("/api/v1/auth/me", headers=headers)).status_code == 401
    assert (
        await signup.client.post("/api/v1/auth/login", json={"email": BODY["email"], "password": BODY["password"]})
    ).status_code == 200


async def test_duplicate_and_concurrent_registration_creates_one_account(signup):
    responses = await asyncio.gather(
        *(
            signup.client.post("/api/v1/auth/register", json={**BODY, "email": email})
            for email in ["New.Owner@example.com", "new.owner@example.com", "  NEW.OWNER@EXAMPLE.COM "] * 2
        )
    )
    assert sorted(r.status_code for r in responses) == [201, 409, 409, 409, 409, 409]
    assert (await counts(signup))["businesses"] == 1 and len(signup.mailbox.messages) == 1


async def test_concurrent_verification_creates_one_session(signup):
    await register(signup)
    token = link_token(signup.mailbox.messages[0])
    responses = await asyncio.gather(
        *(signup.client.post("/api/v1/auth/verify-email", json={"token": token}) for _ in range(4))
    )
    assert sorted(r.status_code for r in responses) == [200, 400, 400, 400]
    assert (await counts(signup))["operator_sessions"] == 1


async def test_same_business_names_remain_isolated(signup):
    first = await verified(signup)
    second = await verified(signup, email="second@example.com")
    assert first["operator"]["business"]["id"] != second["operator"]["business"]["id"]
    for account in (first, second):
        response = await signup.client.get("/api/v1/auth/me", headers={"authorization": f"Bearer {account['token']}"})
        assert response.json()["operator"] == account["operator"]
    async with signup.factory() as session:
        with pytest.raises(InvalidState, match="business-id"):
            await BusinessRepository(session).get_by_name("Мой бизнес")


@pytest.mark.parametrize(
    "change",
    [
        {"name": " "},
        {"name": "a" * 101},
        {"name": "bad\x00name"},
        {"name": "\tValid"},
        {"email": "broken"},
        {"email": None},
        {"password": "short"},
        {"password": " " * 12},
        {"password": "x" * 129},
        {"locale": "other"},
        {"business_id": "00000000-0000-0000-0000-000000000000"},
    ],
)
async def test_invalid_registration_writes_nothing(signup, change):
    response = await signup.client.post("/api/v1/auth/register", json={**BODY, **change})
    assert response.status_code == 422 and BODY["password"] not in response.text
    assert all(value == 0 for value in (await counts(signup)).values())


async def test_token_creation_failure_rolls_back_business_and_account(signup, monkeypatch):
    async def fail(*args, **kwargs):
        raise RuntimeError("simulated token insert failure")

    monkeypatch.setattr(account_email_service.AccountEmailService, "prepare", fail)
    assert (await signup.client.post("/api/v1/auth/register", json=BODY)).status_code == 500
    assert all(value == 0 for value in (await counts(signup)).values())


async def test_verification_session_failure_does_not_consume_link(signup, monkeypatch):
    await register(signup)
    token = link_token(signup.mailbox.messages[0])
    original = OperatorRepository.add_session

    async def fail(*args, **kwargs):
        raise RuntimeError("simulated session failure")

    monkeypatch.setattr(OperatorRepository, "add_session", fail)
    assert (await signup.client.post("/api/v1/auth/verify-email", json={"token": token})).status_code == 500
    monkeypatch.setattr(OperatorRepository, "add_session", original)
    assert (await signup.client.post("/api/v1/auth/verify-email", json={"token": token})).status_code == 200


async def test_missing_email_config_creates_nothing(signup, monkeypatch):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    signup.runtime.auth_mailer = ResendAuthMailer(signup.runtime.settings)
    response = await signup.client.post("/api/v1/auth/register", json=BODY)
    assert response.status_code == 503 and response.json()["code"] == "not_configured"
    assert all(value == 0 for value in (await counts(signup)).values())


async def test_email_outage_keeps_pending_account_and_allows_resend(signup):
    signup.mailbox.fail = True
    response = await register(signup)
    assert response.json()["email_delivery"] == "unavailable"
    assert (await counts(signup))["operator_sessions"] == 0
    signup.mailbox.fail = False
    await age_mail(signup)
    response = await signup.client.post("/api/v1/auth/resend-verification", json={"email": BODY["email"]})
    assert response.json() == {"status": "accepted"} and len(signup.mailbox.messages) == 1


async def test_recipient_cooldown_and_neutral_email_responses(signup):
    await register(signup)
    for email in [BODY["email"], "unknown@example.com"]:
        response = await signup.client.post("/api/v1/auth/resend-verification", json={"email": email})
        assert response.status_code == 200 and response.json() == {"status": "accepted"}
    assert len(signup.mailbox.messages) == 1
    await age_mail(signup)
    await signup.client.post("/api/v1/auth/resend-verification", json={"email": BODY["email"], "locale": "en"})
    assert len(signup.mailbox.messages) == 2 and signup.mailbox.messages[-1].locale == "en"


async def test_password_reset_revokes_sessions_and_all_other_reset_links(signup):
    account = await verified(signup)
    await age_mail(signup)
    response = await signup.client.post("/api/v1/auth/forgot-password", json={"email": BODY["email"]})
    assert response.json() == {"status": "accepted"}
    first = link_token(signup.mailbox.messages[-1])
    await age_mail(signup)
    await signup.client.post("/api/v1/auth/forgot-password", json={"email": BODY["email"]})
    second = link_token(signup.mailbox.messages[-1])
    assert first != second
    new = "new-qa-password-2026"
    response = await signup.client.post("/api/v1/auth/reset-password", json={"token": second, "password": new})
    assert response.status_code == 200 and "token" not in response.json()
    for token in [first, second]:
        assert (
            await signup.client.post(
                "/api/v1/auth/reset-password", json={"token": token, "password": "other-new-password"}
            )
        ).status_code == 400
    assert (
        await signup.client.get("/api/v1/auth/me", headers={"authorization": f"Bearer {account['token']}"})
    ).status_code == 401
    assert (
        await signup.client.post("/api/v1/auth/login", json={"email": BODY["email"], "password": BODY["password"]})
    ).status_code == 401
    assert (
        await signup.client.post("/api/v1/auth/login", json={"email": BODY["email"], "password": new})
    ).status_code == 200


async def test_expired_and_wrong_purpose_tokens_are_rejected(signup):
    await register(signup)
    token = link_token(signup.mailbox.messages[0])
    assert (
        await signup.client.post("/api/v1/auth/reset-password", json={"token": token, "password": "new-qa-password"})
    ).status_code == 400
    async with signup.factory() as session:
        row = await session.get(AuthEmailTokenRow, signup.mailbox.messages[0].id)
        row.expires_at = utcnow() - timedelta(seconds=1)
        await session.commit()
    assert (await signup.client.post("/api/v1/auth/verify-email", json={"token": token})).status_code == 400


async def test_concurrent_reset_uses_token_once(signup):
    await verified(signup)
    await age_mail(signup)
    await signup.client.post("/api/v1/auth/forgot-password", json={"email": BODY["email"]})
    token = link_token(signup.mailbox.messages[-1])
    responses = await asyncio.gather(
        *(
            signup.client.post("/api/v1/auth/reset-password", json={"token": token, "password": "new-qa-password"})
            for _ in range(3)
        )
    )
    assert sorted(r.status_code for r in responses) == [200, 400, 400]


async def test_signup_and_email_rate_limits(signup, monkeypatch):
    assert (
        await signup.client.post("/api/v1/auth/register", json=BODY, headers={"x-api-key": "wrong"})
    ).status_code == 401
    monkeypatch.setattr(registration_service, "REGISTRATION_LIMITER", LoginLimiter(limit=1, window_s=3600))
    await register(signup)
    assert (
        await signup.client.post("/api/v1/auth/register", json={**BODY, "email": "other@example.com"})
    ).status_code == 429
    monkeypatch.setattr(account_email_service, "EMAIL_LIMITER", LoginLimiter(limit=1, window_s=3600))
    assert (
        await signup.client.post("/api/v1/auth/forgot-password", json={"email": "unknown@example.com"})
    ).status_code == 200
    assert (
        await signup.client.post("/api/v1/auth/forgot-password", json={"email": "other@example.com"})
    ).status_code == 429


async def test_unicode_password_and_english_account(signup):
    data = await verified(signup, password="🔑" * 10, locale="en")
    assert data["operator"]["business"]["name"] == "My business"
    assert signup.mailbox.messages[0].locale == "en"


async def test_unknown_and_unverified_reset_requests_do_not_send_email(signup):
    await register(signup)
    await age_mail(signup)
    for email in [BODY["email"], "unknown@example.com"]:
        response = await signup.client.post("/api/v1/auth/forgot-password", json={"email": email})
        assert response.status_code == 200 and response.json() == {"status": "accepted"}
    assert len(signup.mailbox.messages) == 1


async def test_login_racing_password_reset_cannot_leave_an_old_password_session(signup):
    await verified(signup)
    await age_mail(signup)
    await signup.client.post("/api/v1/auth/forgot-password", json={"email": BODY["email"]})
    token = link_token(signup.mailbox.messages[-1])
    login, reset = await asyncio.gather(
        signup.client.post("/api/v1/auth/login", json={"email": BODY["email"], "password": BODY["password"]}),
        signup.client.post("/api/v1/auth/reset-password", json={"token": token, "password": "racing-reset-password"}),
    )
    assert reset.status_code == 200
    assert login.status_code in (200, 401)
    if login.status_code == 200:
        response = await signup.client.get(
            "/api/v1/auth/me", headers={"authorization": f"Bearer {login.json()['token']}"}
        )
        assert response.status_code == 401


async def test_recipient_hour_limit_is_persistent_in_postgres(signup):
    await register(signup)
    for _ in range(4):
        await age_mail(signup)
        assert (
            await signup.client.post("/api/v1/auth/resend-verification", json={"email": BODY["email"]})
        ).status_code == 200
    assert len(signup.mailbox.messages) == 5
    await age_mail(signup)
    # Resetting process IP counters must not bypass the recipient's DB limit.
    account_email_service.EMAIL_LIMITER._failures.clear()
    assert (await signup.client.post("/api/v1/auth/resend-verification", json={"email": BODY["email"]})).json() == {
        "status": "accepted"
    }
    assert len(signup.mailbox.messages) == 5


async def test_invalid_reset_password_does_not_consume_the_link(signup):
    await verified(signup)
    await age_mail(signup)
    await signup.client.post("/api/v1/auth/forgot-password", json={"email": BODY["email"]})
    token = link_token(signup.mailbox.messages[-1])
    for password in ["short", " " * 12, "x" * 129]:
        response = await signup.client.post("/api/v1/auth/reset-password", json={"token": token, "password": password})
        assert response.status_code == 422 and token not in response.text
    assert (
        await signup.client.post(
            "/api/v1/auth/reset-password", json={"token": token, "password": "valid-reset-password"}
        )
    ).status_code == 200
