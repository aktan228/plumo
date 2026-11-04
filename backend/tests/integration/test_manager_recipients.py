"""J-01: each business binds its own manager chat; notifications never cross businesses or fall back."""

from datetime import timedelta

from sqlalchemy import select, text

from app.application.services.manager_recipients import manager_webhook_secret
from app.container import build_agent
from app.domain.enums import JobKind
from app.domain.errors import ProviderUnavailable
from app.domain.models import InboundMessage, utcnow
from app.infrastructure.database.models import JobRow, ManagerRecipientRow
from app.worker import Worker

WEBHOOK = "/api/v1/webhooks/telegram-manager"
SECRET = {"X-Telegram-Bot-Api-Secret-Token": manager_webhook_secret("test-channel-secret")}


class Recorder:
    def __init__(self, script=()):
        self.notified: list[tuple[str, str]] = []
        self.texts: list[str] = []
        self.script = list(script)

    async def notify(self, handoff, chat_id):
        self.notified.append((str(handoff.conversation_id), chat_id))
        step = self.script.pop(0) if self.script else None
        if step is not None:
            raise step

    async def send_text(self, chat_id, text):
        self.texts.append(chat_id)


def _start(code_command: str, chat_id: int, update_id: int = 1, chat_type: str = "private") -> dict:
    return {
        "update_id": update_id,
        "message": {
            "message_id": 1,
            "date": 1761700000,
            "chat": {"id": chat_id, "type": chat_type},
            "from": {"id": chat_id, "is_bot": False, "first_name": "Айбек", "username": "aibek_mgr"},
            "text": code_command,
        },
    }


def _as(stand, who: str) -> dict:
    return {"Authorization": f"Bearer {stand.tokens[who]}"}


async def _bind(stand, who: str, chat_id: int, update_id: int) -> dict:
    """The whole flow through the API: link, the manager's /start, the operator's confirmation."""

    link = (await stand.client.post("/api/v1/manager-notifications/link", headers=_as(stand, who))).json()
    reply = await stand.client.post(WEBHOOK, json=_start(link["command"], chat_id, update_id), headers=SECRET)
    assert reply.status_code == 200 and reply.json()["method"] == "sendMessage"
    confirmed = await stand.client.post("/api/v1/manager-notifications/confirm", headers=_as(stand, who))
    assert confirmed.status_code == 200, confirmed.text
    return confirmed.json()


async def _handoff(stand, business_id, user: str) -> None:
    async with stand.factory() as session:
        agent = build_agent(session, stand.runtime)
        response = await agent.process_message(
            InboundMessage(channel="whatsapp", external_user_id=user, text="Позовите менеджера", business_id=business_id)
        )
        assert response.handoff_required
        await session.commit()


async def _notify_jobs(stand) -> list[JobRow]:
    async with stand.factory() as session:
        return list((await session.scalars(select(JobRow).where(JobRow.kind == JobKind.notify_handoff))).all())


async def test_link_start_and_confirm_make_the_chat_ready(stand):
    recorder = stand.runtime.handoff_provider = Recorder()
    before = (await stand.client.get("/api/v1/manager-notifications")).json()
    assert before["status"] == "not_configured"

    link = (await stand.client.post("/api/v1/manager-notifications/link")).json()
    assert link["status"] == "waiting_code" and link["command"].startswith("/start plumo_mgr_")
    code = link["command"].removeprefix("/start plumo_mgr_")
    async with stand.factory() as session:
        row = await session.get(ManagerRecipientRow, stand.business.id)
        assert row.code_hash and code not in row.code_hash

    await stand.client.post(WEBHOOK, json=_start(link["command"], 5551), headers=SECRET)
    waiting = (await stand.client.get("/api/v1/manager-notifications")).json()
    assert waiting["status"] == "awaiting_confirmation"
    assert waiting["candidate"]["label"] == "Айбек @aibek_mgr" and waiting["recipient"] is None

    confirmed = (await stand.client.post("/api/v1/manager-notifications/confirm")).json()
    assert confirmed["status"] == "ready" and confirmed["control_delivery"] == "sent"
    assert confirmed["recipient"]["label"] == "Айбек @aibek_mgr"
    assert recorder.texts == ["5551"]


