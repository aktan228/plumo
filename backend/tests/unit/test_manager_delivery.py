from uuid import uuid4

import httpx
import pytest

from app.domain.errors import ProviderDeliveryUnknown, ProviderUnavailable
from app.domain.models import HandoffRequest, utcnow
from app.infrastructure.handoff.telegram_provider import TelegramHandoffProvider


def handoff():
    now = utcnow()
    return HandoffRequest(uuid4(), uuid4(), uuid4(), "no_knowledge", "normal", "Approved test summary", [], "PENDING", now, now)


@pytest.mark.parametrize("mode", ["read_timeout", "missing_receipt", "invalid_receipt"])
async def test_ambiguous_delivery_never_becomes_a_safe_retry(mode):
    def transport(request):
        if mode == "read_timeout":
            raise httpx.ReadTimeout("no receipt", request=request)
        if mode == "invalid_receipt":
            return httpx.Response(200, json={"ok": True, "result": {"message_id": "bad"}})
        return httpx.Response(200, json={"ok": True})
    provider = TelegramHandoffProvider(token="test-token", transport=httpx.MockTransport(transport))
    try:
        with pytest.raises(ProviderDeliveryUnknown):
            await provider.notify_to(handoff(), "101")
    finally:
        await provider.aclose()


async def test_shared_environment_chat_is_never_an_implicit_recipient(monkeypatch):
    monkeypatch.setenv("TELEGRAM_MANAGER_CHAT_ID", "999")
    provider = TelegramHandoffProvider(token="test-token", transport=httpx.MockTransport(lambda req: pytest.fail("no send expected")))
    try:
        with pytest.raises(ProviderUnavailable):
            await provider.notify(handoff())
    finally:
        await provider.aclose()
