"""PJ-06: the restored-copy check counts, links and opens tokens without printing any of them."""

import uuid

from app.domain.models import utcnow
from app.infrastructure.channels.token_crypto import encrypt_token
from app.infrastructure.database.models import ChannelConnectionRow, WorkerHeartbeatRow
from app.infrastructure.database.session import create_session_factory
from app.restore_check import check, collect
from app.seed import seed


async def test_copy_matches_its_snapshot_and_a_wrong_key_or_live_worker_fails(engine, settings, monkeypatch, capsys):
    url = settings.database_url
    monkeypatch.setenv("CHANNEL_SECRET_KEY", "restore-key")
    async with create_session_factory(engine)() as session:
        business_id = (await seed(session)).id
        connection_id = uuid.uuid4()
        session.add(ChannelConnectionRow(
            id=connection_id, business_id=business_id, channel="telegram", credential_ref="db",
            encrypted_token=encrypt_token("123:token-value", business_id, connection_id), external_account_id="1",
            status="connected", created_at=utcnow(), updated_at=utcnow(),
        ))
        await session.commit()

    data = await collect(url)
    snapshot = {"counts": dict(data["counts"])}
    assert data["tokens"] == {"stored": 1, "opened": 1, "key_set": True}
    assert check(data, snapshot, data["schema_version"]) == 0
    assert "token-value" not in capsys.readouterr().out

    snapshot["counts"]["knowledge_items_active"] += 1  # a row lost in the restore
    assert check(data, snapshot, data["schema_version"]) == 1

    monkeypatch.setenv("CHANNEL_SECRET_KEY", "another-key")
    assert (await collect(url))["tokens"]["opened"] == 0

    monkeypatch.setenv("CHANNEL_SECRET_KEY", "restore-key")
    async with create_session_factory(engine)() as session:
        session.add(WorkerHeartbeatRow(worker_id="w", started_at=utcnow(), seen_at=utcnow()))
        await session.commit()
    capsys.readouterr()
    assert check(await collect(url), None, data["schema_version"]) == 1
    assert "FAIL no worker on this copy" in capsys.readouterr().out
