"""Shared pieces of the real channel adapters: errors, normalized events, text limits."""

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# Telegram sendMessage: 1-4096 characters. Instagram Send API: 1000 bytes of UTF-8.
TELEGRAM_TEXT_LIMIT = 4096
INSTAGRAM_TEXT_BYTES = 1000
# The core rejects longer input; a longer customer message is cut and marked.
INBOUND_TEXT_LIMIT = 4000


class ChannelError(Exception):
    """A provider call failed. `kind` decides what the caller does next.

    auth        token invalid or revoked: connection needs action, no retries
    permission  the account lacks a permission or role: needs action, no retries
    rate_limited  provider asked to slow down; retry after `retry_after` seconds
    transient   network error before the request reached the provider, or 5xx: retry
    ambiguous   timeout after the request was sent: the message may be delivered, do not resend
    recipient   customer blocked the bot / is unavailable / chat not found: no retries
    window      Instagram reply window is closed: no retries
    bad_request  the provider rejected the payload: no retries
    """

    def __init__(
        self,
        kind: str,
        code: str,
        message: str,
        *,
        retry_after: float | None = None,
        status: int | None = None,
    ) -> None:
        self.kind = kind
        self.code = code
        self.message = message[:300]
        self.retry_after = retry_after
        self.status = status
        super().__init__(f"{kind}:{code}: {self.message}")

    @property
    def retryable(self) -> bool:
        return self.kind in ("rate_limited", "transient")

    @property
    def needs_action(self) -> bool:
        return self.kind in ("auth", "permission")

    def describe(self) -> str:
        """What the dashboard shows: plain Russian, no provider internals."""

        if self.code in _HUMAN:
            return _HUMAN[self.code]
        if self.kind in ("transient", "ambiguous", "rate_limited"):
            return "Сервис канала временно недоступен. Повторите проверку позже."
        return self.message


_HUMAN = {
    "token_invalid": "Токен недействителен или отозван. Замените его на сервере и подключите снова.",
    "credential_missing": "Серверная конфигурация больше недоступна этому бизнесу.",
    "credential_empty": "В серверной конфигурации нет токена.",
    "missing_permission": "У приложения нет нужных прав или роли для этого аккаунта.",
    "public_url_unreachable": "Telegram не нашёл публичный адрес API Plumo. Проверьте PUBLIC_BASE_URL на сервере и подключите снова.",
    "subscription_failed":"Meta не подтвердила подписку на сообщения.",
}


@dataclass(slots=True)
class ChannelEvent:
    """One provider event, normalized. `external_event_id` is the dedup key within a connection."""

    external_event_id: str
    kind: str
    sender_id: str | None = None
    chat_id: str | None = None
    provider_message_id: str | None = None
    text: str | None = None
    provider_time: datetime | None = None
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AccountInfo:
    external_account_id: str
    display_name: str
    username: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


def clip_inbound(text: str) -> tuple[str, bool]:
    text = text.strip()
    if len(text) <= INBOUND_TEXT_LIMIT:
        return text, False
    return text[: INBOUND_TEXT_LIMIT - 1] + "…", True


def fits(channel: str, text: str) -> bool:
    if channel == "instagram":
        return len(text.encode("utf-8")) <= INSTAGRAM_TEXT_BYTES
    return len(text) <= TELEGRAM_TEXT_LIMIT


_BREAKS = re.compile(r"(?<=[.!?…])\s+|\n+")


def split_for_channel(channel: str, text: str) -> list[str]:
    """Cut an agent reply into parts the channel accepts, on sentence and word borders.

    Manager messages are not split: the dashboard rejects a text that does not fit.
    """

    text = text.strip()
    if fits(channel, text):
        return [text]
    parts: list[str] = []
    current = ""
    for piece in _pieces(channel, text):
        candidate = f"{current} {piece}".strip() if current else piece
        if fits(channel, candidate):
            current = candidate
            continue
        if current:
            parts.append(current)
        current = piece
    if current:
        parts.append(current)
    return parts


def _pieces(channel: str, text: str) -> list[str]:
    """Sentences; a sentence that alone does not fit is split by words, a word by characters."""

    result: list[str] = []
    for sentence in (item.strip() for item in _BREAKS.split(text)):
        if not sentence:
            continue
        if fits(channel, sentence):
            result.append(sentence)
            continue
        for word in sentence.split():
            while not fits(channel, word):
                cut = len(word) // 2
                while cut > 1 and not fits(channel, word[:cut]):
                    cut //= 2
                result.append(word[:cut])
                word = word[cut:]
            result.append(word)
    return result
