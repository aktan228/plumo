"""Repositories for operators, channel connections, inbound events, deliveries and jobs."""

from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import ConnectionStatus, InboundStatus, JobStatus, OutboundStatus
from app.domain.models import (
    ChannelConnection,
    InboundEvent,
    Job,
    Operator,
    OperatorSession,
    OutboundMessage,
    utcnow,
)
from app.infrastructure.database.models import (
    ChannelConnectionRow,
    ConversationReadRow,
    InboundEventRow,
    JobRow,
    OperatorRow,
    OperatorSessionRow,
    OutboundMessageRow,
)


class OperatorRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, operator_id: UUID) -> Operator | None:
        row = await self.session.get(OperatorRow, operator_id)
        return _operator(row) if row else None

    async def get_with_hash(self, email: str) -> tuple[Operator, str] | None:
        row = await self.session.scalar(select(OperatorRow).where(OperatorRow.email == email.strip().lower()))
        return (_operator(row), row.password_hash) if row else None

    async def add(self, *, business_id: UUID, email: str, password_hash: str, display_name: str = "") -> Operator:
        now = utcnow()
        row = OperatorRow(
            id=uuid4(),
            business_id=business_id,
            email=email.strip().lower(),
            password_hash=password_hash,
            display_name=display_name.strip()[:100],
            active=True,
            created_at=now,
            updated_at=now,
        )
        self.session.add(row)
        await self.session.flush()
        return _operator(row)

    async def set_password(self, operator_id: UUID, password_hash: str) -> None:
        row = await self.session.get(OperatorRow, operator_id)
        if row is not None:
            row.password_hash = password_hash
            row.updated_at = utcnow()
            await self.session.flush()

    async def add_session(self, operator_id: UUID, token_hash: str, expires_at: datetime) -> None:
        now = utcnow()
        self.session.add(
            OperatorSessionRow(
                id=uuid4(),
                operator_id=operator_id,
                token_hash=token_hash,
                created_at=now,
                expires_at=expires_at,
                last_seen_at=now,
            )
        )
        await self.session.flush()

    async def find_session(self, token_hash: str) -> tuple[OperatorSession, Operator] | None:
        """A live session of an active operator, or None."""

        now = utcnow()
        stmt = (
            select(OperatorSessionRow, OperatorRow)
            .join(OperatorRow, OperatorRow.id == OperatorSessionRow.operator_id)
            .where(
                OperatorSessionRow.token_hash == token_hash,
                OperatorSessionRow.revoked_at.is_(None),
                OperatorSessionRow.expires_at > now,
                OperatorRow.active.is_(True),
            )
        )
        found = (await self.session.execute(stmt)).first()
        if found is None:
            return None
        session_row, operator_row = found
        if now - session_row.last_seen_at > timedelta(minutes=5):
            session_row.last_seen_at = now
            await self.session.flush()
        return (
            OperatorSession(session_row.id, operator_row.id, operator_row.business_id, session_row.expires_at),
            _operator(operator_row),
        )

    async def revoke_session(self, token_hash: str) -> None:
        await self.session.execute(
            update(OperatorSessionRow)
            .where(OperatorSessionRow.token_hash == token_hash, OperatorSessionRow.revoked_at.is_(None))
            .values(revoked_at=utcnow())
        )


class ConnectionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, connection_id: UUID) -> ChannelConnection | None:
        row = await self.session.get(ChannelConnectionRow, connection_id)
        return _connection(row) if row else None

    async def get_for_business(self, connection_id: UUID, business_id: UUID) -> ChannelConnection | None:
        row = await self.session.get(ChannelConnectionRow, connection_id)
        return _connection(row) if row is not None and row.business_id == business_id else None

    async def lock(self, connection_id: UUID) -> ChannelConnection | None:
        stmt = (
            select(ChannelConnectionRow)
            .where(ChannelConnectionRow.id == connection_id)
            .with_for_update(key_share=True)
            .execution_options(populate_existing=True)
        )
        row = await self.session.scalar(stmt)
        return _connection(row) if row else None

    async def list_for_business(self, business_id: UUID) -> list[ChannelConnection]:
        stmt = (
            select(ChannelConnectionRow)
            .where(ChannelConnectionRow.business_id == business_id)
            .order_by(ChannelConnectionRow.updated_at.desc())
        )
        return [_connection(row) for row in (await self.session.scalars(stmt)).all()]

    async def active(self, business_id: UUID, channel: str) -> ChannelConnection | None:
        stmt = select(ChannelConnectionRow).where(
            ChannelConnectionRow.business_id == business_id,
            ChannelConnectionRow.channel == channel,
            ChannelConnectionRow.status != ConnectionStatus.disconnected,
        )
        row = await self.session.scalar(stmt)
        return _connection(row) if row else None

    async def active_by_account(self, channel: str, external_account_id: str) -> ChannelConnection | None:
        stmt = select(ChannelConnectionRow).where(
            ChannelConnectionRow.channel == channel,
            ChannelConnectionRow.external_account_id == external_account_id,
            ChannelConnectionRow.status != ConnectionStatus.disconnected,
        )
        row = await self.session.scalar(stmt)
        return _connection(row) if row else None

    async def find_account(self, business_id: UUID, channel: str, external_account_id: str) -> ChannelConnection | None:
        stmt = select(ChannelConnectionRow).where(
            ChannelConnectionRow.business_id == business_id,
            ChannelConnectionRow.channel == channel,
            ChannelConnectionRow.external_account_id == external_account_id,
        )
        row = await self.session.scalar(stmt)
        return _connection(row) if row else None

    async def save(self, connection: ChannelConnection) -> ChannelConnection:
        row = await self.session.get(ChannelConnectionRow, connection.id)
        if row is None:
            row = ChannelConnectionRow(id=connection.id, created_at=connection.created_at)
            self.session.add(row)
        row.business_id = connection.business_id
        row.channel = connection.channel
        row.credential_ref = connection.credential_ref
        row.auth_method = connection.auth_method
        row.external_account_id = connection.external_account_id
        row.display_name = connection.display_name[:200]
        row.username = (connection.username or None) and connection.username[:100]
        row.status = connection.status
        row.agent_enabled = connection.agent_enabled
        row.webhook_nonce = connection.webhook_nonce
        row.version = connection.version
        row.last_check_at = connection.last_check_at
        row.last_check_ok = connection.last_check_ok
        row.last_event_at = connection.last_event_at
        row.last_error_code = connection.last_error_code
        row.last_error_message = (connection.last_error_message or None) and connection.last_error_message[:300]
        row.last_error_at = connection.last_error_at
        row.details = dict(connection.details)
        row.updated_at = utcnow()
        row.disconnected_at = connection.disconnected_at
        await self.session.flush()
        return _connection(row)

    async def touch_event(self, connection_id: UUID) -> None:
        await self.session.execute(
            update(ChannelConnectionRow).where(ChannelConnectionRow.id == connection_id).values(last_event_at=utcnow())
        )


class InboundEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add_if_new(self, event: InboundEvent) -> bool:
        """Insert unless (connection, external id) is already stored. True when this call stored it."""

        stmt = (
            insert(InboundEventRow)
            .values(
                id=event.id,
                business_id=event.business_id,
                connection_id=event.connection_id,
                channel=event.channel,
                external_event_id=event.external_event_id[:128],
                kind=event.kind,
                sender_id=event.sender_id,
                provider_message_id=(event.provider_message_id or None) and event.provider_message_id[:128],
                text=event.text,
                data=dict(event.data),
                provider_time=event.provider_time,
                received_at=event.received_at,
                status=event.status,
            )
            .on_conflict_do_nothing(constraint="uq_inbound_connection_event")
            .returning(InboundEventRow.id)
        )
        return (await self.session.execute(stmt)).first() is not None

    async def get(self, event_id: UUID) -> InboundEvent | None:
        row = await self.session.get(InboundEventRow, event_id)
        return _inbound(row) if row else None

    async def redact_older_than(self, days: int) -> int:
        """Clear text and contact data of finished events received more than `days` ago."""

        result = await self.session.execute(
            update(InboundEventRow)
            .where(
                InboundEventRow.received_at < utcnow() - timedelta(days=days),
                InboundEventRow.status != InboundStatus.queued,
                (InboundEventRow.text.is_not(None)) | (InboundEventRow.data != text("'{}'::jsonb")),
            )
            .values(text=None, data={})
        )
        return result.rowcount or 0

    async def mark(self, event_id: UUID, status: str, error_code: str | None = None) -> None:
        await self.session.execute(
            update(InboundEventRow)
            .where(InboundEventRow.id == event_id)
            .values(status=status, error_code=error_code, processed_at=utcnow())
        )


class OutboundRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, outbound: OutboundMessage) -> bool:
        """Insert unless the idempotency key is taken. True when this call stored it."""

        stmt = (
            insert(OutboundMessageRow)
            .values(
                id=outbound.id,
                business_id=outbound.business_id,
                conversation_id=outbound.conversation_id,
                connection_id=outbound.connection_id,
                message_id=outbound.message_id,
                author_role=outbound.author_role,
                operator_id=outbound.operator_id,
                text=outbound.text,
                idempotency_key=outbound.idempotency_key[:128],
                mode_version=outbound.mode_version,
                status=outbound.status,
                attempts=outbound.attempts,
                parts_sent=outbound.parts_sent,
                provider_message_ids=list(outbound.provider_message_ids),
                created_at=outbound.created_at,
                updated_at=outbound.updated_at,
            )
            .on_conflict_do_nothing(constraint="uq_outbound_business_idempotency")
            .returning(OutboundMessageRow.id)
        )
        return (await self.session.execute(stmt)).first() is not None

    async def get(self, outbound_id: UUID) -> OutboundMessage | None:
        row = await self.session.get(OutboundMessageRow, outbound_id)
        return _outbound(row) if row else None

    async def get_by_key(self, business_id: UUID, key: str) -> OutboundMessage | None:
        stmt = select(OutboundMessageRow).where(
            OutboundMessageRow.business_id == business_id, OutboundMessageRow.idempotency_key == key[:128]
        )
        row = await self.session.scalar(stmt)
        return _outbound(row) if row else None

    async def lock(self, outbound_id: UUID) -> OutboundMessage | None:
        stmt = (
            select(OutboundMessageRow)
            .where(OutboundMessageRow.id == outbound_id)
            .with_for_update(key_share=True)
            .execution_options(populate_existing=True)
        )
        row = await self.session.scalar(stmt)
        return _outbound(row) if row else None

    async def save(self, outbound: OutboundMessage) -> OutboundMessage:
        row = await self.session.get(OutboundMessageRow, outbound.id)
        if row is None:
            raise ValueError(f"outbound {outbound.id} disappeared")
        row.status = outbound.status
        row.attempts = outbound.attempts
        row.parts_sent = outbound.parts_sent
        row.provider_message_ids = list(outbound.provider_message_ids)
        row.error_code = outbound.error_code
        row.error_message = (outbound.error_message or None) and outbound.error_message[:300]
        row.mode_version = outbound.mode_version
        row.sent_at = outbound.sent_at
        row.updated_at = utcnow()
        await self.session.flush()
        return _outbound(row)

    async def cancel_queued(self, conversation_id: UUID, author_role: str, reason: str) -> int:
        """Queued replies of one author in a dialog. A reply already `sending` cannot be called back."""

        result = await self.session.execute(
            update(OutboundMessageRow)
            .where(
                OutboundMessageRow.conversation_id == conversation_id,
                OutboundMessageRow.author_role == author_role,
                OutboundMessageRow.status == OutboundStatus.queued,
            )
            .values(status=OutboundStatus.cancelled, error_code=reason, updated_at=utcnow())
        )
        return result.rowcount or 0

    async def cancel_queued_for_connection(self, connection_id: UUID, reason: str) -> int:
        result = await self.session.execute(
            update(OutboundMessageRow)
            .where(
                OutboundMessageRow.connection_id == connection_id,
                OutboundMessageRow.status == OutboundStatus.queued,
            )
            .values(status=OutboundStatus.cancelled, error_code=reason, updated_at=utcnow())
        )
        return result.rowcount or 0

    async def by_messages(self, message_ids: list[UUID]) -> dict[UUID, OutboundMessage]:
        if not message_ids:
            return {}
        stmt = select(OutboundMessageRow).where(OutboundMessageRow.message_id.in_(message_ids))
        return {row.message_id: _outbound(row) for row in (await self.session.scalars(stmt)).all()}


