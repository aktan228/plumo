"""Client token -> encrypted store -> signed webhook -> proof -> real queued agent reply."""

import asyncio
from urllib.parse import parse_qs, urlsplit

import httpx

from channel_stand import TG_TOKEN
from app.infrastructure.channels.credentials import CredentialStore
from app.infrastructure.database.channel_repositories import ConnectionRepository
from app.infrastructure.database.models import BusinessRow
from app.main import create_app


async def connect(stand, **extra):
    result = await stand.client.post("/api/v1/integrations/telegram/connect", json={"token": TG_TOKEN, **extra})
    assert result.status_code == 200, result.text
    data = result.json()
    async with stand.factory() as db:
        connection = await ConnectionRepository(db).get(data["id"])
    return data, connection


async def proof(stand, data, connection, update_id=100):
    parameter = parse_qs(urlsplit(data["verification"]["link"]).query)["start"][0]
    response = await stand.tg_update(connection, update_id, "/start " + parameter)
    assert response.status_code == 200
    return parameter


async def publish_marker(stand):
    async with stand.factory() as db:
        business = await db.get(BusinessRow, stand.business.id)
        business.profile = {**business.profile, "onboarding_publication": {"draft_version": 1, "knowledge_count": 2}}
        await db.commit()


async def test_self_service_encrypts_token_and_does_not_need_credentials_file(stand, caplog):
    stand.runtime.channel_gateway.credentials = CredentialStore("")
    data, connection = await connect(stand)
    assert data["auth_method"] == "bot_token" and data["agent_enabled"] is False
    assert data["verification"]["state"] == "pending" and TG_TOKEN not in str(data)
    assert connection.encrypted_token.startswith("v1.") and TG_TOKEN not in connection.encrypted_token
    assert stand.runtime.channel_gateway.token(connection) == TG_TOKEN
    overview = await stand.client.get("/api/v1/integrations")
    assert TG_TOKEN not in overview.text and "encrypted_token" not in overview.text
    assert "credentials_file" not in overview.json()["channels"][0]["requirements"]
    assert TG_TOKEN not in caplog.text
    for body in [
        {"token": "invalid"},
        {"token": TG_TOKEN, "credential_ref": "tg-test"},
        {"token": TG_TOKEN, "business_id": str(stand.tokens["other_business"])},
    ]:
        result = await stand.client.post("/api/v1/integrations/telegram/connect", json=body)
        assert result.status_code == 422 and TG_TOKEN not in result.text


async def test_proof_before_enable_then_real_inbound_response(stand):
    await publish_marker(stand)
    data, connection = await connect(stand)
    early = await stand.client.patch(f"/api/v1/integrations/{connection.id}", json={"agent_enabled": True})
    assert early.status_code == 409 and early.json()["code"] == "telegram_test_required"
    before = await stand.sql("SELECT count(*) FROM customers")
    parameter = await proof(stand, data, connection)
    assert stand.providers.sent == []
    assert await stand.worker.drain() == 1
    assert len(stand.providers.sent) == 1 and "проверено" in stand.providers.sent[0]["text"]
    assert await stand.sql("SELECT count(*) FROM customers") == before
    overview = (await stand.client.get("/api/v1/integrations")).json()["channels"][0]["connection"]
    assert overview["verification"]["state"] == "verified"
    assert (
        await stand.client.patch(
            f"/api/v1/integrations/{connection.id}", json={"agent_enabled": True, "version": overview["version"]}
        )
    ).status_code == 200
    await stand.tg_update(connection, 100, "/start " + parameter)
    await stand.worker.drain()
    assert len(stand.providers.sent) == 1
    await stand.tg_update(connection, 101, "Еще продается квартира за 85000?")
    assert await stand.worker.drain() == 2
    assert len(stand.providers.sent) == 2 and "85 000" in stand.providers.sent[-1]["text"]
    disconnected = await stand.client.post(f"/api/v1/integrations/{connection.id}/disconnect")
    assert disconnected.json()["agent_enabled"] is False
    assert (await stand.sql("SELECT encrypted_token FROM channel_connections WHERE id=:id", id=connection.id))[0][
        0
    ] is None


async def test_webhook_conflict_and_other_tenant_cannot_take_bot(stand):
    stand.providers.webhook_url = "https://other.example/webhook"
    conflict = await stand.client.post("/api/v1/integrations/telegram/connect", json={"token": TG_TOKEN})
    assert conflict.status_code == 409 and conflict.json()["code"] == "webhook_conflict"
    assert stand.providers.webhook_url == "https://other.example/webhook"
    data, connection = await connect(stand, replace_webhook=True)
    assert data["status"] == "connected"
    other = await stand.client.post(
        "/api/v1/integrations/telegram/connect",
        json={"token": TG_TOKEN},
        headers={"authorization": f"Bearer {stand.tokens['other']}"},
    )
    assert other.status_code == 409 and other.json()["code"] == "account_in_use"
    forbidden = await stand.client.post(
        f"/api/v1/integrations/{connection.id}/verification",
        headers={"authorization": f"Bearer {stand.tokens['other']}"},
    )
    assert forbidden.status_code == 404


async def test_ambiguous_control_message_is_not_resent_automatically(stand):
    data, connection = await connect(stand)
    parameter = await proof(stand, data, connection)
    stand.providers.fail("sendMessage", httpx.ReadTimeout("test timeout"))
    await stand.worker.drain()
    record = (await stand.client.get("/api/v1/integrations")).json()["channels"][0]["connection"]
    assert record["verification"]["state"] == "unknown"
    count = stand.providers.calls.count("sendMessage")
    await stand.tg_update(connection, 101, "/start " + parameter)
    await stand.worker.drain()
    assert stand.providers.calls.count("sendMessage") == count
    fresh = (await stand.client.post(f"/api/v1/integrations/{connection.id}/verification")).json()
    assert fresh["verification"]["link"] != data["verification"]["link"]
    await proof(stand, fresh, connection, 102)
    await stand.worker.drain()
    assert (await stand.client.get("/api/v1/integrations")).json()["channels"][0]["connection"]["verification"][
        "state"
    ] == "verified"


async def test_bad_proof_is_ignored_and_rotated_key_requires_token_again(stand, monkeypatch):
    data, connection = await connect(stand)
    await stand.tg_update(connection, 100, "/start plumo_check_wrong")
    await stand.worker.drain()
    assert stand.providers.sent == []
    monkeypatch.setenv("CHANNEL_SECRET_KEY", "different-server-key")
    result = await stand.client.post(f"/api/v1/integrations/{connection.id}/check")
    assert result.json()["status"] == "action_required" and TG_TOKEN not in result.text


async def test_embedded_worker_processes_verification_without_manual_drain(stand):
    data, connection = await connect(stand)
    await proof(stand, data, connection)
    settings = stand.runtime.settings.model_copy(
        update={"channel_worker_enabled": True, "worker_poll_interval_s": 0.02}
    )
    app = create_app(settings=settings, runtime=stand.runtime)
    async with app.router.lifespan_context(app):
        async with asyncio.timeout(8):
            while not stand.providers.sent:
                await asyncio.sleep(0.05)
    assert len(stand.providers.sent) == 1
