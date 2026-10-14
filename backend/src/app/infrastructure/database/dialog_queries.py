"""Dashboard reads: the dialog list with search, filters and keyset pagination, and one dialog's page.

Search and filters run in SQL over the whole business, not over a loaded page.
Order is last activity, newest first, then id: stable while new messages arrive.
"""

import base64
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.errors import InvalidMessage
from app.domain.models import Message
from app.infrastructure.database.models import MessageRow
from app.infrastructure.database.repositories import _message


@dataclass(slots=True)
class DialogRow:
    id: UUID
    channel: str
    mode: str
    mode_version: int
    waiting: bool
    customer_id: UUID
    connection_id: UUID | None
    contact_name: str | None
    contact_handle: str | None
    phone: str | None
    contact_phone: str | None
    language: str
    started_at: datetime
    activity_at: datetime
    last_text: str | None
    last_role: str | None
    last_at: datetime | None
    last_seq: int | None
    unread: int


def encode_cursor(activity_at: datetime, row_id: UUID) -> str:
    raw = json.dumps([activity_at.isoformat(), str(row_id)])
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        stamp, row_id = json.loads(base64.urlsafe_b64decode(padded.encode()).decode())
        return datetime.fromisoformat(stamp), UUID(row_id)
    except (ValueError, TypeError):
        raise InvalidMessage("cursor is invalid") from None


def _like(term: str) -> str:
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


