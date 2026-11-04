"""The two manager APIs share one recipient; canonical retries keep the dashboard fence."""
from sqlalchemy import select

from test_onboarding import wizard as wizard
from test_handoff_notify import Recorder, _ask_for_a_manager
from app.application.services.handoff_notifier import HandoffNotifier
from app.infrastructure.database.models import HandoffRequestRow, JobRow, ManagerRecipientRow
from app.infrastructure.database.channel_repositories import JobQueue


async def test_both_manager_apis_share_recipient_and_disconnect_version(wizard):
    async with wizard.factory() as session:
        session.add(ManagerRecipientRow(business_id=wizard.ids[0], chat_id="101", chat_label="Shared manager", version=4))
        await session.commit()
    legacy = (await wizard.http.get("/api/v1/manager-recipient")).json()
    canonical = (await wizard.http.get("/api/v1/manager-notifications")).json()
    assert legacy["recipient"]["name"] == canonical["recipient"]["label"] == "Shared manager"
    result = await wizard.http.post("/api/v1/manager-notifications/disconnect")
    assert result.status_code == 200
    after = (await wizard.http.get("/api/v1/manager-recipient")).json()
    assert after["recipient"] is None and after["version"] > legacy["version"]
    stale = await wizard.http.post("/api/v1/manager-recipient/cancel", json={"version": legacy["version"]})
    assert stale.status_code == 409


async def test_canonical_notification_ignores_an_older_attempt_result(session, runtime):
    runtime.handoff_provider = Recorder()
    await _ask_for_a_manager(session, runtime)
    await session.commit()
    job = await JobQueue(session).claim("merge-worker", 60, ["notify_handoff"])
    await session.commit()
    assert job is not None
    handoff = await session.scalar(select(HandoffRequestRow))
    handoff.notify_status = "sending"
    handoff.notify_generation = 2
    await session.commit()
    notifier = HandoffNotifier(runtime.session_factory, runtime.handoff_provider)
    await notifier._finish(job, "merge-worker", "sent", None, generation=1)
    session.expire_all()
    row = await session.get(HandoffRequestRow, job.handoff_id)
    assert row.notify_status == "sending" and row.notified_at is None
    assert (await session.get(JobRow, job.id)).status == "running"
    await notifier._finish(job, "merge-worker", "sent", None, generation=2)
    session.expire_all()
    assert (await session.get(HandoffRequestRow, job.handoff_id)).notify_status == "sent"
