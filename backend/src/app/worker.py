"""Background worker: processes stored channel events and sends queued replies.

    python -m app.worker              # runs until Ctrl+C
    python -m app.worker --once       # handles what is due now and exits (tests, cron)

Several workers may run at once: jobs are claimed with SKIP LOCKED, one dialog's
jobs run one at a time. A job whose worker died is taken again after its lease.
"""

import argparse
import asyncio
import logging
from datetime import timedelta

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert

from app import release
from app.application.services.delivery_service import DeliveryService
from app.application.services.handoff_notifier import HandoffNotifier
from app.application.services.inbound_processor import InboundProcessor
from app.application.services.leads import send_due
from app.config import Settings, get_settings
from app.container import Runtime, build_agent, build_runtime
from app.domain.enums import InboundStatus, JobKind, OutboundStatus
from app.domain.models import Job, utcnow
from app.infrastructure.database.channel_repositories import InboundEventRepository, JobQueue, OutboundRepository
from app.infrastructure.database.models import HandoffRequestRow, RateWindowRow, WorkerHeartbeatRow
from app.infrastructure.logging.setup import setup_logging

logger = logging.getLogger("plumo.worker")

# Longer than one agent turn (CHAT_TURN_BUDGET_S, 25 s) plus storage, and than one send.
LEASE_S = 120.0
# How often the worker clears expired raw events.
HOUSEKEEPING_S = 3600.0
# Heartbeat for monitoring (/ops/status): three missed beats mean the worker is gone.
HEARTBEAT_S = 15.0
# How often stored website requests are passed on to the team chat.
LEADS_S = 10.0


