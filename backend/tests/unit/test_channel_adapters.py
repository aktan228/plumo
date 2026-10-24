"""Telegram and Instagram adapters without a database: parsing, signatures, error mapping, limits."""

import hashlib
import hmac
import json
import logging
import re
from uuid import uuid4

import httpx
import pytest

from app.application.services.auth_service import LoginLimiter, hash_password, verify_password
from app.domain.errors import TooManyRequests
from app.infrastructure.channels.base import ChannelError, fits, split_for_channel
from app.infrastructure.channels.credentials import CredentialStore
from app.infrastructure.channels.gateway import telegram_webhook_secret
from app.infrastructure.channels.instagram import InstagramClient, parse_entry, valid_signature
from app.infrastructure.channels.telegram import TelegramClient, parse_update
from app.infrastructure.logging.setup import JsonFormatter, redact

TOKEN = "123456789:AAH-secret_part_of_the_token_xyz"


def _message(text=None, chat_type="private", **extra) -> dict:
    message = {
        "message_id": 10,
        "date": 1760000000,
        "chat": {"id": 555, "type": chat_type},
        "from": {"id": 555, "is_bot": False, "first_name": "Айгуль", "last_name": "К.", "username": "aigul"},
        **extra,
    }
    if text is not None:
        message["text"] = text
    return {"update_id": 9001, "message": message}


def test_telegram_text_start_media_and_groups() -> None:
    text = parse_update(_message("Саламатсызбы! Баасы канча? ң ө ү"))
    assert (text.kind, text.text, text.chat_id, text.external_event_id) == ("text", "Саламатсызбы! Баасы канча? ң ө ү", "555", "9001")
    assert text.data["contact_name"] == "Айгуль К." and text.data["contact_handle"] == "@aigul"

    assert parse_update(_message("/start promo")).kind == "start"
    photo = parse_update(_message(photo=[{"file_id": "x"}], caption="вот"))
    assert photo.kind == "unsupported" and photo.data["unsupported"] == "photo" and photo.text == "[photo]"
    assert parse_update(_message("всем привет", chat_type="group")).kind == "ignored"
    assert parse_update({"update_id": 1, "edited_message": {}}).kind == "ignored"
    assert parse_update({"message": {}}) is None

    long = parse_update(_message("я" * 5000))
    assert len(long.text) == 4000 and long.data["truncated"] is True


def test_telegram_secret_fits_the_allowed_alphabet() -> None:
    secret = telegram_webhook_secret(uuid4(), "nonce", key="k")
    assert re.fullmatch(r"[A-Za-z0-9_-]{1,256}", secret)
    assert secret != telegram_webhook_secret(uuid4(), "nonce", key="k")


def _client(handler) -> TelegramClient:
    return TelegramClient(TOKEN, transport=httpx.MockTransport(handler))


async def test_telegram_errors_are_classified_and_never_carry_the_token() -> None:
    async def run(handler, call):
        client = _client(handler)
        try:
            return await call(client)
        finally:
            await client.aclose()

    def status(code, body):
        return lambda request: httpx.Response(code, json=body)

    with pytest.raises(ChannelError) as revoked:
        await run(status(401, {"ok": False, "description": "Unauthorized"}), lambda c: c.get_me())
    assert revoked.value.kind == "auth" and revoked.value.needs_action

    with pytest.raises(ChannelError) as limited:
        await run(
            status(429, {"ok": False, "description": "Too Many Requests", "parameters": {"retry_after": 7}}),
            lambda c: c.send_message("1", "hi"),
        )
    assert limited.value.kind == "rate_limited" and limited.value.retry_after == 7.0

    with pytest.raises(ChannelError) as blocked:
        await run(status(403, {"ok": False, "description": "bot was blocked by the user"}), lambda c: c.send_message("1", "x"))
    assert blocked.value.kind == "recipient"

    def timeout(request):
        raise httpx.ReadTimeout("timed out", request=request)

    with pytest.raises(ChannelError) as ambiguous:
        await run(timeout, lambda c: c.send_message("1", "x"))
    assert ambiguous.value.kind == "ambiguous"
    assert ambiguous.value.__cause__ is None and ambiguous.value.__suppress_context__

    def refused(request):
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(ChannelError) as unreachable:
        await run(refused, lambda c: c.send_message("1", "x"))
    assert unreachable.value.kind == "transient"

    for error in (revoked.value, limited.value, blocked.value, ambiguous.value, unreachable.value):
        assert "secret_part" not in str(error)


async def test_telegram_send_is_plain_text() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 42}})

    client = _client(handler)
    assert await client.send_message("555", "<b>*цена*</b>") == "42"
    await client.aclose()
    assert "parse_mode" not in seen and seen["text"] == "<b>*цена*</b>"


def test_instagram_signature_is_checked_on_the_raw_body() -> None:
    body = json.dumps({"object": "instagram", "entry": []}).encode()
    signature = "sha256=" + hmac.new(b"app-secret", body, hashlib.sha256).hexdigest()
    assert valid_signature("app-secret", body, signature)
    assert not valid_signature("app-secret", body + b" ", signature)
    assert not valid_signature("other", body, signature)
    assert not valid_signature("app-secret", body, None)
    assert not valid_signature("", body, signature)


