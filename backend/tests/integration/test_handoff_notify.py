"""Manager notification as a queued job (plan 4.1): atomic with the handoff, once, retried, per business."""

from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.container import build_agent
from app.domain.enums import JobKind
from app.domain.errors import DeliveryUnknown, ProviderTransientError, ProviderUnavailable
from app.domain.models import InboundMessage
from app.infrastructure.database.channel_repositories import JobQueue
from app.infrastructure.database.models import HandoffRequestRow, JobRow, ManagerRecipientRow
from app.seed import DEMO_BUSINESS_ID, seed
from app.worker import Worker


class Recorder:
    """Stands in for the Telegram provider. `script`: what each call does, an exception raises it."""

    def __init__(self, script=()):
        self.calls = []
        self.chats = []
        self.script = list(script)

    async def notify(self, handoff, chat_id):
        self.calls.append(handoff.id)
        self.chats.append(chat_id)
        step = self.script.pop(0) if self.script else None
        if step is not None:
            raise step


async def _ask_for_a_manager(session, runtime, user="+996700555201"):
    await seed(session)
    # The demo business has a confirmed manager chat; tests without one are in test_manager_recipients.py.
    session.add(ManagerRecipientRow(business_id=DEMO_BUSINESS_ID, chat_id="4242", chat_label="Менеджер"))
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
    assert len(recorder.calls) == 1 and recorder.chats == ["4242"]
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


async def _handoff_row(session):
    session.expire_all()
    return await session.scalar(select(HandoffRequestRow))


async def test_notification_state_follows_the_job(session, runtime):
    runtime.handoff_provider = Recorder()
    await _ask_for_a_manager(session, runtime)
    assert (await _handoff_row(session)).notify_status == "queued"
    await session.commit()

    await Worker(runtime, worker_id="t1").drain()
    handoff = await _handoff_row(session)
    assert handoff.notify_status == "sent" and handoff.notify_attempted_at is not None


async def test_rate_limit_waits_as_long_as_telegram_asks(session, runtime):
    runtime.handoff_provider = Recorder([ProviderTransientError("429", retry_after=120)])
    await _ask_for_a_manager(session, runtime)
    await session.commit()

    await Worker(runtime, worker_id="t1").drain()
    handoff = await _handoff_row(session)
    job = (await _notify_jobs(session))[0]
    assert job.status == "queued" and handoff.notify_status == "queued"
    waited = (job.run_at - handoff.notify_attempted_at).total_seconds()
    assert waited >= 119


async def test_no_answer_after_sending_is_unknown_and_not_repeated(session, runtime):
    recorder = runtime.handoff_provider = Recorder([DeliveryUnknown("read timeout")])
    await _ask_for_a_manager(session, runtime)
    await session.commit()
    worker = Worker(runtime, worker_id="t1")

    await worker.drain()
    await _due_now(session)
    await worker.drain()
    assert len(recorder.calls) == 1
    assert (await _handoff_row(session)).notify_status == "unknown"
    assert (await _notify_jobs(session))[0].last_error == "delivery_unknown"


async def test_worker_that_died_mid_send_leaves_unknown_not_a_second_send(session, runtime):
    recorder = runtime.handoff_provider = Recorder()
    await _ask_for_a_manager(session, runtime)
    await session.commit()
    # The previous worker wrote "sending", called Telegram and died; its lease ran out.
    await session.execute(text("UPDATE handoff_requests SET notify_status = 'sending'"))
    await session.execute(
        text("UPDATE jobs SET status = 'running', attempts = 1, locked_until = now() - interval '1 second' WHERE kind = 'notify_handoff'")
    )
    await session.commit()

    await Worker(runtime, worker_id="t2").drain()
    assert recorder.calls == []
    handoff = await _handoff_row(session)
    assert (handoff.notify_status, handoff.notify_error) == ("unknown", "worker_stopped_mid_send")


async def test_stopped_worker_loses_no_notification(session, runtime):
    """Handoff created while no worker runs: the job waits in the table and goes out when one starts."""

    recorder = runtime.handoff_provider = Recorder()
    await _ask_for_a_manager(session, runtime)
    await session.commit()
    assert recorder.calls == [] and (await _handoff_row(session)).notify_status == "queued"

    await Worker(runtime, worker_id="started-later").drain()
    assert len(recorder.calls) == 1


async def test_person_resolves_an_unknown_notification(client, runtime):
    from app.domain.errors import DeliveryUnknown as Unknown

    application_runtime = client._transport.app.state.runtime
    recorder = application_runtime.handoff_provider = Recorder([Unknown("timeout")])
    factory = application_runtime.session_factory
    async with factory() as session:
        session.add(ManagerRecipientRow(business_id=DEMO_BUSINESS_ID, chat_id="4242", chat_label="Менеджер"))
        await session.commit()
    response = await client.post(
        "/api/v1/messages", json={"channel": "whatsapp", "external_user_id": "+996700555299", "text": "Позовите менеджера"}
    )
    assert response.json()["handoff_required"]
    worker = Worker(application_runtime, worker_id="t1")
    await worker.drain()
    handoff = (await client.get("/api/v1/handoffs")).json()[0]
    assert handoff["notify_status"] == "unknown"

    # Nothing to decide about a sent one; a person picks retry for the unknown one.
    resolve = f"/api/v1/handoffs/{handoff['id']}/notification/resolve"
    retried = await client.post(resolve, json={"action": "retry"})
    assert retried.status_code == 200 and retried.json()["notify_status"] == "queued"
    await worker.drain()
    assert len(recorder.calls) == 2
    after = (await client.get("/api/v1/handoffs")).json()[0]
    assert after["notify_status"] == "sent" and after["notified_at"]
    again = await client.post(resolve, json={"action": "mark_sent"})
    assert again.status_code == 409 and again.json()["code"] == "delivery_not_resolvable"


async def test_another_business_cannot_resolve_this_notification(stand):
    stand.runtime.handoff_provider = Recorder([DeliveryUnknown("timeout")])
    async with stand.factory() as session:
        session.add(ManagerRecipientRow(business_id=stand.business.id, chat_id="4242", chat_label="Менеджер"))
        agent = build_agent(session, stand.runtime)
        await agent.process_message(InboundMessage(channel="whatsapp", external_user_id="+996700555300", text="Позовите менеджера", business_id=stand.business.id))
        await session.commit()
    await Worker(stand.runtime, worker_id="t1").drain()
    handoff_id = (await stand.client.get("/api/v1/handoffs")).json()[0]["id"]

    other = {"Authorization": f"Bearer {stand.tokens['other']}"}
    response = await stand.client.post(f"/api/v1/handoffs/{handoff_id}/notification/resolve", json={"action": "mark_sent"}, headers=other)
    assert response.status_code == 404
    own = await stand.client.post(f"/api/v1/handoffs/{handoff_id}/notification/resolve", json={"action": "mark_sent"})
    assert own.status_code == 200 and own.json()["notify_status"] == "sent"
