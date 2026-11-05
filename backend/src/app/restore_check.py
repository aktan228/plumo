"""Check a restored database copy (PJ-06). Read-only; prints counts and statuses, never texts, contacts or secrets.

    python -m app.restore_check --snapshot > counts.json    # on the source, right before the backup
    python -m app.restore_check --expect counts.json         # on the restored copy

DATABASE_URL points at the database to check; CHANNEL_SECRET_KEY (optional) is the key the copy will run with.
Exit code 0 = every check passed. Nothing is sent: the copy must not run a worker (see docs/operations.md).
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import text

from app.config import get_settings
from app.infrastructure.channels.base import ChannelError
from app.infrastructure.channels.token_crypto import decrypt_token
from app.infrastructure.database.session import create_engine

# What a restore must bring back. Counted, never read.
COUNTS = {
    "businesses": "SELECT count(*) FROM businesses",
    "operators": "SELECT count(*) FROM operators",
    "knowledge_items_active": "SELECT count(*) FROM knowledge_items WHERE active",
    "scenario_revisions": "SELECT count(*) FROM scenario_revisions",
    "customers": "SELECT count(*) FROM customers",
    "conversations": "SELECT count(*) FROM conversations",
    "messages": "SELECT count(*) FROM messages",
    "handoff_requests": "SELECT count(*) FROM handoff_requests",
    "channel_connections_live": "SELECT count(*) FROM channel_connections WHERE status <> 'disconnected'",
    "manager_recipients_confirmed": "SELECT count(*) FROM manager_recipients WHERE chat_id IS NOT NULL",
}

# One business's rows must not point at another business's rows.
CROSS_BUSINESS = {
    "conversation_customer": "SELECT count(*) FROM conversations c JOIN customers u ON u.id = c.customer_id "
    "WHERE c.business_id IS DISTINCT FROM u.business_id",
    "message_conversation": "SELECT count(*) FROM messages m JOIN conversations c ON c.id = m.conversation_id "
    "WHERE m.customer_id <> c.customer_id",
    "handoff_conversation": "SELECT count(*) FROM handoff_requests h JOIN conversations c ON c.id = h.conversation_id "
    "WHERE h.customer_id <> c.customer_id",
}

# Work a worker would do on start: on a restored copy that means messages to real people.
PENDING = {
    "jobs_queued": "SELECT count(*) FROM jobs WHERE status IN ('queued', 'running')",
    "outbound_queued": "SELECT count(*) FROM outbound_messages WHERE status IN ('queued', 'sending')",
}


def migrations_head() -> str:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    return ScriptDirectory.from_config(config).get_current_head()


async def collect(url: str) -> dict:
    engine = create_engine(url, null_pool=True)
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SET TRANSACTION READ ONLY"))
            scalar = connection.scalar
            data = {
                "schema_version": await scalar(text("SELECT version_num FROM alembic_version"))
                if await scalar(text("SELECT to_regclass('alembic_version') IS NOT NULL")) else None,
                "counts": {name: await scalar(text(sql)) for name, sql in COUNTS.items()},
                "cross_business": {name: await scalar(text(sql)) for name, sql in CROSS_BUSINESS.items()},
                "pending": {name: await scalar(text(sql)) for name, sql in PENDING.items()},
                "latest_message_at": await scalar(text("SELECT max(created_at) FROM messages")),
                "worker_last_seen_at": await scalar(text("SELECT max(seen_at) FROM worker_heartbeats")),
            }
            tokens = (
                await connection.execute(
                    text("SELECT business_id, id, encrypted_token FROM channel_connections "
                         "WHERE status <> 'disconnected' AND encrypted_token IS NOT NULL")
                )
            ).all()
    finally:
        await engine.dispose()
    opened = 0
    if os.getenv("CHANNEL_SECRET_KEY", "").strip():
        for business_id, connection_id, value in tokens:
            try:
                decrypt_token(value, business_id, connection_id)  # the result is dropped, never printed
                opened += 1
            except ChannelError:
                pass
    data["tokens"] = {"stored": len(tokens), "opened": opened, "key_set": bool(os.getenv("CHANNEL_SECRET_KEY", "").strip())}
    return data


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(UTC).isoformat(timespec="seconds") if value else None


def check(data: dict, expected: dict | None, head: str) -> int:
    failed = 0

    def line(name: str, ok: bool, detail: str) -> None:
        nonlocal failed
        failed += not ok
        print(f"{'ok  ' if ok else 'FAIL'} {name}: {detail}")

    now = datetime.now(UTC)
    line("schema version", data["schema_version"] == head, f"{data['schema_version']}, head of this code {head}")
    for name, value in data["counts"].items():
        if expected:
            want = expected["counts"].get(name)
            line(name, value == want, f"{value}, source {want}")
        else:
            line(name, True, str(value))
    for name, value in data["cross_business"].items():
        line(f"no cross-business link: {name}", value == 0, str(value))
    beat = data["worker_last_seen_at"]
    # A heartbeat restored from the backup is old; a fresh one means a worker runs against this copy.
    line("no worker on this copy", not beat or now - beat > timedelta(minutes=2), f"last heartbeat {_iso(beat)}")
    pending = data["pending"]
    line(
        "pending work reviewed",
        True,
        f"jobs {pending['jobs_queued']}, replies {pending['outbound_queued']} — a worker started here would send them",
    )
    tokens = data["tokens"]
    if not tokens["key_set"]:
        line("channel tokens open with CHANNEL_SECRET_KEY", tokens["stored"] == 0, f"key not set, {tokens['stored']} stored")
    else:
        line("channel tokens open with CHANNEL_SECRET_KEY", tokens["opened"] == tokens["stored"],
             f"{tokens['opened']} of {tokens['stored']}")
    latest = data["latest_message_at"]
    print(f"     latest message in the copy: {_iso(latest)}" + (f" ({(now - latest).total_seconds() / 3600:.1f} h ago)" if latest else ""))
    if expected:
        print(f"     source snapshot taken at {expected.get('taken_at')}")
    print("passed" if not failed else f"{failed} failed")
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--snapshot", action="store_true", help="print counts as JSON (run on the source)")
    group.add_argument("--expect", type=Path, help="JSON from --snapshot to compare with")
    args = parser.parse_args()
    data = asyncio.run(collect(get_settings().database_url))
    if args.snapshot:
        snapshot = {"taken_at": _iso(datetime.now(UTC)), "schema_version": data["schema_version"], "counts": data["counts"]}
        json.dump(snapshot, sys.stdout, indent=2)
        print()
        return 0
    expected = json.loads(args.expect.read_text(encoding="utf-8")) if args.expect else None
    return check(data, expected, migrations_head())


if __name__ == "__main__":
    sys.exit(main())
