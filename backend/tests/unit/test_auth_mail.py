import json
from uuid import uuid4

import httpx
import pytest

from app.config import Settings
from app.domain.errors import NotConfigured, ProviderUnavailable
from app.infrastructure.auth_mail import AuthEmail, ResendAuthMailer, email_content


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "test-only-key")
    return Settings(auth_public_url="https://app.plumo.example", auth_email_from="Plumo <account@plumo.example>")


async def test_resend_contract_and_retry_keep_idempotency_key(configured):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(503 if len(requests) == 1 else 200, json={"id": "email-id"})

    mail = AuthEmail(
        uuid4(), "fictional@example.com", "verify", "https://app.plumo.example/verify-email#token=test", "ru"
    )
    await ResendAuthMailer(configured, transport=httpx.MockTransport(handler)).send(mail)
    assert len(requests) == 2 and requests[0].headers["idempotency-key"] == requests[1].headers["idempotency-key"]
    payload = json.loads(requests[0].content)
    assert payload["to"] == [mail.recipient] and mail.link in payload["text"] and "Подтвердить" in payload["html"]
    assert requests[0].url == "https://api.resend.com/emails"


async def test_provider_errors_do_not_expose_secrets(configured):
    mail = AuthEmail(
        uuid4(), "fictional@example.com", "reset", "https://app.plumo.example/reset-password#token=secret", "en"
    )
    adapter = ResendAuthMailer(
        configured, transport=httpx.MockTransport(lambda request: httpx.Response(403, text="private provider error"))
    )
    with pytest.raises(ProviderUnavailable) as caught:
        await adapter.send(mail)
    assert "private provider error" not in str(caught.value) and "test-only-key" not in str(caught.value)


@pytest.mark.parametrize(
    "url",
    [
        "",
        "http://app.plumo.example",
        "https://user:password@app.plumo.example",
        "https://app.plumo.example/path",
        "https://app.plumo.example?redirect=evil",
    ],
)
def test_invalid_frontend_origins_rejected(configured, url):
    with pytest.raises(NotConfigured):
        ResendAuthMailer(configured.model_copy(update={"auth_public_url": url})).check_config()


def test_local_origin_only_allowed_in_development(configured):
    ResendAuthMailer(
        configured.model_copy(update={"auth_public_url": "http://127.0.0.1:13030", "app_env": "development"})
    ).check_config()
    with pytest.raises(NotConfigured):
        ResendAuthMailer(
            configured.model_copy(update={"auth_public_url": "http://127.0.0.1:13030", "app_env": "production"})
        ).check_config()


def test_email_templates_have_expiry_and_ignore_instructions():
    for purpose in ["verify", "reset"]:
        for locale in ["ru", "en"]:
            subject, text, html = email_content(
                AuthEmail(
                    uuid4(), "fictional@example.com", purpose, "https://app.plumo.example/page#token=safe", locale
                )
            )
            assert subject and "https://app.plumo.example/page#token=safe" in text and "<script" not in html
            assert ("24" if purpose == "verify" else "30") in text
