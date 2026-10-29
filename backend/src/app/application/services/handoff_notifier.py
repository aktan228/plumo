"""Sends the manager notification of a handoff from a `notify_handoff` job.

The job was queued in the transaction that stored the handoff, so a handoff that rolled
back never reaches the manager. The handoff carries the notification's state, the same
states as a delivery:

    queued -> sending -> sent          Telegram accepted it (not: the manager read it)
                      -> queued        network error before sending, 429, 5xx: retried with a limit
                      -> failed        refused for good (chat gone, bot blocked) or retries exhausted
                      -> unknown       sent but no answer, or the worker died mid-send
    queued -> cancelled                the business has no confirmed recipient

`sending` is committed before the call to Telegram. A job taken again after its lease
(worker restarted) that finds `sending` cannot know whether Telegram got it: it records
`unknown` and sends nothing; a person decides in the dashboard. Exactly-once is not
promised: the only double is a person choosing to resend.

The chat is the business's confirmed recipient, read when the job runs: a recipient
changed or disconnected while the job waited gets nothing, and a business without one
is told so (`recipient_not_configured`) instead of falling back to a shared chat.
"""

import logging
from collections.abc import Callable

from sqlalchemy import select

from app.application.services.delivery_service import _backoff
from app.application.services.manager_recipients import ManagerRecipients
from app.domain.enums import OutboundStatus
from app.domain.errors import DeliveryUnknown, HandoffNotFound, InvalidState, ProviderTransientError, ProviderUnavailable
from app.domain.models import Job, utcnow
from app.domain.ports import HumanHandoffProvider
from app.infrastructure.database.channel_repositories import JobQueue
from app.infrastructure.database.models import ConversationRow, HandoffRequestRow
from app.infrastructure.database.repositories import HandoffRepository

logger = logging.getLogger("plumo.handoff")

# Decided states: a redelivered job leaves them alone.
_FINAL = (OutboundStatus.sent, OutboundStatus.failed, OutboundStatus.unknown, OutboundStatus.cancelled)


class HandoffNotifier:
    def __init__(self, session_factory: Callable, provider: HumanHandoffProvider) -> None:
        self.session_factory = session_factory
        self.provider = provider

    async def run(self, job: Job, worker_id: str) -> None:
        async with self.session_factory() as session:
            jobs = JobQueue(session)
            handoff = await _lock(session, job.handoff_id) if job.handoff_id else None
            conversation = await session.get(ConversationRow, handoff.conversation_id) if handoff else None
            if handoff is None or conversation is None:
                await _close(jobs, job, worker_id, "handoff_not_found")
                await session.commit()
                return
            if conversation.business_id != job.business_id:
                # A job never notifies about another business's dialog.
                logger.error("handoff_notify_business_mismatch", extra={"job_id": job.id, "handoff_id": str(handoff.id)})
                await _close(jobs, job, worker_id, "business_mismatch")
                await session.commit()
                return
            if handoff.notified_at is not None or handoff.notify_status in _FINAL:
                await _close(jobs, job, worker_id, None)
                await session.commit()
                return
            if handoff.notify_status == OutboundStatus.sending:
                # The previous attempt died between "sending" and the answer: Telegram may have it.
                _state(handoff, OutboundStatus.unknown, "worker_stopped_mid_send")
                await _close(jobs, job, worker_id, "delivery_unknown")
                await session.commit()
                logger.error("handoff_notify_unknown", extra={"handoff_id": str(handoff.id)})
                return
            chat_id = await ManagerRecipients(session).chat_for(job.business_id)
            if chat_id is None:
                _state(handoff, OutboundStatus.cancelled, "recipient_not_configured")
                await _close(jobs, job, worker_id, "recipient_not_configured")
                await session.commit()
                logger.warning("handoff_notify_no_recipient", extra={"handoff_id": str(handoff.id)})
                return
            _state(handoff, OutboundStatus.sending, None)
            handoff.notify_attempted_at = utcnow()
            domain = await HandoffRepository(session).get(handoff.id)
            await session.commit()

        try:
            await self.provider.notify(domain, chat_id)
        except DeliveryUnknown:
            await self._finish(job, worker_id, OutboundStatus.unknown, "no_answer", job_error="delivery_unknown")
            logger.error("handoff_notify_unknown", extra={"handoff_id": str(domain.id)})
        except ProviderTransientError as exc:
            await self._retry_or_fail(job, worker_id, str(exc), exc.retry_after)
        except ProviderUnavailable as exc:
            # Chat gone, bot blocked, revoked token: another attempt will not help, someone has to look.
            logger.error("handoff_notify_rejected", extra={"handoff_id": str(domain.id), "error": str(exc)[:200]})
            await self._finish(
                job, worker_id, OutboundStatus.failed, "notify_rejected", job_error="notify_rejected",
                recipient=(chat_id, "delivery_rejected"),
            )
        except Exception as exc:
            logger.exception("handoff_notify_failed", extra={"handoff_id": str(domain.id)})
            await self._retry_or_fail(job, worker_id, type(exc).__name__, None)
        else:
            await self._finish(job, worker_id, OutboundStatus.sent, None, recipient=(chat_id, None))

    async def _finish(
        self, job: Job, worker_id: str, status: str, error: str | None, *, job_error: str | None = None, recipient=None
    ) -> None:
        async with self.session_factory() as session:
            handoff = await _lock(session, job.handoff_id)
            if handoff is not None and handoff.notify_status == OutboundStatus.sending:
                _state(handoff, status, error)
                if status == OutboundStatus.sent:
                    handoff.notified_at = handoff.notified_at or utcnow()
            if recipient is not None:
                await ManagerRecipients(session).mark(job.business_id, *recipient)
            await _close(JobQueue(session), job, worker_id, job_error)
            await session.commit()

    async def _retry_or_fail(self, job: Job, worker_id: str, error: str, retry_after: float | None) -> None:
        if job.attempts >= job.max_attempts:
            await self._finish(job, worker_id, OutboundStatus.failed, "retries_exhausted", job_error="retries_exhausted")
            logger.error("handoff_notify_gave_up", extra={"handoff_id": str(job.handoff_id), "attempts": job.attempts})
            return
        # Telegram's retry_after wins over our backoff when it asks for longer.
        delay = max(_backoff(job.attempts), retry_after or 0.0)
        async with self.session_factory() as session:
            handoff = await _lock(session, job.handoff_id)
            if handoff is not None and handoff.notify_status == OutboundStatus.sending:
                _state(handoff, OutboundStatus.queued, error[:64])
            await JobQueue(session).retry(job, worker_id, delay, error[:200])
            await session.commit()
        logger.warning(
            "handoff_notify_retry",
            extra={"handoff_id": str(job.handoff_id), "attempt": job.attempts, "retry_in_s": round(delay, 1)},
        )


