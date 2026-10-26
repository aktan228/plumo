"""Telegram Bot API: the business's own bot, private text chats only.

Methods per https://core.telegram.org/bots/api (checked 2026-10-14): getMe,
getWebhookInfo, setWebhook (secret_token, 1-256 chars of A-Za-z0-9_-, comes back
in X-Telegram-Bot-Api-Secret-Token), deleteWebhook, sendMessage (1-4096 chars).

The bot token is part of every URL. It is never logged, never put into an
exception message, and httpx request logging is switched off for it.
"""

import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from app.infrastructure.channels.base import AccountInfo, ChannelError, ChannelEvent, clip_inbound

logger = logging.getLogger("plumo.channels.telegram")

API = "https://api.telegram.org"
# Only private messages are needed; edits, reactions and member updates are not requested.
ALLOWED_UPDATES = ["message"]
_MEDIA = (
    "photo",
    "voice",
    "video",
    "video_note",
    "audio",
    "document",
    "sticker",
    "animation",
    "contact",
    "location",
    "venue",
    "poll",
    "dice",
    "story",
)


class TelegramClient:
    def __init__(self, token: str, *, timeout_s: float = 15.0, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._token = token
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(timeout_s, connect=5.0), transport=transport)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get_me(self) -> AccountInfo:
        user = await self._call("getMe", {})
        if not isinstance(user, dict) or not user.get("id"):
            raise ChannelError("bad_request", "unexpected_response", "getMe returned no bot id")
        name = " ".join(part for part in (user.get("first_name"), user.get("last_name")) if part) or "Telegram bot"
        return AccountInfo(
            external_account_id=str(user["id"]),
            display_name=name,
            username=user.get("username"),
            details={"is_bot": bool(user.get("is_bot"))},
        )

    async def get_webhook_info(self) -> dict[str, Any]:
        info = await self._call("getWebhookInfo", {})
        return info if isinstance(info, dict) else {}

    async def set_webhook(self, url: str, secret_token: str) -> None:
        await self._call(
            "setWebhook",
            {
                "url": url,
                "secret_token": secret_token,
                "allowed_updates": ALLOWED_UPDATES,
                "max_connections": 10,
                # Updates that waited while the webhook was elsewhere are kept.
                "drop_pending_updates": False,
            },
        )

    async def delete_webhook(self) -> None:
        await self._call("deleteWebhook", {"drop_pending_updates": False})

    async def send_message(self, chat_id: str, text: str) -> str:
        # No parse_mode: the text goes out as typed, a stray "*" or "<" cannot break it.
        result = await self._call(
            "sendMessage",
            {"chat_id": chat_id, "text": text, "link_preview_options": {"is_disabled": True}},
            sends=True,
        )
        message_id = result.get("message_id") if isinstance(result, dict) else None
        if message_id is None:
            raise ChannelError("ambiguous", "no_message_id", "sendMessage answered without message_id")
        return str(message_id)

    async def _call(self, method: str, body: dict, *, sends: bool = False):
        url = f"{API}/bot{self._token}/{method}"
        try:
            response = await self._client.post(url, json=body)
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout):
            # The request never reached Telegram: safe to repeat.
            raise ChannelError("transient", "telegram_unreachable", "Telegram is unreachable") from None
        except httpx.TimeoutException:
            if sends:
                raise ChannelError("ambiguous", "telegram_timeout", "Telegram did not answer in time") from None
            raise ChannelError("transient", "telegram_timeout", "Telegram did not answer in time") from None
        except httpx.HTTPError:
            kind = "ambiguous" if sends else "transient"
            raise ChannelError(kind, "telegram_network_error", "network error talking to Telegram") from None
        return _result(response, sends)


def _result(response: httpx.Response, sends: bool):
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    if response.status_code < 300 and payload.get("ok"):
        return payload.get("result")
    status = response.status_code
    description = str(payload.get("description") or f"HTTP {status}")[:200]
    parameters = payload.get("parameters") or {}
    if status == 401:
        raise ChannelError("auth", "token_invalid", "Telegram rejected the bot token", status=status)
    if status == 429:
        raw = parameters.get("retry_after")
        retry = float(raw) if raw is not None else 5.0
        raise ChannelError("rate_limited", "telegram_rate_limited", description, retry_after=retry, status=status)
    if status == 403:
        # "bot was blocked by the user", "user is deactivated"
        raise ChannelError("recipient", "recipient_blocked", description, status=status)
    if status == 400 and "chat not found" in description.lower():
        raise ChannelError("recipient", "chat_not_found", description, status=status)
    if status >= 500:
        kind = "ambiguous" if sends else "transient"
        raise ChannelError(kind, "telegram_server_error", description, status=status)
    raise ChannelError("bad_request", "telegram_bad_request", description, status=status)


def parse_update(update: dict[str, Any]) -> ChannelEvent | None:
    """One Telegram Update to an event, or None when it has no update_id.

    Text in a private chat is a customer message. /start is a separate kind.
    Media, groups, channels and service updates are kept as unsupported or ignored
    and never reach the model with empty text.
    """

    update_id = update.get("update_id")
    if update_id is None:
        return None
    event_id = str(update_id)
    message = update.get("message")
    if not isinstance(message, dict):
        kind = next((key for key in update if key != "update_id"), "unknown")
        return ChannelEvent(event_id, "ignored", data={"update_type": str(kind)[:40]})
    chat = message.get("chat") or {}
    sender = message.get("from") or {}
    when = _time(message.get("date"))
    if chat.get("type") != "private" or sender.get("is_bot"):
        return ChannelEvent(event_id, "ignored", provider_time=when, data={"update_type": f"chat:{chat.get('type')}"})
    chat_id = str(chat.get("id") or "")
    sender_id = str(sender.get("id") or chat_id)
    if not chat_id:
        return ChannelEvent(event_id, "ignored", data={"update_type": "no_chat"})
    data = _contact(sender)
    data["chat_id"] = chat_id
    message_id = str(message.get("message_id")) if message.get("message_id") is not None else None
    text = message.get("text")
    if isinstance(text, str) and text.strip():
        stripped = text.strip()
        if stripped.startswith("/start plumo_check_"):
            data["start_parameter"] = stripped[len("/start "):][:128]
        if stripped == "/start" or stripped.startswith("/start "):
            return ChannelEvent(event_id, "start", sender_id, chat_id, message_id, "/start", when, data)
        clipped, cut = clip_inbound(stripped)
        if cut:
            data["truncated"] = True
        return ChannelEvent(event_id, "text", sender_id, chat_id, message_id, clipped, when, data)
    media = next((key for key in _MEDIA if key in message), "other")
    data["unsupported"] = media
    caption = message.get("caption")
    if isinstance(caption, str) and caption.strip():
        data["has_caption"] = True
    return ChannelEvent(event_id, "unsupported", sender_id, chat_id, message_id, f"[{media}]", when, data)


def _contact(sender: dict) -> dict[str, Any]:
    name = " ".join(str(part) for part in (sender.get("first_name"), sender.get("last_name")) if part).strip()
    data: dict[str, Any] = {}
    if name:
        data["contact_name"] = name[:200]
    if sender.get("username"):
        data["contact_handle"] = "@" + str(sender["username"])[:99]
    return data


def _time(value) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(value), tz=UTC)
    except (TypeError, ValueError, OverflowError, OSError):
        return None
