"""Manager notification as a queued job (plan 4.1): atomic with the handoff, once, retried, per business."""

from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.container import build_agent
from app.domain.enums import JobKind
from app.domain.errors import ProviderTransientError, ProviderUnavailable
from app.domain.models import InboundMessage
from app.infrastructure.database.channel_repositories import JobQueue
from app.infrastructure.database.models import HandoffRequestRow, JobRow
from app.seed import DEMO_BUSINESS_ID, seed
from app.worker import Worker


class Recorder:
    """Stands in for the Telegram provider. `script`: what each call does, an exception raises it."""

    def __init__(self, script=()):
        self.calls = []
        self.script = list(script)

    async def notify(self, handoff):
        self.calls.append(handoff.id)
        step = self.script.pop(0) if self.script else None
        if step is not None:
            raise step


async def _ask_for_a_manager(session, runtime, user="+996700555201"):
    await seed(session)
    await session.commit()
    agent = build_agent(session, runtime)
    return await agent.process_message(InboundMessage(channel="whatsapp", external_user_id=user, text="Позовите менеджера"))


async def _notify_jobs(session):
    return (await session.scalars(select(JobRow).where(JobRow.kind == JobKind.notify_handoff))).all()


async def _due_now(session):
    await session.execute(text("UPDATE jobs SET run_at = now() - interval '1 second' WHERE status = 'queued'"))
    await session.commit()


async def test_notification_goes_out_once_after_the_commit(session, runtime):
    recorder = runtime.handoff_provider = Recorder()
    response = await _ask_for_a_manager(session, runtime)
    assert response.handoff_required

    # The job exists in this transaction and nobody has been told yet.
    assert len(await _notify_jobs(session)) == 1
    assert recorder.calls == []
    await session.commit()

    assert await Worker(runtime, worker_id="t1").drain() == 1
    assert len(recorder.calls) == 1
    session.expire_all()
    handoff = await session.scalar(select(HandoffRequestRow))
    job = (await _notify_jobs(session))[0]
    assert handoff.notified_at is not None and job.status == "done"


async def test_rolled_back_handoff_notifies_nobody(session, runtime):
    recorder = runtime.handoff_provider = Recorder()
    await _ask_for_a_manager(session, runtime)
    await session.rollback()

    assert await Worker(runtime, worker_id="t1").drain() == 0
    assert recorder.calls == []
    assert await session.scalar(select(func.count()).select_from(HandoffRequestRow)) == 0
    assert await _notify_jobs(session) == []


async def test_redelivered_job_sends_nothing_more(session, runtime):
    recorder = runtime.handoff_provider = Recorder()
    await _ask_for_a_manager(session, runtime)
    await session.commit()
    worker = Worker(runtime, worker_id="t1")
    await worker.drain()
    assert len(recorder.calls) == 1

    # The worker died before it closed the job: the job runs again after its lease.
    await session.execute(text("UPDATE jobs SET status = 'queued', run_at = now() WHERE kind = 'notify_handoff'"))
    await session.commit()
    await worker.drain()
    assert len(recorder.calls) == 1


async def test_one_notification_job_per_handoff(session, runtime):
    await _ask_for_a_manager(session, runtime)
    await session.commit()
    handoff = await session.scalar(select(HandoffRequestRow))
    with pytest.raises(IntegrityError):
        await JobQueue(session).enqueue(
            kind=JobKind.notify_handoff,
            business_id=DEMO_BUSINESS_ID,
            ordering_key="notify:again",
            handoff_id=handoff.id,
        )
        await session.flush()
    await session.rollback()


async def test_telegram_failure_is_retried_until_it_works(session, runtime):
    recorder = runtime.handoff_provider = Recorder([ProviderTransientError("down"), ProviderTransientError("429"), None])
    await _ask_for_a_manager(session, runtime)
    await session.commit()
    worker = Worker(runtime, worker_id="t1")

    for _ in range(3):
        await worker.drain()
        await _due_now(session)
    assert len(recorder.calls) == 3
    session.expire_all()
    assert (await session.scalar(select(HandoffRequestRow))).notified_at is not None
    job = (await _notify_jobs(session))[0]
    assert job.status == "done" and job.attempts == 3


async def test_notification_gives_up_after_the_last_attempt(session, runtime):
    recorder = runtime.handoff_provider = Recorder([ProviderTransientError("down")] * 10)
    await _ask_for_a_manager(session, runtime)
    await session.commit()
    worker = Worker(runtime, worker_id="t1")

    for _ in range(10):
        await worker.drain()
        await _due_now(session)
    job = (await _notify_jobs(session))[0]
    assert job.status == "failed" and job.last_error == "retries_exhausted"
    assert len(recorder.calls) == job.max_attempts
    session.expire_all()
    assert (await session.scalar(select(HandoffRequestRow))).notified_at is None


async def test_refusal_is_not_retried(session, runtime):
    recorder = runtime.handoff_provider = Recorder([ProviderUnavailable("chat not found")])
    await _ask_for_a_manager(session, runtime)
    await session.commit()
    worker = Worker(runtime, worker_id="t1")

    await worker.drain()
    await _due_now(session)
    await worker.drain()
    assert len(recorder.calls) == 1
    assert (await _notify_jobs(session))[0].last_error == "notify_rejected"


async def test_job_of_another_business_notifies_nobody(session, runtime):
    recorder = runtime.handoff_provider = Recorder()
    await _ask_for_a_manager(session, runtime)
    await session.commit()
    from datetime import UTC, datetime

    from app.domain.models import Business
    from app.infrastructure.database.repositories import BusinessRepository

    now = datetime.now(UTC)
    other = await BusinessRepository(session).add(Business(uuid4(), "Other Shop", "", "", {}, "", now, now))
    await session.execute(text("UPDATE jobs SET business_id = :b WHERE kind = 'notify_handoff'"), {"b": other.id})
    await session.commit()

    await Worker(runtime, worker_id="t1").drain()
    assert recorder.calls == []
    assert (await _notify_jobs(session))[0].last_error == "business_mismatch"
