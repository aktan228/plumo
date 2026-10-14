"""Send one queued reply through its channel. Runs in the worker.

Three short transactions around the network call:

1. lock the dialog and the delivery, check connection, mode, version and the
   reply window again, mark `sending`, commit;
2. send (long replies of the agent go out in parts; progress is saved per part);
3. record the provider's answer: sent / retry later / failed / unknown.

`sent` means the provider accepted the message and returned its id, not that the
customer read it. A timeout after the request left is `unknown`: nothing is resent
until a person decides (POST /outbound-messages/{id}/resolve). A worker that dies
between 1 and 3 leaves `sending`; the next claim turns it into `unknown`.
"""

import logging
import random

from app.domain.enums import ConnectionStatus, ConversationMode, MessageRole, OutboundStatus
from app.domain.models import Job, utcnow
from app.infrastructure.channels.base import ChannelError, split_for_channel
from app.application.services.outbound_service import INSTAGRAM_WINDOW
from app.infrastructure.database.channel_repositories import ConnectionRepository, JobQueue, OutboundRepository
from app.infrastructure.database.repositories import ConversationRepository, MessageRepository

logger = logging.getLogger("plumo.delivery")


class DeliveryService:
    def __init__(self, session_factory, gateway) -> None:
        self.session_factory = session_factory
        self.gateway = gateway

    async def run(self, job: Job, worker_id: str) -> None:
        plan = await self._start(job, worker_id)
        if plan is None:
            return
        outbound, connection, chat_id = plan
        parts = split_for_channel(connection.channel, outbound.text)
        error: ChannelError | None = None
        for index in range(outbound.parts_sent, len(parts)):
            try:
                provider_id = await self.gateway.send_text(connection, chat_id, parts[index])
            except ChannelError as exc:
                error = exc
                break
            await self._progress(outbound.id, index + 1, provider_id)
        await self._finish(job, worker_id, outbound.id, connection.id, error)

    async def _start(self, job: Job, worker_id: str):
        async with self.session_factory() as session:
            outbound_repo = OutboundRepository(session)
            jobs = JobQueue(session)
            current = await outbound_repo.get(job.outbound_message_id) if job.outbound_message_id else None
            if current is None:
                await jobs.fail(job, worker_id, "outbound_missing")
                await session.commit()
                return None
            conversation = await ConversationRepository(session).lock(current.conversation_id)
            outbound = await outbound_repo.lock(current.id)
            if outbound.status == OutboundStatus.sending:
                # The previous attempt stopped after the request may have left: do not resend.
                outbound.status = OutboundStatus.unknown
                outbound.error_code = "interrupted"
                await outbound_repo.save(outbound)
                await jobs.complete(job, worker_id)
                await session.commit()
                logger.warning("delivery_interrupted", extra={"outbound_id": str(outbound.id)})
                return None
            if outbound.status != OutboundStatus.queued:
                await jobs.complete(job, worker_id)
                await session.commit()
                return None
            connection = (
                await ConnectionRepository(session).get(outbound.connection_id) if outbound.connection_id else None
            )
            verdict = await self._verdict(session, outbound, conversation, connection)
            if verdict is not None:
                status, code = verdict
                outbound.status = status
                outbound.error_code = code
                await outbound_repo.save(outbound)
                await jobs.complete(job, worker_id)
                await session.commit()
                logger.info("delivery_stopped", extra={"outbound_id": str(outbound.id), "status": status, "code": code})
                return None
            outbound.status = OutboundStatus.sending
            outbound.attempts += 1
            outbound = await outbound_repo.save(outbound)
            await session.commit()
            return outbound, connection, conversation.external_chat_id

    async def _verdict(self, session, outbound, conversation, connection) -> tuple[str, str] | None:
        """Why this reply must not go out now, as (final status, code); None when it may."""

        if conversation is None:
            return OutboundStatus.failed, "conversation_missing"
        if connection is None or connection.status == ConnectionStatus.disconnected:
            return OutboundStatus.cancelled, "channel_disconnected"
        if connection.status == ConnectionStatus.action_required:
            return OutboundStatus.failed, "channel_action_required"
        if not conversation.external_chat_id:
            return OutboundStatus.failed, "no_reply_target"
        if outbound.mode_version != conversation.mode_version:
            return OutboundStatus.cancelled, "mode_changed"
        if outbound.author_role == MessageRole.assistant:
            if conversation.mode != ConversationMode.ai:
                return OutboundStatus.cancelled, "mode_changed"
            if not connection.agent_enabled:
                return OutboundStatus.cancelled, "agent_disabled"
        elif conversation.mode != ConversationMode.human:
            return OutboundStatus.cancelled, "mode_changed"
        if conversation.channel == "instagram":
            last = await MessageRepository(session).last_timestamp(conversation.id, MessageRole.user)
            if last is None or utcnow() - last > INSTAGRAM_WINDOW:
                return OutboundStatus.failed, "window_closed"
        return None

    async def _progress(self, outbound_id, parts_sent: int, provider_id: str) -> None:
        async with self.session_factory() as session:
            repo = OutboundRepository(session)
            outbound = await repo.lock(outbound_id)
            outbound.parts_sent = parts_sent
            outbound.provider_message_ids = [*outbound.provider_message_ids, provider_id]
            await repo.save(outbound)
            await session.commit()

    async def _finish(self, job: Job, worker_id: str, outbound_id, connection_id, error: ChannelError | None) -> None:
        async with self.session_factory() as session:
            repo = OutboundRepository(session)
            jobs = JobQueue(session)
            outbound = await repo.lock(outbound_id)
            now = utcnow()
            if error is None:
                outbound.status = OutboundStatus.sent
                outbound.sent_at = now
                outbound.error_code = None
                outbound.error_message = None
                await repo.save(outbound)
                await jobs.complete(job, worker_id)
                await session.commit()
                return
            outbound.error_code = error.code
            outbound.error_message = error.message
            retry_delay = None
            if error.kind == "ambiguous":
                outbound.status = OutboundStatus.unknown
            elif error.retryable and job.attempts < job.max_attempts:
                outbound.status = OutboundStatus.queued
                retry_delay = error.retry_after if error.retry_after is not None else _backoff(job.attempts)
            else:
                outbound.status = OutboundStatus.failed
                if error.retryable:
                    outbound.error_code = "retries_exhausted"
            await repo.save(outbound)
            if error.needs_action:
                await _mark_connection(session, connection_id, error)
            if retry_delay is not None:
                await jobs.retry(job, worker_id, retry_delay, error.code)
            else:
                await jobs.complete(job, worker_id)
            await session.commit()
            logger.warning(
                "delivery_failed",
                extra={
                    "outbound_id": str(outbound.id),
                    "status": outbound.status,
                    "code": error.code,
                    "kind": error.kind,
                    "retry_in_s": retry_delay,
                },
            )


async def _mark_connection(session, connection_id, error: ChannelError) -> None:
    connections = ConnectionRepository(session)
    connection = await connections.lock(connection_id)
    if connection is None or connection.status == ConnectionStatus.disconnected:
        return
    now = utcnow()
    connection.status = ConnectionStatus.action_required
    connection.last_check_ok = False
    connection.last_error_code = error.code
    connection.last_error_message = error.describe()
    connection.last_error_at = now
    connection.version += 1
    await connections.save(connection)


def _backoff(attempt: int) -> float:
    """2, 4, 8... seconds, capped at a minute, with jitter so retries do not line up."""

    base = min(60.0, 2.0 ** max(1, attempt))
    return base + random.uniform(0, base / 4)
