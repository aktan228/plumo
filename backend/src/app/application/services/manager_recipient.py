"""One confirmed private-chat recipient per tenant; only hashes of binding codes persist."""
import hashlib
import os
import re
import secrets
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.domain.errors import InvalidState, NotConfigured, VersionConflict
from app.domain.models import utcnow
from app.infrastructure.database.models import ManagerRecipientRow


def manager_token():
    return (os.getenv("MANAGER_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()


def manager_configured():
    return bool(manager_token() and re.fullmatch(r"[A-Za-z0-9_]{5,32}", os.getenv("MANAGER_BOT_USERNAME", ""))
                and re.fullmatch(r"[A-Za-z0-9_-]{32,256}", os.getenv("MANAGER_WEBHOOK_SECRET", "")))


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
        pending = row.expires_at is not None and row.expires_at > utcnow() and (row.pending_hash or row.candidate_chat_id)
        return {
            "version": row.version, "configured": configured,
            "state": "awaiting_confirmation" if pending else "ready" if row.chat_id and configured else "attention" if row.chat_id else "not_configured",
            "recipient": {"chat_id": row.chat_id, "name": row.display_name} if row.chat_id else None,
            "candidate": {"chat_id": row.candidate_chat_id, "name": row.candidate_name} if pending and row.candidate_chat_id else None,
            "expires_at": row.expires_at if pending else None,
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
        row.expires_at = utcnow() + timedelta(minutes=10)
        row.candidate_chat_id = row.candidate_name = None
        self._touch(row)
        await self.session.flush()
        return row, f"https://t.me/{os.environ['MANAGER_BOT_USERNAME']}?start=mgr_{code}"

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
        row.pending_hash = None  # One genuine event consumes the code; replay cannot replace the candidate.
        self._touch(row)
        await self.session.flush()

    async def change(self, business_id, version, action):
        row = await self.get(business_id, lock=True)
        self._version(row, version)
        if action == "confirm":
            if not row.candidate_chat_id or not row.expires_at or row.expires_at <= utcnow():
                raise InvalidState("The binding expired or has no candidate", code="manager_binding_expired")
            row.chat_id, row.display_name = row.candidate_chat_id, row.candidate_name
        elif action == "disconnect":
            row.chat_id = row.display_name = None
        row.pending_hash = row.candidate_chat_id = row.candidate_name = row.expires_at = None
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