class Worker:
    def __init__(self, runtime: Runtime, *, worker_id: str | None = None) -> None:
        self.runtime = runtime
        self.worker_id = worker_id or release.worker_id()
        factory = runtime.session_factory
        self.inbound = InboundProcessor(factory, runtime, build_agent)
        self.delivery = DeliveryService(factory, runtime.channel_gateway)
        self.notifier = HandoffNotifier(factory, runtime.handoff_provider)

    async def run_once(self) -> bool:
        """Claim and handle one job. False when nothing is due."""

        async with self.runtime.session_factory() as session:
            job = await JobQueue(session).claim(self.worker_id, LEASE_S)
            await session.commit()
        if job is None:
            return False
        if job.attempts > job.max_attempts:
            await self._give_up(job)
            return True
        if job.kind == JobKind.process_inbound:
            await self.inbound.run(job, self.worker_id)
        elif job.kind == JobKind.verify_telegram:
            from app.application.services.telegram_verification import TelegramVerificationWorker
            await TelegramVerificationWorker(self.runtime.session_factory, self.runtime.channel_gateway).run(job, self.worker_id)
        elif job.kind == JobKind.send_outbound:
            await self.delivery.run(job, self.worker_id)
        elif job.kind == JobKind.notify_handoff:
            await self.notifier.run(job, self.worker_id)
        else:
            async with self.runtime.session_factory() as session:
                await JobQueue(session).fail(job, self.worker_id, f"unknown kind {job.kind}")
                await session.commit()
        return True

    async def drain(self, limit: int = 1000) -> int:
        """Handle due jobs until none is left. For tests and `--once`."""

        handled = 0
        while handled < limit and await self.run_once():
            handled += 1
        return handled

    async def run_forever(self, stop: asyncio.Event, concurrency: int, poll_s: float) -> None:
        async def slot(number: int) -> None:
            while not stop.is_set():
                try:
                    busy = await self.run_once()
                except Exception:  # a broken job must not stop the slot
                    logger.exception("worker_slot_error", extra={"slot": number})
                    busy = False
                if not busy:
                    try:
                        await asyncio.wait_for(stop.wait(), timeout=poll_s)
                    except TimeoutError:
                        pass

        async def housekeeping() -> None:
            while not stop.is_set():
                try:
                    await self.redact_old_events()
                except Exception:
                    logger.exception("housekeeping_failed")
                try:
                    await asyncio.wait_for(stop.wait(), timeout=HOUSEKEEPING_S)
                except TimeoutError:
                    pass

        async def heartbeat() -> None:
            started = utcnow()
            while not stop.is_set():
                try:
                    await self.beat(started)
                except Exception:  # monitoring must not stop the worker; a stale beat shows the problem
                    logger.exception("heartbeat_failed")
                try:
                    await asyncio.wait_for(stop.wait(), timeout=HEARTBEAT_S)
                except TimeoutError:
                    pass

        async def team_leads() -> None:
            while not stop.is_set():
                try:
                    await send_due(self.runtime.session_factory, self.runtime.handoff_provider)
                except Exception:
                    logger.exception("lead_notify_failed")
                try:
                    await asyncio.wait_for(stop.wait(), timeout=LEADS_S)
                except TimeoutError:
                    pass

        logger.info("worker_started", extra={"worker_id": self.worker_id, "concurrency": concurrency})
        await asyncio.gather(heartbeat(), housekeeping(), team_leads(), *(slot(index) for index in range(max(1, concurrency))))
        logger.info("worker_stopped", extra={"worker_id": self.worker_id})

    async def beat(self, started) -> None:
        async with self.runtime.session_factory() as session:
            await session.execute(
                insert(WorkerHeartbeatRow)
                .values(worker_id=self.worker_id[:64], started_at=started, seen_at=utcnow())
                .on_conflict_do_update(index_elements=[WorkerHeartbeatRow.worker_id], set_={"seen_at": utcnow()})
            )
            # Rows of workers gone for a day are history, not workers.
            await session.execute(delete(WorkerHeartbeatRow).where(WorkerHeartbeatRow.seen_at < utcnow() - timedelta(days=1)))
            # Rate windows only matter while they are current; a day of them is plenty for a look back.
            await session.execute(delete(RateWindowRow).where(RateWindowRow.window_start < utcnow() - timedelta(days=1)))
            await session.commit()

    async def redact_old_events(self) -> int:
        """Drop the customer's text and contact data from raw events older than INBOUND_RETENTION_DAYS.

        The dialog history keeps the message; only the webhook copy is cleared.
        Events still queued are left alone.
        """

        days = self.runtime.settings.inbound_retention_days
        if days <= 0:
            return 0
        async with self.runtime.session_factory() as session:
            cleared = await InboundEventRepository(session).redact_older_than(days)
            await session.commit()
        if cleared:
            logger.info("inbound_events_redacted", extra={"events": cleared, "older_than_days": days})
        return cleared

    async def _give_up(self, job: Job) -> None:
        """The job crashed its worker too many times: final state, nothing resent."""

        async with self.runtime.session_factory() as session:
            if job.inbound_event_id:
                await InboundEventRepository(session).mark(job.inbound_event_id, InboundStatus.failed, "worker_crashed")
            if job.outbound_message_id:
                repo = OutboundRepository(session)
                outbound = await repo.lock(job.outbound_message_id)
                if outbound is not None and outbound.status in (OutboundStatus.queued, OutboundStatus.sending):
                    outbound.status = (
                        OutboundStatus.unknown if outbound.status == OutboundStatus.sending else OutboundStatus.failed
                    )
                    outbound.error_code = "worker_crashed"
                    await repo.save(outbound)
            if job.handoff_id:
                # The worker died on this notification again and again; if one of those got as far as Telegram, nobody knows.
                handoff = await session.get(HandoffRequestRow, job.handoff_id, with_for_update=True)
                if handoff is not None and handoff.notify_status in (OutboundStatus.queued, OutboundStatus.sending):
                    handoff.notify_error = "worker_crashed"
                    handoff.notify_status = (
                        OutboundStatus.unknown if handoff.notify_status == OutboundStatus.sending else OutboundStatus.failed
                    )
            await JobQueue(session).fail(job, self.worker_id, "attempts_exhausted")
            await session.commit()
        logger.error("job_given_up", extra={"job_id": job.id, "kind": job.kind})


async def main(settings: Settings, once: bool) -> None:
    setup_logging(settings.log_level)
    runtime = build_runtime(settings)
    worker = Worker(runtime)
    try:
        if once:
            handled = await worker.drain()
            logger.info("worker_drained", extra={"jobs": handled})
            return
        stop = asyncio.Event()
        try:
            await worker.run_forever(stop, settings.worker_concurrency, settings.worker_poll_interval_s)
        except (KeyboardInterrupt, asyncio.CancelledError):
            stop.set()
    finally:
        await runtime.providers.aclose()
        close = getattr(runtime.handoff_provider, "aclose", None)
        if close is not None:
            await close()
        await runtime.engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Plumo channel worker")
    parser.add_argument("--once", action="store_true", help="handle due jobs and exit")
    args = parser.parse_args()
    try:
        asyncio.run(main(get_settings(), args.once))
    except KeyboardInterrupt:
        pass