class DialogQueries:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(
        self,
        *,
        business_id: UUID,
        operator_id: UUID,
        channel: str | None = None,
        mode: str | None = None,
        query: str | None = None,
        cursor: str | None = None,
        limit: int = 30,
    ) -> tuple[list[DialogRow], str | None]:
        params: dict[str, Any] = {"business_id": business_id, "operator_id": operator_id, "limit": limit + 1}
        where = ["c.business_id = :business_id"]
        if channel:
            where.append("c.channel = :channel")
            params["channel"] = channel
        term = (query or "").strip()
        if term:
            params["q"] = _like(term[:100])
            where.append(
                """(
                    c.contact_name ILIKE :q ESCAPE '\\' OR c.contact_handle ILIKE :q ESCAPE '\\'
                    OR cu.phone ILIKE :q ESCAPE '\\' OR cu.contact_phone ILIKE :q ESCAPE '\\'
                    OR EXISTS (
                        SELECT 1 FROM messages s
                        WHERE s.conversation_id = c.id AND s.role <> 'system' AND s.text ILIKE :q ESCAPE '\\'
                    )
                )"""
            )
        outer = []
        if mode == "human":
            outer.append("mode = 'human'")
        elif mode == "waiting":
            outer.append("mode = 'ai' AND waiting")
        elif mode == "ai":
            outer.append("mode = 'ai' AND NOT waiting")
        elif mode:
            raise InvalidMessage("mode must be ai, waiting or human")
        if cursor:
            cursor_at, cursor_id = decode_cursor(cursor)
            outer.append("(activity_at, id) < (:cursor_at, :cursor_id)")
            params["cursor_at"] = cursor_at
            params["cursor_id"] = cursor_id
        stmt = text(
            f"""
            WITH base AS (
                SELECT c.id, c.channel, c.mode, c.mode_version, c.customer_id, c.connection_id,
                       c.contact_name, c.contact_handle, c.started_at,
                       cu.phone, cu.contact_phone, cu.language,
                       lm.text AS last_text, lm.role AS last_role, lm.timestamp AS last_at, lm.seq AS last_seq,
                       COALESCE(lm.timestamp, c.started_at) AS activity_at,
                       EXISTS (
                           SELECT 1 FROM handoff_requests h
                           WHERE h.conversation_id = c.id AND h.status = 'PENDING'
                       ) AS waiting,
                       (
                           SELECT count(*) FROM messages u
                           WHERE u.conversation_id = c.id AND u.role = 'user'
                             AND u.seq > COALESCE(r.last_read_seq, 0)
                       ) AS unread
                FROM conversations c
                JOIN customers cu ON cu.id = c.customer_id
                LEFT JOIN conversation_reads r ON r.conversation_id = c.id AND r.operator_id = :operator_id
                LEFT JOIN LATERAL (
                    SELECT m.text, m.role, m.timestamp, m.seq FROM messages m
                    WHERE m.conversation_id = c.id
                    ORDER BY m.timestamp DESC, m.seq DESC
                    LIMIT 1
                ) lm ON true
                WHERE {" AND ".join(where)}
            )
            SELECT * FROM base
            {"WHERE " + " AND ".join(outer) if outer else ""}
            ORDER BY activity_at DESC, id DESC
            LIMIT :limit
            """
        )
        rows = [DialogRow(**dict(item)) for item in (await self.session.execute(stmt, params)).mappings().all()]
        next_cursor = None
        if len(rows) > limit:
            rows = rows[:limit]
            next_cursor = encode_cursor(rows[-1].activity_at, rows[-1].id)
        return rows, next_cursor

    async def one(self, *, business_id: UUID, operator_id: UUID, conversation_id: UUID) -> DialogRow | None:
        """One dialog of the business, or None: another business's id looks like a missing one."""

        stmt = text(
            """
            SELECT c.id, c.channel, c.mode, c.mode_version, c.customer_id, c.connection_id,
                   c.contact_name, c.contact_handle, c.started_at,
                   cu.phone, cu.contact_phone, cu.language,
                   lm.text AS last_text, lm.role AS last_role, lm.timestamp AS last_at, lm.seq AS last_seq,
                   COALESCE(lm.timestamp, c.started_at) AS activity_at,
                   EXISTS (
                       SELECT 1 FROM handoff_requests h WHERE h.conversation_id = c.id AND h.status = 'PENDING'
                   ) AS waiting,
                   (
                       SELECT count(*) FROM messages u
                       WHERE u.conversation_id = c.id AND u.role = 'user' AND u.seq > COALESCE(r.last_read_seq, 0)
                   ) AS unread
            FROM conversations c
            JOIN customers cu ON cu.id = c.customer_id
            LEFT JOIN conversation_reads r ON r.conversation_id = c.id AND r.operator_id = :operator_id
            LEFT JOIN LATERAL (
                SELECT m.text, m.role, m.timestamp, m.seq FROM messages m
                WHERE m.conversation_id = c.id ORDER BY m.timestamp DESC, m.seq DESC LIMIT 1
            ) lm ON true
            WHERE c.id = :conversation_id AND c.business_id = :business_id
            """
        )
        row = (
            await self.session.execute(
                stmt, {"conversation_id": conversation_id, "business_id": business_id, "operator_id": operator_id}
            )
        ).mappings().first()
        return DialogRow(**dict(row)) if row else None

    async def messages_page(
        self, conversation_id: UUID, *, before: str | None = None, limit: int = 50
    ) -> tuple[list[Message], str | None]:
        """Newest `limit` messages before the cursor, returned oldest first. Cursor = (timestamp, seq)."""

        stmt = select(MessageRow).where(MessageRow.conversation_id == conversation_id)
        if before:
            stamp, seq = _decode_message_cursor(before)
            stmt = stmt.where(
                (MessageRow.timestamp < stamp) | ((MessageRow.timestamp == stamp) & (MessageRow.seq < seq))
            )
        stmt = stmt.order_by(MessageRow.timestamp.desc(), MessageRow.seq.desc()).limit(limit + 1)
        rows = list((await self.session.scalars(stmt)).all())
        older = None
        if len(rows) > limit:
            rows = rows[:limit]
            older = _encode_message_cursor(rows[-1].timestamp, rows[-1].seq)
        rows.reverse()
        return [_message(row) for row in rows], older


def _encode_message_cursor(stamp: datetime, seq: int) -> str:
    raw = json.dumps([stamp.isoformat(), seq])
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def _decode_message_cursor(cursor: str) -> tuple[datetime, int]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        stamp, seq = json.loads(base64.urlsafe_b64decode(padded.encode()).decode())
        return datetime.fromisoformat(stamp), int(seq)
    except (ValueError, TypeError):
        raise InvalidMessage("cursor is invalid") from None
