"""Turn one stored channel event into history, an agent turn and a queued reply. Runs in the worker.

Everything happens in one transaction: the customer message, the agent reply,
its actions, the delivery record and the job state commit together. If the
worker dies before commit, nothing of the turn is kept and the job runs again
after its lease. A paid model call made before such a crash is lost and may be
billed twice: deduplication of stored events cannot prevent that.
"""

import logging
import random

from app.domain.enums import ConnectionStatus, InboundStatus
from app.domain.errors import BusinessNotFound, CustomerNotFound, InvalidMessage
from app.domain.models import InboundMessage, Job
from app.application.services.outbound_service import OutboundService
from app.infrastructure.database.channel_repositories import (
    ConnectionRepository,
    InboundEventRepository,
    JobQueue,
    OutboundRepository,
)
from app.infrastructure.database.repositories import ConversationRepository, MessageRepository

logger = logging.getLogger("plumo.inbound")

_PERMANENT = (InvalidMessage, BusinessNotFound, CustomerNotFound)


class InboundProcessor:
    def __init__(self, session_factory, runtime, build_agent) -> None:
        self.session_factory = session_factory
        self.runtime = runtime
        self.build_agent = build_agent

    async def run(self, job: Job, worker_id: str) -> None:
        try:
            async with self.session_factory() as session:
                owned = await self._process(session, job, worker_id)
                if owned:
                    await session.commit()
                else:
                    # The lease ran out and another worker owns the job now; its result wins.
                    await session.rollback()
                    logger.warning("inbound_lost_lease", extra={"job_id": job.id})
        except Exception as exc:  # noqa: BLE001 - every failure must end in retry or a final state
            await self._failed(job, worker_id, exc)

    async def _process(self, session, job: Job, worker_id: str) -> bool:
        events = InboundEventRepository(session)
        jobs = JobQueue(session)
        event = await events.get(job.inbound_event_id) if job.inbound_event_id else None
        if event is None or event.status != InboundStatus.queued:
            return await jobs.complete(job, worker_id)
        connection = await ConnectionRepository(session).get(event.connection_id)
        if connection is None:
            await events.mark(event.id, InboundStatus.ignored, "connection_missing")
            return await jobs.complete(job, worker_id)

        metadata = {"provider": event.channel, "inbound_event_id": str(event.id)}
        if event.provider_time is not None:
            metadata["provider_time"] = event.provider_time.isoformat()
        for key in ("unsupported", "truncated", "has_caption"):
            if key in event.data:
                metadata[key] = event.data[key]
        message = InboundMessage(
            channel=event.channel,
            # Scoped by the bot/account: another account's customer with the same id is someone else.
            external_user_id=f"{connection.external_account_id}:{event.sender_id}",
            text=event.text or "",
            message_id=event.provider_message_id,
            timestamp=event.received_at,
            metadata=metadata,
            business_id=connection.business_id,
            connection_id=connection.id,
            kind=event.kind,
            auto_reply=connection.agent_enabled
            and connection.status in (ConnectionStatus.connected, ConnectionStatus.error),
            reply_to=str(event.data.get("chat_id") or event.sender_id or ""),
            contact_name=event.data.get("contact_name"),
            contact_handle=event.data.get("contact_handle"),
        )
        agent = self.build_agent(session, self.runtime)
        response = await agent.process_message(message)
        conversations = ConversationRepository(session)
        conversation = await conversations.get(response.conversation_id)
        if conversation is not None:
            outbound = OutboundService(
                conversations=conversations,
                messages=MessageRepository(session),
                outbound=OutboundRepository(session),
                connections=ConnectionRepository(session),
                jobs=jobs,
            )
            await outbound.queue_agent_reply(response, conversation, f"agent:{event.id}")
        await events.mark(event.id, InboundStatus.processed)
        return await jobs.complete(job, worker_id)

    async def _failed(self, job: Job, worker_id: str, exc: Exception) -> None:
        permanent = isinstance(exc, _PERMANENT)
        code = getattr(exc, "code", None) or type(exc).__name__
        async with self.session_factory() as session:
            jobs = JobQueue(session)
            if not permanent and job.attempts < job.max_attempts:
                await jobs.retry(job, worker_id, _backoff(job.attempts), str(code))
            else:
                await jobs.fail(job, worker_id, str(code))
                if job.inbound_event_id:
                    await InboundEventRepository(session).mark(job.inbound_event_id, InboundStatus.failed, str(code)[:64])
            await session.commit()
        logger.error(
            "inbound_failed",
            extra={"job_id": job.id, "attempt": job.attempts, "error_type": type(exc).__name__, "permanent": permanent},
            exc_info=not permanent,
        )


def _backoff(attempt: int) -> float:
    base = min(120.0, 5.0 * 2 ** max(0, attempt - 1))
    return base + random.uniform(0, base / 4)
