"""Turn one stored channel event into history, an agent turn and a queued reply. Runs in the worker.

Everything happens in one transaction: the customer message, the agent reply,
its actions, the delivery record and the job state commit together. If the
worker dies before commit, nothing of the turn is kept and the job runs again
after its lease. A paid model call made before such a crash is lost and may be
billed twice: deduplication of stored events cannot prevent that.

A voice message is the exception: its transcript is saved on the event in a transaction
of its own right after the paid transcription, so a retry reuses it (voice_messages.py).
"""

import logging
import random
from datetime import timedelta

from app.domain.enums import ConnectionStatus, InboundKind, InboundStatus, VoiceNotice
from app.domain.errors import BusinessNotFound, CustomerNotFound, InvalidMessage
from app.domain.models import InboundMessage, Job
from app.application.services.outbound_service import OutboundService
from app.application.services.spend_limits import RATE_REASONS, Allowance, SpendLimits
from app.application.services.voice_messages import VoiceTranscriber, stt_estimate_usd, too_long
from app.infrastructure.database.channel_repositories import (
    ConnectionRepository,
    InboundEventRepository,
    JobQueue,
    OutboundRepository,
)
from app.infrastructure.database.repositories import ConversationRepository, MessageRepository

logger = logging.getLogger("plumo.inbound")

_PERMANENT = (InvalidMessage, BusinessNotFound, CustomerNotFound)
# Deferred turns start up to this many seconds into the next window, not all in its first instant.
_DEFER_SPREAD_S = 5.0


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
        # Turns that may call a paid model: text, and a voice message that will be transcribed.
        paid = event.kind == InboundKind.text
        stt = None
        if event.kind == InboundKind.voice:
            stt = self._voice_setup(event, message)
            paid = stt is not None
        if paid:
            extra = stt_estimate_usd(event, self.runtime.settings) if stt is not None else 0.0
            refused = await self._limit(session, event, connection.business_id, extra)
            if refused is not None and refused.reason in RATE_REASONS and refused.retry_at is not None:
                # A full short window: the turn runs in the next one. Nothing is stored or
                # sent yet, and later messages of this customer keep waiting behind it.
                run_at = refused.retry_at + timedelta(seconds=random.uniform(0, _DEFER_SPREAD_S))
                logger.warning(
                    "turn_deferred",
                    extra={"reason": refused.reason, "business_id": str(connection.business_id), "job_id": job.id},
                )
                return await jobs.defer(job, worker_id, run_at, refused.reason)
            message.limit_reason = refused.reason if refused is not None else None
            if message.limit_reason and stt is not None:
                # Over a budget: not transcribed, the manager sees "not recognized".
                message.metadata["voice_status"] = "limit"
        stt_cost = 0.0
        if stt is not None and not message.limit_reason:
            # Nothing is written yet; no transaction stays open while the audio downloads.
            await session.commit()
            stt_cost = await self._transcribe(event, connection, message, stt, job)
        agent = self.build_agent(session, self.runtime)
        response = await agent.process_message(message, checkpoint=session.commit)
        if paid and not message.limit_reason:
            await SpendLimits(session, self.runtime.settings).settle(event.id, response.usage.estimated_cost + stt_cost)
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

    def _voice_setup(self, event, message: InboundMessage):
        """The STT to use, or None when the voice message gets a fixed line without one.

        Voice off, mock mode, or no real provider: the "text only" line, as before voice support.
        """

        settings = self.runtime.settings
        duration = event.data.get("duration")
        message.metadata["voice"] = True
        if isinstance(duration, int):
            message.metadata["voice_duration_s"] = duration
        stt = self.runtime.providers.voice_message_stt()
        if stt is None:
            message.kind = InboundKind.unsupported
            message.metadata["unsupported"] = "voice"
            message.metadata["voice_status"] = "off"
            return None
        if too_long(event, settings.voice_max_duration_s):
            message.kind = VoiceNotice.too_long
            message.metadata["voice_status"] = "too_long"
            message.metadata["voice_limit_s"] = settings.voice_max_duration_s
            return None
        return stt

    async def _transcribe(self, event, connection, message: InboundMessage, stt, job: Job) -> float:
        """Fill the message from the voice message. Returns the transcription cost to settle."""

        name, provider = stt
        outcome = await VoiceTranscriber(self.session_factory, self.runtime.channel_gateway, self.runtime.settings).transcribe(
            event, connection, name, provider, last_attempt=job.attempts >= job.max_attempts
        )
        message.metadata["stt_provider"] = name
        if outcome.language in ("ru", "ky"):
            message.language_hint = outcome.language
        if outcome.kind == InboundKind.text:
            message.text = outcome.text or ""
            message.metadata["voice_status"] = "transcribed"
            if outcome.confidence is not None:
                message.metadata["stt_confidence"] = round(outcome.confidence, 3)
        else:
            message.kind = outcome.kind
            message.metadata["voice_status"] = "unclear" if outcome.kind == VoiceNotice.unclear else "failed"
            if outcome.error_code:
                message.metadata["stt_error"] = outcome.error_code
        return outcome.cost_usd

    async def _limit(self, session, event, business_id, extra_usd: float = 0.0) -> Allowance | None:
        """Why this turn may not call a paid model now, or None. The reservation commits on its own."""

        limits = SpendLimits(session, self.runtime.settings)
        if await limits.sender_over_rate(event):
            return Allowance(False, "sender_rate_limit")
        async with self.session_factory() as own:
            allowance = await SpendLimits(own, self.runtime.settings).reserve(event.id, business_id, extra_usd)
            if allowance.ok:
                await own.commit()
            else:
                await own.rollback()
        if allowance.ok:
            return None
        if allowance.reason not in RATE_REASONS:
            logger.warning("turn_over_limit", extra={"reason": allowance.reason, "business_id": str(business_id)})
        return allowance

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
