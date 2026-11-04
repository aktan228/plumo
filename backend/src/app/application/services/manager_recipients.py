"""Which Telegram chat gets a business's handoff notifications.

The operator asks for a one-time code, the manager sends it to the service bot as
`/start plumo_mgr_<code>`, the chat waits as a candidate and the operator confirms it.
Only the code's hash is stored. A chat id typed into a form never becomes a recipient:
it has to come from an authentic update of the service bot. The business always comes
from the operator's session or from the code, never from the request.
"""

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.domain.errors import InvalidState, NotFound
from app.domain.models import utcnow
from app.infrastructure.database.models import ManagerRecipientRow

START_PREFIX = "plumo_mgr_"
CODE_TTL = timedelta(minutes=15)

NOT_CONFIGURED = "not_configured"
WAITING_CODE = "waiting_code"
AWAITING_CONFIRMATION = "awaiting_confirmation"
READY = "ready"
NEEDS_ATTENTION = "needs_attention"

BOUND_REPLY = "Код принят. Вернитесь в кабинет Plumo и подтвердите этот чат, чтобы получать сюда уведомления."
UNKNOWN_CODE_REPLY = "Код не найден или просрочен. Получите новую ссылку в кабинете Plumo."
CONTROL_TEXT = "Plumo: этот чат подтверждён. Сюда будут приходить уведомления, когда клиенту нужен менеджер."


def manager_webhook_secret(key: str) -> str:
    """Secret for the service bot's setWebhook, derived from CHANNEL_SECRET_KEY, never stored."""

    digest = hmac.new(key.encode(), b"telegram-manager-bot", hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def _hash(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


@dataclass(frozen=True)
class StartCode:
    chat_id: str
    label: str
    code: str


def parse_start(update: Any) -> StartCode | None:
    """`/start plumo_mgr_<code>` from a person in a private chat, else None."""

    if not isinstance(update, dict):
        return None
    message = update.get("message")
    if not isinstance(message, dict):
        return None
    chat = message.get("chat") or {}
    sender = message.get("from") or {}
    text = message.get("text")
    if chat.get("type") != "private" or sender.get("is_bot") or not isinstance(text, str):
        return None
    command, _, parameter = text.strip().partition(" ")
    if command != "/start" or not parameter.startswith(START_PREFIX):
        return None
    chat_id = str(chat.get("id") or "")
    code = parameter[len(START_PREFIX) :].strip()[:128]
    if not chat_id.lstrip("-").isdigit() or not code:
        return None
    name = " ".join(str(part) for part in (sender.get("first_name"), sender.get("last_name")) if part).strip()
    handle = f"@{sender['username']}" if sender.get("username") else ""
    label = " ".join(part for part in (name, handle) if part)[:200] or f"Telegram {chat_id}"
    return StartCode(chat_id=chat_id, label=label, code=code)


def status_of(row: ManagerRecipientRow | None, now: datetime | None = None) -> str:
    if row is None:
        return NOT_CONFIGURED
    if row.chat_id:
        return NEEDS_ATTENTION if row.attention else READY
    if row.candidate_chat_id:
        return AWAITING_CONFIRMATION
    if row.code_hash and row.code_expires_at and row.code_expires_at > (now or utcnow()):
        return WAITING_CODE
    return NOT_CONFIGURED


class ManagerRecipients:
    def __init__(self, session) -> None:
        self.session = session

    async def get(self, business_id, *, lock: bool = False) -> ManagerRecipientRow | None:
        stmt = select(ManagerRecipientRow).where(ManagerRecipientRow.business_id == business_id)
        if lock:
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
        return await self.session.scalar(stmt)

    async def issue_code(self, business_id) -> tuple[ManagerRecipientRow, str]:
        """A new one-time code; the previous unused one stops working. The confirmed chat stays."""

        now = utcnow()
        # Two first clicks at once must not both insert the row.
        await self.session.execute(
            insert(ManagerRecipientRow)
            .values(business_id=business_id, created_at=now, updated_at=now)
            .on_conflict_do_nothing(index_elements=[ManagerRecipientRow.business_id])
        )
        row = await self.get(business_id, lock=True)
        code = secrets.token_urlsafe(16)
        row.code_hash = _hash(code)
        row.code_expires_at = now + CODE_TTL
        row.candidate_chat_id = row.candidate_label = row.candidate_seen_at = None
        row.updated_at = now
        row.version += 1
        await self.session.flush()
        return row, code

    async def accept_start(self, start: StartCode) -> bool:
        """The service bot got a code: its chat becomes the candidate of that business. Single use."""

        row = await self.session.scalar(
            select(ManagerRecipientRow)
            .where(ManagerRecipientRow.code_hash == _hash(start.code))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        now = utcnow()
        if row is None or row.code_expires_at is None or row.code_expires_at <= now:
            return False
        row.code_hash = row.code_expires_at = None
        row.candidate_chat_id = start.chat_id
        row.candidate_label = start.label
        row.candidate_seen_at = now
        row.updated_at = now
        row.version += 1
        await self.session.flush()
        return True

    async def confirm(self, business_id, operator_id) -> ManagerRecipientRow:
        row = await self.get(business_id, lock=True)
        if row is None or not row.candidate_chat_id:
            raise InvalidState("No chat is waiting for confirmation. Send the new link to the manager first.", code="no_candidate")
        now = utcnow()
        row.chat_id, row.chat_label = row.candidate_chat_id, row.candidate_label
        row.candidate_chat_id = row.candidate_label = row.candidate_seen_at = None
        row.confirmed_at, row.confirmed_by = now, operator_id
        row.attention = row.attention_at = None
        row.updated_at = now
        row.version += 1
        await self.session.flush()
        return row

    async def disconnect(self, business_id) -> None:
        row = await self.get(business_id, lock=True)
        if row is None:
            raise NotFound("Manager notifications are not set up.", code="recipient_not_found")
        row.code_hash = row.code_expires_at = None
        row.candidate_chat_id = row.candidate_label = row.candidate_seen_at = None
        row.chat_id = row.chat_label = row.confirmed_at = row.confirmed_by = None
        row.attention = row.attention_at = None
        row.updated_at = utcnow()
        row.version += 1
        await self.session.flush()

    async def chat_for(self, business_id) -> str | None:
        """The confirmed chat of this business only. No shared fallback chat exists."""

        row = await self.get(business_id)
        return row.chat_id if row is not None and row.chat_id else None

    async def mark(self, business_id, chat_id: str, attention: str | None) -> None:
        """Record the outcome of a send to `chat_id`; a recipient changed meanwhile is left alone."""

        row = await self.get(business_id, lock=True)
        if row is None or row.chat_id != chat_id or row.attention == attention:
            return
        row.attention = attention
        row.attention_at = utcnow() if attention else None
        row.updated_at = utcnow()
        await self.session.flush()