def test_instagram_batch_keeps_customer_messages_only() -> None:
    account = "17841400000000001"

    def item(message=None, **extra):
        base = {"sender": {"id": "IGSID-1"}, "recipient": {"id": account}, "timestamp": 1760000000123}
        if message is not None:
            base["message"] = message
        return {**base, **extra}

    entry = {
        "id": account,
        "messaging": [
            item({"mid": "m1", "text": "Здравствуйте, есть доставка?"}),
            item({"mid": "m2", "attachments": [{"type": "image", "payload": {"url": "https://x"}}]}),
            {"sender": {"id": account}, "recipient": {"id": "IGSID-1"}, "message": {"mid": "m3", "text": "наш ответ", "is_echo": True}},
            item(read={"mid": "m1"}),
            item(reaction={"mid": "m1", "action": "react", "emoji": "❤"}),
            item({"mid": "m4", "is_deleted": True}),
            item({"mid": "m5", "is_unsupported": True}),
            item({"mid": "m6", "text": "второе"}),
        ],
    }
    events = parse_entry(entry)
    assert [(item.external_event_id, item.kind) for item in events] == [
        ("m1", "text"),
        ("m2", "unsupported"),
        ("m5", "unsupported"),
        ("m6", "text"),
    ]
    assert events[0].chat_id == "IGSID-1" and events[0].provider_time.year == 2025


async def test_instagram_errors_are_classified() -> None:
    async def error(body, status=400):
        client = InstagramClient("IGtoken-secret", transport=httpx.MockTransport(lambda r: httpx.Response(status, json=body)))
        try:
            await client.send_message("IGSID", "hi")
        except ChannelError as exc:
            return exc
        finally:
            await client.aclose()

    assert (await error({"error": {"code": 190, "message": "expired"}})).kind == "auth"
    assert (await error({"error": {"code": 10, "error_subcode": 2534022, "message": "window"}})).kind == "window"
    assert (await error({"error": {"code": 4, "message": "limit"}})).kind == "rate_limited"
    assert (await error({"error": {"code": 10, "message": "no permission"}})).kind == "permission"
    assert (await error({"error": {"code": 551, "message": "unavailable"}})).kind == "recipient"
    assert (await error({"error": {"code": 2, "message": "boom"}}, 500)).kind == "ambiguous"


def test_long_agent_replies_are_split_to_channel_limits() -> None:
    text = ". ".join(["Квартира в центре, 2 комнаты, 85 000 USD, ремонт свежий"] * 40) + "."
    parts = split_for_channel("instagram", text)
    assert len(parts) > 1 and all(fits("instagram", part) for part in parts)
    assert " ".join(parts).replace("  ", " ") == text
    assert split_for_channel("telegram", "коротко") == ["коротко"]
    assert all(len(part) <= 4096 for part in split_for_channel("telegram", "я" * 9000))
    assert not fits("instagram", "я" * 501) and fits("instagram", "я" * 500)


def test_credentials_are_scoped_and_never_printed(tmp_path, monkeypatch) -> None:
    business, other = uuid4(), uuid4()
    file = tmp_path / "creds.json"
    file.write_text(
        json.dumps(
            {
                "credentials": [
                    {"ref": "tg", "channel": "telegram", "token_env": "TG_TOKEN_X", "business_ids": [str(business)]},
                    {"ref": "bad", "channel": "whatsapp", "token": "x", "business_ids": ["*"]},
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("TG_TOKEN_X", TOKEN)
    store = CredentialStore(str(file))
    found = store.get("tg", business, "telegram")
    assert found is not None and found.secret() == TOKEN and TOKEN not in repr(found)
    assert store.get("tg", other, "telegram") is None
    assert store.available(business, "instagram") == []
    assert CredentialStore("").all() == [] and CredentialStore(str(tmp_path / "missing.json")).all() == []


def test_logs_do_not_carry_tokens() -> None:
    line = f"POST https://api.telegram.org/bot{TOKEN}/sendMessage Authorization: Bearer IGQVJabcdefghijklmnop"
    clean = redact(line)
    assert "secret_part" not in clean and "IGQVJabcdefghijklmnop" not in clean
    record = logging.LogRecord("httpx", logging.INFO, __file__, 1, "HTTP Request: %s", (line,), None)
    assert "secret_part" not in JsonFormatter().format(record)


def test_passwords_and_sign_in_limit() -> None:
    stored = hash_password("correct horse battery")
    assert stored.startswith("scrypt$") and "correct" not in stored
    assert verify_password("correct horse battery", stored)
    assert not verify_password("wrong", stored) and not verify_password("x", "garbage")

    limiter = LoginLimiter(limit=2, window_s=60)
    limiter.failed("a@b.c")
    limiter.check("a@b.c")
    limiter.failed("a@b.c")
    with pytest.raises(TooManyRequests):
        limiter.check("a@b.c")
    limiter.check("other@b.c")
