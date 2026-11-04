"""The older Dashboard API over the same recipient as `manager_recipients` (one row per business).

State, confirmation and disconnection come from `ManagerRecipients`, so this API and
/manager-notifications never disagree about who gets the notifications or in what state.
What stays here is this API's shape: optimistic `version`, `mgr_` codes, cancel.
Only hashes of binding codes persist.
"""
import hashlib
import re
import secrets

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.application.services.manager_recipients import (
    AWAITING_CONFIRMATION,
    CODE_TTL,
    NEEDS_ATTENTION,
    NOT_CONFIGURED,
    READY,
    WAITING_CODE,
    ManagerRecipients,
    service_bot_token,
    service_bot_username,
    status_of,
)
from app.domain.errors import InvalidState, NotConfigured, VersionConflict
from app.domain.models import utcnow
from app.infrastructure.database.models import ManagerRecipientRow

# The canonical status as this API names it.
_STATE = {
    NOT_CONFIGURED: "not_configured",
    WAITING_CODE: "awaiting_confirmation",
    AWAITING_CONFIRMATION: "awaiting_confirmation",
    READY: "ready",
    NEEDS_ATTENTION: "attention",
}


def manager_token():
    return service_bot_token()


def manager_configured():
    """The service bot can send notifications and hand out t.me links: a token and its @name."""

    return bool(service_bot_token() and re.fullmatch(r"[A-Za-z0-9_]{5,32}", service_bot_username() or ""))


class ManagerRecipientService:
    def __init__(self, session):
        self.session = session

    async def get(self, business_id, *, lock=False):
        await self.session.execute(insert(ManagerRecipientRow).values(business_id=business_id).on_conflict_do_nothing())
        stmt = select(ManagerRecipientRow).where(ManagerRecipientRow.business_id == business_id)
        if lock:
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
        return await self.session.scalar(stmt)

    def output(self, row, *, configured):
        status = status_of(row)
        return {
            "version": row.version, "configured": configured,
            "state": _STATE[status],
            "recipient": {"chat_id": row.chat_id, "name": row.display_name} if row.chat_id else None,
            "candidate": {"chat_id": row.candidate_chat_id, "name": row.candidate_name} if row.candidate_chat_id else None,
            "expires_at": row.expires_at if status == WAITING_CODE else None,
        }

    async def begin(self, business_id, version):
        if not manager_configured():
            raise NotConfigured("The notification bot is not configured", code="manager_bot_not_configured")
        row = await self.get(business_id, lock=True)
        self._version(row, version)
        if row.expires_at and row.expires_at > utcnow() and (utcnow() - row.updated_at).total_seconds() < 30:
            raise InvalidState("Wait before creating another link", code="manager_link_cooldown")
        code = secrets.token_urlsafe(32)
        row.pending_hash = hashlib.sha256(code.encode()).hexdigest()
        row.expires_at = utcnow() + CODE_TTL
        row.candidate_chat_id = row.candidate_name = None
        self._touch(row)
        await self.session.flush()
        return row, f"https://t.me/{service_bot_username()}?start=mgr_{code}"

    async def discover(self, update):
        message = update.get("message")
        if not isinstance(message, dict):
            return
        chat, sender = message.get("chat") or {}, message.get("from") or {}
        match = re.fullmatch(r"/start(?:@[A-Za-z0-9_]+)? mgr_([A-Za-z0-9_-]{43})", str(message.get("text", "")))
        if (not match or not isinstance(chat, dict) or not isinstance(sender, dict) or chat.get("type") != "private"
                or type(chat.get("id")) is not int or chat["id"] <= 0 or sender.get("id") != chat["id"] or sender.get("is_bot")):
            return
        row = await self.session.scalar(select(ManagerRecipientRow).where(
            ManagerRecipientRow.pending_hash == hashlib.sha256(match[1].encode()).hexdigest()
        ).with_for_update().execution_options(populate_existing=True))
        if row is None or row.expires_at is None or row.expires_at <= utcnow() or not row.pending_hash:
            return
        username = sender.get("username")
        row.candidate_name = (f"@{username}" if isinstance(username, str) and re.fullmatch(r"[A-Za-z0-9_]+", username)
                              else str(sender.get("first_name") or "Telegram manager"))[:200]
        row.candidate_chat_id = str(chat["id"])
        row.candidate_seen_at = utcnow()
        # One genuine event consumes the code; replay cannot replace the candidate.
        row.pending_hash = row.expires_at = None
        self._touch(row)
        await self.session.flush()

    async def change(self, business_id, version, action, operator_id=None):
        row = await self.get(business_id, lock=True)
        self._version(row, version)
        recipients = ManagerRecipients(self.session)
        if action == "confirm":
            # The same rule as /manager-notifications/confirm: a candidate that came with a valid code.
            return await recipients.confirm(business_id, operator_id)
        if action == "disconnect":
            await recipients.disconnect(business_id)
            return await self.get(business_id)
        row.pending_hash = row.candidate_chat_id = row.candidate_name = row.candidate_seen_at = row.expires_at = None
        self._touch(row)
        await self.session.flush()
        return row

    @staticmethod
    def _version(row, version):
        if row.version != version:
            raise VersionConflict("The recipient changed. Refresh before changing it.")

    @staticmethod
    def _touch(row):
        row.version += 1
        row.updated_at = utcnow()
