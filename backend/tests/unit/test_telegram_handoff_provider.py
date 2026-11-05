"""How the service bot's Telegram answers map to retry, unknown and refusal (PJ-02).

Repeating is safe only when the request surely did not reach Telegram (no connection)
or Telegram said "not now" (429). After a 5xx, a read timeout or a reply without a
receipt Telegram may have delivered it: that is `unknown`, a person decides.
"""

import httpx
import pytest

from app.domain.errors import ProviderDeliveryUnknown, ProviderTransientError, ProviderUnavailable
from app.infrastructure.handoff.telegram_provider import TelegramHandoffProvider

RECEIPT = {"ok": True, "result": {"message_id": 7}}


def _provider(handler) -> TelegramHandoffProvider:
    return TelegramHandoffProvider(token="12345:test-only", transport=httpx.MockTransport(handler))


def _answer(status: int, body: dict | None = None):
    return lambda request: httpx.Response(status, json=body if body is not None else {"ok": False})


def _raise(error: Exception):
    def handler(request):
        raise error

    return handler


async def test_receipt_means_sent():
    await _provider(_answer(200, RECEIPT)).send_text("101", "hi")


async def test_no_connection_is_safe_to_repeat():
    with pytest.raises(ProviderTransientError):
        await _provider(_raise(httpx.ConnectError("refused"))).send_text("101", "hi")


async def test_429_is_repeated_no_sooner_than_telegram_asks():
    with pytest.raises(ProviderTransientError) as caught:
        await _provider(_answer(429, {"ok": False, "parameters": {"retry_after": 17}})).send_text("101", "hi")
    assert caught.value.retry_after == 17


@pytest.mark.parametrize("status", [500, 502, 503, 504])
async def test_5xx_after_sending_is_unknown_not_repeated(status):
    with pytest.raises(ProviderDeliveryUnknown):
        await _provider(_answer(status)).send_text("101", "hi")


async def test_read_timeout_after_sending_is_unknown():
    with pytest.raises(ProviderDeliveryUnknown):
        await _provider(_raise(httpx.ReadTimeout("no answer"))).send_text("101", "hi")


async def test_answer_without_a_receipt_is_unknown():
    with pytest.raises(ProviderDeliveryUnknown):
        await _provider(_answer(200, {"ok": True, "result": {}})).send_text("101", "hi")


@pytest.mark.parametrize("status", [400, 401, 403])
async def test_refusal_is_final(status):
    with pytest.raises(ProviderUnavailable):
        await _provider(_answer(status)).send_text("101", "hi")