async def test_each_business_gets_only_its_own_notifications(stand):
    recorder = stand.runtime.handoff_provider = Recorder()
    await _bind(stand, "own", 1001, update_id=1)
    await _bind(stand, "other", 2002, update_id=2)
    await _handoff(stand, stand.business.id, "+996700000001")
    await _handoff(stand, stand.tokens["other_business"], "+996700000002")

    await Worker(stand.runtime, worker_id="t").drain()

    async with stand.factory() as session:
        rows = (await session.execute(text("SELECT id::text, business_id FROM conversations"))).all()
    owner = {conversation: business for conversation, business in rows}
    chat_of = {stand.business.id: "1001", stand.tokens["other_business"]: "2002"}
    assert len(recorder.notified) == 2
    for conversation, chat in recorder.notified:
        assert chat == chat_of[owner[conversation]]


async def test_another_business_cannot_confirm_or_disconnect_this_recipient(stand):
    stand.runtime.handoff_provider = Recorder()
    link = (await stand.client.post("/api/v1/manager-notifications/link")).json()
    await stand.client.post(WEBHOOK, json=_start(link["command"], 1001), headers=SECRET)

    # The other business's operator only ever reaches its own (empty) record.
    other_confirm = await stand.client.post("/api/v1/manager-notifications/confirm", headers=_as(stand, "other"))
    assert other_confirm.status_code == 409
    other_delete = await stand.client.post("/api/v1/manager-notifications/disconnect", headers=_as(stand, "other"))
    assert other_delete.status_code == 404
    assert (await stand.client.get("/api/v1/manager-notifications", headers=_as(stand, "other"))).json()["status"] == "not_configured"

    own = (await stand.client.get("/api/v1/manager-notifications")).json()
    assert own["status"] == "awaiting_confirmation"


async def test_expired_and_reused_codes_bind_nothing(stand):
    stand.runtime.handoff_provider = Recorder()
    first = (await stand.client.post("/api/v1/manager-notifications/link")).json()
    used = await stand.client.post(WEBHOOK, json=_start(first["command"], 1001, 1), headers=SECRET)
    assert "Вернитесь в кабинет" in used.json()["text"]
    again = await stand.client.post(WEBHOOK, json=_start(first["command"], 6666, 2), headers=SECRET)
    assert "не найден" in again.json()["text"]
    candidate = (await stand.client.get("/api/v1/manager-notifications")).json()["candidate"]
    assert candidate["label"].startswith("Айбек")
    async with stand.factory() as session:
        assert (await session.get(ManagerRecipientRow, stand.business.id)).candidate_chat_id == "1001"

    late = (await stand.client.post("/api/v1/manager-notifications/link")).json()
    async with stand.factory() as session:
        await session.execute(
            text("UPDATE manager_recipients SET code_expires_at = :at"), {"at": utcnow() - timedelta(seconds=1)}
        )
        await session.commit()
    expired = await stand.client.post(WEBHOOK, json=_start(late["command"], 7777, 3), headers=SECRET)
    assert "не найден" in expired.json()["text"]
    assert (await stand.client.get("/api/v1/manager-notifications")).json()["status"] == "not_configured"


async def test_forged_or_unsigned_update_binds_nothing(stand):
    link = (await stand.client.post("/api/v1/manager-notifications/link")).json()
    unsigned = await stand.client.post(WEBHOOK, json=_start(link["command"], 1001))
    forged = await stand.client.post(
        WEBHOOK, json=_start(link["command"], 1001), headers={"X-Telegram-Bot-Api-Secret-Token": "guess"}
    )
    group = await stand.client.post(WEBHOOK, json=_start(link["command"], -1001, chat_type="group"), headers=SECRET)
    assert unsigned.status_code == 401 and forged.status_code == 401
    assert group.status_code == 200 and group.json() == {"ok": True}
    assert (await stand.client.get("/api/v1/manager-notifications")).json()["status"] == "waiting_code"


