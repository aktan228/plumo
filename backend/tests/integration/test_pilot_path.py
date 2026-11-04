"""J-06: the pilot path end to end for two businesses at once, through the real API, worker and database.

Telegram (business bots and the service bot) is faked at the HTTP level; everything else is real.
Each step has its own detailed test elsewhere (see docs/pilot-path.md); this one checks the seams.
"""

from test_manager_recipients import Recorder, _as, _bind

from app.worker import Worker


async def _dialog(stand, who: str) -> str:
    items = (await stand.client.get("/api/v1/conversations", headers=_as(stand, who))).json()["items"]
    assert len(items) == 1
    return items[0]["id"]


async def test_two_businesses_walk_the_pilot_path_without_seeing_each_other(stand):
    manager_bot = stand.runtime.handoff_provider = Recorder()
    own_bot = await stand.telegram()
    other_bot = await stand.telegram(business_id=stand.tokens["other_business"])
    await _bind(stand, "own", 1001, update_id=1)
    await _bind(stand, "other", 2002, update_id=2)
    # A worker built after the fake service bot is in place (it keeps the provider it starts with).
    worker = Worker(stand.runtime, worker_id="pilot")

    # A customer of each business asks, the agent answers in that business's bot.
    await stand.tg_update(own_bot, 10, "Еще продается квартира за 85000?", chat_id=5550001)
    await stand.tg_update(other_bot, 20, "Здравствуйте", chat_id=6660001)
    await worker.drain()
    assert len(stand.providers.sent) == 2

    # Both ask for a person: each manager is told in their own chat, once.
    await stand.tg_update(own_bot, 11, "Позовите менеджера", chat_id=5550001)
    await stand.tg_update(other_bot, 21, "Позовите менеджера", chat_id=6660001)
    await worker.drain()
    assert sorted(chat for _, chat in manager_bot.notified) == ["1001", "2002"]

    own_dialog, other_dialog = await _dialog(stand, "own"), await _dialog(stand, "other")
    assert own_dialog != other_dialog
    card = (await stand.client.get(f"/api/v1/conversations/{own_dialog}")).json()
    assert card["handoff"]["notify_status"] == "sent"
    # The link in the notification opens only the business's own dialog.
    assert (await stand.client.get(f"/api/v1/conversations/{other_dialog}")).status_code == 404

    # The manager takes the dialog, answers in the channel and gives it back.
    assert (await stand.client.post(f"/api/v1/conversations/{own_dialog}/takeover")).json()["mode"] == "human"
    assert (await stand.client.post(f"/api/v1/conversations/{other_dialog}/takeover")).status_code == 404
    sent = await stand.client.post(
        f"/api/v1/conversations/{own_dialog}/messages", json={"text": "Здравствуйте, это менеджер.", "idempotency_key": "pilot-0001-abc"}
    )
    assert sent.status_code == 200
    await worker.drain()
    assert stand.providers.sent[-1]["text"] == "Здравствуйте, это менеджер."
    assert (await stand.client.post(f"/api/v1/conversations/{own_dialog}/resume")).json()["mode"] == "ai"

    # The agent answers again; the other business's dialog is still waiting for its manager.
    replies = len(stand.providers.sent)
    await stand.tg_update(own_bot, 12, "Спасибо, а на Киевской сколько?", chat_id=5550001)
    await worker.drain()
    assert len(stand.providers.sent) == replies + 1
    other_card = (await stand.client.get(f"/api/v1/conversations/{other_dialog}", headers=_as(stand, "other"))).json()
    assert other_card["dialog"]["mode"] == "waiting"

    # Each business sees only its own allowance.
    own_limits = (await stand.client.get("/api/v1/limits")).json()
    other_limits = (await stand.client.get("/api/v1/limits", headers=_as(stand, "other"))).json()
    assert own_limits["calls"] >= 3 and other_limits["calls"] == 2