async def _lock(session, handoff_id) -> HandoffRequestRow | None:
    return await session.scalar(
        select(HandoffRequestRow)
        .where(HandoffRequestRow.id == handoff_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


async def _close(jobs: JobQueue, job: Job, worker_id: str, error: str | None) -> None:
    if error:
        await jobs.fail(job, worker_id, error)
    else:
        await jobs.complete(job, worker_id)


def _state(row: HandoffRequestRow, status: str, error: str | None) -> None:
    row.notify_status = status
    row.notify_error = error
    row.updated_at = utcnow()


async def resolve_notification(session, handoff_id, business_id, action: str) -> HandoffRequestRow:
    """A person's decision on a failed or unknown notification, for their own business only.

    retry: send again (the person accepts a possible double for `unknown`);
    mark_sent: the manager confirmed they got it; mark_failed: give up.
    """

    handoff = await _lock(session, handoff_id)
    conversation = await session.get(ConversationRow, handoff.conversation_id) if handoff else None
    if handoff is None or conversation is None or conversation.business_id != business_id:
        raise HandoffNotFound(f"handoff {handoff_id} was not found")
    if handoff.notify_status not in (OutboundStatus.failed, OutboundStatus.unknown, OutboundStatus.cancelled):
        raise InvalidState(f"notification is {handoff.notify_status}; nothing to resolve", code="delivery_not_resolvable")
    if action == "mark_sent":
        if handoff.notify_status != OutboundStatus.unknown:
            raise InvalidState("only an unknown notification can be marked as sent", code="delivery_not_resolvable")
        _state(handoff, OutboundStatus.sent, "confirmed_by_operator")
        handoff.notified_at = handoff.notified_at or utcnow()
    elif action == "mark_failed":
        _state(handoff, OutboundStatus.failed, handoff.notify_error or "marked_failed")
    else:
        if await ManagerRecipients(session).chat_for(business_id) is None:
            raise InvalidState("Set up manager notifications first.", code="recipient_not_configured")
        if not await JobQueue(session).requeue_notification(handoff.id):
            raise InvalidState("the notification is still being handled", code="delivery_not_resolvable")
        _state(handoff, OutboundStatus.queued, None)
    await session.flush()
    return handoff