async def test_business_without_recipient_is_not_notified_anywhere(stand):
    recorder = stand.runtime.handoff_provider = Recorder()
    await _bind(stand, "other", 2002, update_id=1)
    await _handoff(stand, stand.business.id, "+996700000003")

    await Worker(stand.runtime, worker_id="t").drain()

    assert recorder.notified == []
    jobs = await _notify_jobs(stand)
    assert [(job.status, job.last_error) for job in jobs] == [("failed", "recipient_not_configured")]
    assert (await stand.client.get("/api/v1/manager-notifications")).json()["status"] == "not_configured"


async def test_new_manager_takes_over_only_after_confirmation(stand):
    recorder = stand.runtime.handoff_provider = Recorder()
    await _bind(stand, "own", 1001, update_id=1)
    link = (await stand.client.post("/api/v1/manager-notifications/link")).json()
    await stand.client.post(WEBHOOK, json=_start(link["command"], 3003, 2), headers=SECRET)

    # Not confirmed yet: the current manager still gets the notification.
    await _handoff(stand, stand.business.id, "+996700000004")
    await Worker(stand.runtime, worker_id="t").drain()
    assert recorder.notified[-1][1] == "1001"

    await stand.client.post("/api/v1/manager-notifications/confirm")
    await _handoff(stand, stand.business.id, "+996700000005")
    await Worker(stand.runtime, worker_id="t").drain()
    assert recorder.notified[-1][1] == "3003"


async def test_disconnected_recipient_gets_the_waiting_notification_nowhere(stand):
    recorder = stand.runtime.handoff_provider = Recorder()
    await _bind(stand, "own", 1001, update_id=1)
    await _handoff(stand, stand.business.id, "+996700000006")
    assert (await stand.client.post("/api/v1/manager-notifications/disconnect")).json()["status"] == "not_configured"

    await Worker(stand.runtime, worker_id="t").drain()
    assert recorder.notified == []
    assert (await _notify_jobs(stand))[0].last_error == "recipient_not_configured"


async def test_rejected_delivery_needs_attention_until_a_send_works(stand):
    recorder = stand.runtime.handoff_provider = Recorder([ProviderUnavailable("bot was blocked by the user"), None])
    await _bind(stand, "own", 1001, update_id=1)
    await _handoff(stand, stand.business.id, "+996700000007")
    await Worker(stand.runtime, worker_id="t").drain()
    state = (await stand.client.get("/api/v1/manager-notifications")).json()
    assert state["status"] == "needs_attention" and state["attention"] == "delivery_rejected"

    await _handoff(stand, stand.business.id, "+996700000008")
    await Worker(stand.runtime, worker_id="t").drain()
    assert [chat for _, chat in recorder.notified] == ["1001", "1001"]
    assert (await stand.client.get("/api/v1/manager-notifications")).json()["status"] == "ready"


async def test_confirm_without_a_candidate_is_refused(stand):
    response = await stand.client.post("/api/v1/manager-notifications/confirm")
    assert response.status_code == 409 and response.json()["code"] == "no_candidate"


async def test_two_first_link_requests_at_once_both_succeed(stand):
    import asyncio

    first, second = await asyncio.gather(
        stand.client.post("/api/v1/manager-notifications/link"), stand.client.post("/api/v1/manager-notifications/link")
    )
    assert (first.status_code, second.status_code) == (200, 200)
    # Only the newer code works: each request replaces the previous unused one.
    assert (await stand.client.get("/api/v1/manager-notifications")).json()["status"] == "waiting_code"
