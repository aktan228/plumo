"""Sends the manager notification of a handoff from a `notify_handoff` job.

The job was queued in the transaction that stored the handoff, so a handoff that rolled
back never reaches the manager. The send runs outside any transaction. `notified_at` is
set once the provider accepted the message. The scoped Telegram path records a send
marker before the network call; a crash before its result is committed becomes unknown
and requires manual resolution. A generation fences late results of an older attempt.
"""

import logging
from collections.abc import Callable
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert

from app.application.services.delivery_service import _backoff
from app.domain.errors import ProviderDeliveryUnknown, ProviderTransientError, ProviderUnavailable
from app.domain.models import Job, utcnow
from app.domain.ports import HumanHandoffProvider
from app.infrastructure.database.channel_repositories import JobQueue
from app.infrastructure.database.repositories import ConversationRepository, HandoffRepository
from app.infrastructure.database.models import JobRow, ManagerRecipientRow, ManagerNotificationRow

logger = logging.getLogger("plumo.handoff")


class LegacyHandoffNotifier:
    def __init__(self, session_factory: Callable, provider: HumanHandoffProvider) -> None:
        self.session_factory = session_factory
        self.provider = provider

    async def run(self, job: Job, worker_id: str) -> None:
        async with self.session_factory() as session:
            handoff = await HandoffRepository(session).get(job.handoff_id) if job.handoff_id else None
            conversation = await ConversationRepository(session).get(handoff.conversation_id) if handoff else None
        if handoff is None or conversation is None:
            await self._close(job, worker_id, failed="handoff_not_found")
            return
        if conversation.business_id != job.business_id:
            # A job never notifies about another business's dialog.
            logger.error("handoff_notify_business_mismatch", extra={"job_id": job.id, "handoff_id": str(handoff.id)})
            await self._close(job, worker_id, failed="business_mismatch")
            return
        if handoff.notified_at is not None:
            await self._close(job, worker_id)
            return
        scoped = callable(getattr(self.provider, "notify_to", None))
        recipient = generation = None
        if scoped:
            recipient, state, generation = await self._prepare(job, worker_id)
            if state == "sent":
                await self._close(job, worker_id, notified=handoff.id)
                return
            if state != "sending":
                await self._close(job, worker_id, failed=state)
                return
        try:
            if scoped:
                await self.provider.notify_to(handoff, recipient)
            else:
                await self.provider.notify(handoff)
        except ProviderDeliveryUnknown:
            if scoped:
                await self._attempt(job, "unknown", generation)
            await self._close(job, worker_id, failed="notify_unknown")
            return
        except ProviderTransientError as exc:
            if scoped:
                await self._attempt(job, "retryable" if job.attempts < job.max_attempts else "failed", generation)
            await self._retry_or_fail(job, worker_id, str(exc), handoff.id)
            return
        except ProviderUnavailable as exc:
            if scoped:
                await self._attempt(job, "failed", generation)
            # Wrong chat id, revoked token: another attempt will not help, someone has to look.
            logger.error("handoff_notify_rejected", extra={"handoff_id": str(handoff.id), "error": str(exc)[:200]})
            await self._close(job, worker_id, failed="notify_rejected")
            return
        except Exception as exc:
            if scoped:
                await self._attempt(job, "unknown", generation)
                await self._close(job, worker_id, failed="notify_unknown")
                return
            logger.exception("handoff_notify_failed", extra={"handoff_id": str(handoff.id)})
            await self._retry_or_fail(job, worker_id, type(exc).__name__, handoff.id)
            return
        if not scoped or await self._attempt(job, "sent", generation):
            await self._close(job, worker_id, notified=handoff.id)

    async def _prepare(self, job, worker_id):
        async with self.session_factory() as session:
            owned = await session.scalar(select(JobRow).where(
                JobRow.id == job.id, JobRow.business_id == job.business_id,
                JobRow.status == "running", JobRow.locked_by == worker_id,
                JobRow.locked_until > utcnow(),
            ).with_for_update())
            if owned is None:
                return None, "lease_lost", None
            previous = await session.scalar(select(ManagerNotificationRow).where(
                ManagerNotificationRow.handoff_id == job.handoff_id
            ).with_for_update())
            if previous and previous.business_id != job.business_id:
                return None, "business_mismatch", None
            if previous and previous.state == "sent":
                return None, "sent", previous.generation
            if previous and previous.state == "sending":
                previous.state, previous.updated_at = "unknown", utcnow()
                await session.commit()
                return None, "notify_unknown", previous.generation
            if previous and previous.state in ("unknown", "failed"):
                return None, "notify_unknown" if previous.state == "unknown" else "notify_rejected", previous.generation
            recipient = await session.get(ManagerRecipientRow, job.business_id)
            if not recipient or not recipient.chat_id:
                return None, "notify_recipient_missing", None
            await session.execute(insert(ManagerNotificationRow).values(
                handoff_id=job.handoff_id, business_id=job.business_id,
                recipient_version=recipient.version, state="retryable",
            ).on_conflict_do_nothing())
            attempt = await session.scalar(select(ManagerNotificationRow).where(
                ManagerNotificationRow.handoff_id == job.handoff_id
            ).with_for_update().execution_options(populate_existing=True))
            if attempt.business_id != job.business_id:
                return None, "business_mismatch", None
            if attempt.state == "sending":
                attempt.state = "unknown"
                attempt.updated_at = utcnow()
                await session.commit()
                return None, "notify_unknown", attempt.generation
            if attempt.state != "retryable":
                return None, "sent" if attempt.state == "sent" else "notify_unknown" if attempt.state == "unknown" else "notify_rejected", attempt.generation
            attempt.state, attempt.recipient_version = "sending", recipient.version
            attempt.generation += 1
            attempt.updated_at = utcnow()
            chat_id = recipient.chat_id
            generation = attempt.generation
            await session.commit()  # Durable send marker before network; no transaction spans the call.
            return chat_id, "sending", generation

    async def _attempt(self, job, state, generation):
        async with self.session_factory() as session:
            result = await session.execute(update(ManagerNotificationRow).where(
                ManagerNotificationRow.handoff_id == job.handoff_id,
                ManagerNotificationRow.business_id == job.business_id,
                ManagerNotificationRow.state == "sending",
                ManagerNotificationRow.generation == generation,
            ).values(state=state, updated_at=utcnow()))
            await session.commit()
            return bool(result.rowcount)

    async def _close(self, job: Job, worker_id: str, *, failed: str | None = None, notified=None) -> None:
        async with self.session_factory() as session:
            jobs = JobQueue(session)
            closed = await jobs.fail(job, worker_id, failed) if failed else await jobs.complete(job, worker_id)
            if not closed:
                await session.rollback()
                return
            if notified is not None:
                repo = HandoffRepository(session)
                current = await repo.get(notified)
                if current is not None and current.notified_at is None:
                    current.notified_at = utcnow()
                    await repo.save(current)
            await session.commit()

    async def _retry_or_fail(self, job: Job, worker_id: str, error: str, handoff_id) -> None:
        async with self.session_factory() as session:
            jobs = JobQueue(session)
            if job.attempts < job.max_attempts:
                delay = _backoff(job.attempts)
                await jobs.retry(job, worker_id, delay, error[:200])
                logger.warning(
                    "handoff_notify_retry",
                    extra={"handoff_id": str(handoff_id), "attempt": job.attempts, "retry_in_s": round(delay, 1)},
                )
            else:
                await jobs.fail(job, worker_id, "retries_exhausted")
                logger.error("handoff_notify_gave_up", extra={"handoff_id": str(handoff_id), "attempts": job.attempts})
            await session.commit()