class JobQueue:
    """PostgreSQL job table. Claims use SKIP LOCKED; one ordering key runs one job at a time."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def enqueue(
        self,
        *,
        kind: str,
        business_id: UUID,
        ordering_key: str,
        inbound_event_id: UUID | None = None,
        outbound_message_id: UUID | None = None,
        handoff_id: UUID | None = None,
        max_attempts: int = 5,
        run_at: datetime | None = None,
    ) -> int:
        now = utcnow()
        row = JobRow(
            kind=kind,
            business_id=business_id,
            ordering_key=ordering_key[:200],
            inbound_event_id=inbound_event_id,
            outbound_message_id=outbound_message_id,
            handoff_id=handoff_id,
            status=JobStatus.queued,
            attempts=0,
            max_attempts=max_attempts,
            run_at=run_at or now,
            created_at=now,
            updated_at=now,
        )
        self.session.add(row)
        await self.session.flush()
        return row.id

    async def claim(self, worker_id: str, lease_s: float, kinds: list[str] | None = None) -> Job | None:
        """Take the oldest runnable job whose key has no earlier unfinished job.

        A `running` job whose lease ran out is runnable again: its worker died.
        """

        kind_filter = "AND j.kind = ANY(:kinds)" if kinds else ""
        stmt = text(
            f"""
            UPDATE jobs SET status = 'running', attempts = attempts + 1,
                   locked_until = now() + make_interval(secs => :lease),
                   locked_by = :worker, updated_at = now()
            WHERE id = (
                SELECT j.id FROM jobs j
                WHERE ((j.status = 'queued' AND j.run_at <= now())
                       OR (j.status = 'running' AND j.locked_until < now()))
                  {kind_filter}
                  AND NOT EXISTS (
                      SELECT 1 FROM jobs p
                      WHERE p.ordering_key = j.ordering_key AND p.id < j.id
                        AND p.status IN ('queued', 'running')
                  )
                ORDER BY j.id
                LIMIT 1
                FOR UPDATE SKIP LOCKED
            )
            RETURNING id, kind, business_id, ordering_key, status, attempts, max_attempts, run_at,
                      inbound_event_id, outbound_message_id, locked_until, locked_by, last_error, handoff_id
            """
        )
        params = {"lease": float(lease_s), "worker": worker_id[:64]}
        if kinds:
            params["kinds"] = list(kinds)
        row = (await self.session.execute(stmt, params)).mappings().first()
        return Job(**dict(row)) if row else None

    async def complete(self, job: Job, worker_id: str) -> bool:
        return await self._finish(job, worker_id, status=JobStatus.done, error=None)

    async def fail(self, job: Job, worker_id: str, error: str) -> bool:
        return await self._finish(job, worker_id, status=JobStatus.failed, error=error)

    async def retry(self, job: Job, worker_id: str, delay_s: float, error: str) -> bool:
        result = await self.session.execute(
            update(JobRow)
            .where(
                JobRow.id == job.id,
                JobRow.locked_by == worker_id[:64],
                JobRow.attempts == job.attempts,
                JobRow.status == JobStatus.running,
            )
            .values(
                status=JobStatus.queued,
                run_at=utcnow() + timedelta(seconds=max(0.0, delay_s)),
                locked_until=None,
                locked_by=None,
                last_error=error[:300],
                updated_at=utcnow(),
            )
        )
        return (result.rowcount or 0) == 1

    async def _finish(self, job: Job, worker_id: str, *, status: str, error: str | None) -> bool:
        """Close a job only if this worker still owns this attempt; otherwise someone took it over."""

        now = utcnow()
        result = await self.session.execute(
            update(JobRow)
            .where(
                JobRow.id == job.id,
                JobRow.locked_by == worker_id[:64],
                JobRow.attempts == job.attempts,
                JobRow.status == JobStatus.running,
            )
            .values(
                status=status,
                finished_at=now,
                locked_until=None,
                last_error=(error or None) and error[:300],
                updated_at=now,
            )
        )
        return (result.rowcount or 0) == 1

    async def get(self, job_id: int) -> Job | None:
        row = await self.session.get(JobRow, job_id)
        if row is None:
            return None
        return Job(
            id=row.id,
            kind=row.kind,
            business_id=row.business_id,
            ordering_key=row.ordering_key,
            status=row.status,
            attempts=row.attempts,
            max_attempts=row.max_attempts,
            run_at=row.run_at,
            inbound_event_id=row.inbound_event_id,
            outbound_message_id=row.outbound_message_id,
            locked_until=row.locked_until,
            locked_by=row.locked_by,
            last_error=row.last_error,
            handoff_id=row.handoff_id,
        )


class ReadRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def advance(self, operator_id: UUID, conversation_id: UUID, seq: int) -> int:
        """Move the read cursor forward only: a late request cannot mark newer messages unread."""

        stmt = (
            insert(ConversationReadRow)
            .values(operator_id=operator_id, conversation_id=conversation_id, last_read_seq=seq, updated_at=utcnow())
            .on_conflict_do_update(
                index_elements=["operator_id", "conversation_id"],
                set_={
                    "last_read_seq": text("GREATEST(conversation_reads.last_read_seq, excluded.last_read_seq)"),
                    "updated_at": utcnow(),
                },
            )
            .returning(ConversationReadRow.last_read_seq)
        )
        return int((await self.session.execute(stmt)).scalar_one())


def _operator(row: OperatorRow) -> Operator:
    return Operator(
        id=row.id,
        business_id=row.business_id,
        email=row.email,
        display_name=row.display_name or "",
        active=row.active,
        created_at=row.created_at,
    )


def _connection(row: ChannelConnectionRow) -> ChannelConnection:
    return ChannelConnection(
        id=row.id,
        business_id=row.business_id,
        channel=row.channel,
        credential_ref=row.credential_ref,
        external_account_id=row.external_account_id,
        display_name=row.display_name or "",
        username=row.username,
        status=row.status,
        agent_enabled=bool(row.agent_enabled),
        version=row.version or 1,
        created_at=row.created_at,
        updated_at=row.updated_at,
        auth_method=row.auth_method or "server_credential",
        webhook_nonce=row.webhook_nonce,
        last_check_at=row.last_check_at,
        last_check_ok=row.last_check_ok,
        last_event_at=row.last_event_at,
        last_error_code=row.last_error_code,
        last_error_message=row.last_error_message,
        last_error_at=row.last_error_at,
        details=dict(row.details or {}),
        disconnected_at=row.disconnected_at,
    )


def _inbound(row: InboundEventRow) -> InboundEvent:
    return InboundEvent(
        id=row.id,
        business_id=row.business_id,
        connection_id=row.connection_id,
        channel=row.channel,
        external_event_id=row.external_event_id,
        kind=row.kind,
        status=row.status,
        received_at=row.received_at,
        sender_id=row.sender_id,
        provider_message_id=row.provider_message_id,
        text=row.text,
        data=dict(row.data or {}),
        provider_time=row.provider_time,
        processed_at=row.processed_at,
        error_code=row.error_code,
    )


def _outbound(row: OutboundMessageRow) -> OutboundMessage:
    return OutboundMessage(
        id=row.id,
        business_id=row.business_id,
        conversation_id=row.conversation_id,
        connection_id=row.connection_id,
        message_id=row.message_id,
        author_role=row.author_role,
        text=row.text,
        idempotency_key=row.idempotency_key,
        mode_version=row.mode_version,
        status=row.status,
        attempts=row.attempts or 0,
        created_at=row.created_at,
        updated_at=row.updated_at,
        operator_id=row.operator_id,
        parts_sent=row.parts_sent or 0,
        provider_message_ids=list(row.provider_message_ids or []),
        error_code=row.error_code,
        error_message=row.error_message,
        sent_at=row.sent_at,
    )
