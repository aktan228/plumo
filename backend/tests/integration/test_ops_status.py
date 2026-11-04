"""J-05: health for monitoring. No model, no messages, no secrets in answers."""

from datetime import timedelta

from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.domain.models import utcnow
from app.infrastructure.database.models import JobRow, WorkerHeartbeatRow
from app.main import create_app
from app.worker import Worker

OPS = {"Authorization": "Bearer ops-secret"}


async def test_status_needs_the_ops_token_and_is_off_without_it(client, monkeypatch):
    monkeypatch.delenv("OPS_TOKEN", raising=False)
    assert (await client.get("/ops/status", headers=OPS)).status_code == 404
    monkeypatch.setenv("OPS_TOKEN", "ops-secret")
    assert (await client.get("/ops/status")).status_code == 401
    # An operator's dashboard session is not the ops token.
    assert (await client.get("/ops/status", headers={"Authorization": client.headers["Authorization"]})).status_code == 401
    assert (await client.get("/ops/status", headers=OPS)).status_code == 200


async def test_stopped_worker_makes_the_heartbeat_stale(client, runtime, monkeypatch):
    monkeypatch.setenv("OPS_TOKEN", "ops-secret")
    app_runtime = client._transport.app.state.runtime
    worker = Worker(app_runtime, worker_id="w1")
    await worker.beat(utcnow())
    fresh = (await client.get("/ops/status", headers=OPS)).json()
    assert fresh["workers"]["alive"] == 1 and fresh["workers"]["last_heartbeat_age_s"] < 5
    assert fresh["database"] == "ok" and "schema_version" in fresh

    async with app_runtime.session_factory() as session:
        row = await session.get(WorkerHeartbeatRow, "w1")
        row.seen_at = utcnow() - timedelta(minutes=5)
        await session.commit()
    stale = (await client.get("/ops/status", headers=OPS)).json()
    assert stale["workers"]["alive"] == 0 and stale["status"] == "degraded"


async def test_a_delayed_retry_is_not_an_overdue_job(client, monkeypatch):
    monkeypatch.setenv("OPS_TOKEN", "ops-secret")
    app_runtime = client._transport.app.state.runtime
    await Worker(app_runtime, worker_id="w1").beat(utcnow())
    async with app_runtime.session_factory() as session:
        from app.seed import DEMO_BUSINESS_ID

        now = utcnow()
        session.add(JobRow(kind="send_outbound", business_id=DEMO_BUSINESS_ID, ordering_key="k", status="queued",
                           attempts=1, max_attempts=5, run_at=now + timedelta(minutes=2), created_at=now, updated_at=now))
        await session.commit()
    status = (await client.get("/ops/status", headers=OPS)).json()
    assert status["jobs"]["due"] == 0 and status["jobs"]["delayed_retries"] == 1
    assert status["status"] == "ok"


async def test_no_database_is_unhealthy_without_details(monkeypatch):
    monkeypatch.setenv("OPS_TOKEN", "ops-secret")
    monkeypatch.delenv("PLUMO_API_KEY", raising=False)
    dead = "postgresql+asyncpg://plumo:s3cret-pass@127.0.0.1:1/plumo_nowhere"
    application = create_app(Settings(database_url=dead, ai_mode="mock", handoff_provider="mock"))
    async with application.router.lifespan_context(application):
        async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as http:
            assert (await http.get("/health")).status_code == 200
            db = await http.get("/health/db")
            status = await http.get("/ops/status", headers=OPS)
    assert db.status_code == 503 and db.json() == {"status": "unavailable"}
    assert status.status_code == 503
    for answer in (db.text, status.text):
        assert "s3cret" not in answer and "127.0.0.1" not in answer and "plumo_nowhere" not in answer


async def test_status_names_the_running_code_and_hides_configuration_values(client, monkeypatch):
    monkeypatch.setenv("OPS_TOKEN", "ops-secret")
    monkeypatch.setenv("APP_COMMIT", "abc1234def5678")
    monkeypatch.setenv("RESEND_API_KEY", "re_secret_value")
    app_runtime = client._transport.app.state.runtime
    worker = Worker(app_runtime)
    await worker.beat(utcnow())
    status = (await client.get("/ops/status", headers=OPS)).json()
    assert status["commit"] == "abc1234def56"
    assert status["workers"]["commits"] == ["abc1234def56"]
    config = status["config"]
    assert config["present"]["RESEND_API_KEY"] is True and config["present"]["OPS_TOKEN"] is True
    # Test settings are a development mock: exactly what must never pass as a stand.
    assert {"app_env_development", "ai_mode_mock", "handoff_provider_mock"} <= set(config["problems"])
    text = (await client.get("/ops/status", headers=OPS)).text
    assert "re_secret_value" not in text and "ops-secret" not in text and "postgresql" not in text
