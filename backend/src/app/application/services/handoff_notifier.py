"""Sends the manager notification of a handoff from a `notify_handoff` job.

The job was queued in the transaction that stored the handoff, so a handoff that rolled
back never reaches the manager. The send runs outside any transaction. `notified_at` is
set once the provider accepted the message: a job taken again (lease ran out, worker
restarted) finds it and sends nothing. Only a crash between the provider's answer and
that commit can notify twice; no transport can close that window.
"""

import logging
from collections.abc import Callable

from app.application.services.delivery_service import _backoff
from app.domain.errors import ProviderTransientError, ProviderUnavailable
from app.domain.models import Job, utcnow
from app.domain.ports import HumanHandoffProvider
from app.infrastructure.database.channel_repositories import JobQueue
from app.infrastructure.database.repositories import ConversationRepository, HandoffRepository

logger = logging.getLogger("plumo.handoff")


class HandoffNotifier:
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
        try:
            await self.provider.notify(handoff)
        except ProviderTransientError as exc:
            await self._retry_or_fail(job, worker_id, str(exc), handoff.id)
            return
        except ProviderUnavailable as exc:
            # Wrong chat id, revoked token: another attempt will not help, someone has to look.
            logger.error("handoff_notify_rejected", extra={"handoff_id": str(handoff.id), "error": str(exc)[:200]})
            await self._close(job, worker_id, failed="notify_rejected")
            return
        except Exception as exc:
            logger.exception("handoff_notify_failed", extra={"handoff_id": str(handoff.id)})
            await self._retry_or_fail(job, worker_id, type(exc).__name__, handoff.id)
            return
        await self._close(job, worker_id, notified=handoff.id)

    async def _close(self, job: Job, worker_id: str, *, failed: str | None = None, notified=None) -> None:
        async with self.session_factory() as session:
            if notified is not None:
                repo = HandoffRepository(session)
                current = await repo.get(notified)
                if current is not None and current.notified_at is None:
                    current.notified_at = utcnow()
                    await repo.save(current)
            jobs = JobQueue(session)
            if failed:
                await jobs.fail(job, worker_id, failed)
            else:
                await jobs.complete(job, worker_id)
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
