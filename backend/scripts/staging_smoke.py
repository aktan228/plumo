"""Smoke check of a deployed stand (PJ-03). Standard library only; sends nothing to customers or managers.

    OPS_TOKEN=... python scripts/staging_smoke.py --api https://api.example --frontend https://app.example \
        --expect-commit <sha> [--wait-s 900]

The ops token is read from the environment, never from the command line, and is not printed.
Exit code 0 = every check passed. Checks are listed in docs/operations.md, «Проверки после запуска».
"""

import argparse
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

TIMEOUT_S = 15


def request(url: str, *, method: str = "GET", headers: dict | None = None, body: dict | None = None) -> tuple[int, str]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"user-agent": "plumo-smoke", **(headers or {})})
    if data is not None:
        req.add_header("content-type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        return 0, type(error).__name__


def parse(text: str) -> dict:
    try:
        value = json.loads(text)
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def same_commit(expected: str, actual: str) -> bool:
    actual = (actual or "").strip().lower()
    return len(actual) >= 7 and actual != "unknown" and expected.strip().lower().startswith(actual)


def migrations_head() -> str | None:
    """Head of the Alembic chain in this checkout, when Alembic is installed."""

    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory
    except ImportError:
        return None
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    return ScriptDirectory.from_config(config).get_current_head()


class Report:
    def __init__(self) -> None:
        self.failed = 0

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        self.failed += not ok
        print(f"{'ok  ' if ok else 'FAIL'} {name}{': ' + detail if detail else ''}")
        return ok


def wait_for_release(api: str, token: str, commit: str, wait_s: float) -> None:
    """Hosting deploys on its own: poll until the API and a worker run the expected commit."""

    deadline = time.monotonic() + wait_s
    while True:
        code, text = request(f"{api}/ops/status", headers={"authorization": f"Bearer {token}"})
        status = parse(text)
        workers = status.get("workers", {}).get("commits", [])
        if code == 200 and same_commit(commit, status.get("commit", "")) and workers and all(same_commit(commit, w) for w in workers):
            return
        if time.monotonic() >= deadline:
            print(f"waited {int(wait_s)} s for commit {commit[:12]}: api={status.get('commit')} workers={workers}")
            return
        time.sleep(15)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--api", required=True, help="public HTTPS address of the API")
    parser.add_argument("--frontend", required=True, help="public HTTPS address of the dashboard")
    parser.add_argument("--expect-commit", default="", help="commit that must be running (API and workers)")
    parser.add_argument("--expect-schema", default="head", help="Alembic revision; 'head' = head of this checkout")
    parser.add_argument("--wait-s", type=float, default=0, help="wait up to this long for --expect-commit to be deployed")
    args = parser.parse_args()
    api, frontend = args.api.rstrip("/"), args.frontend.rstrip("/")
    token = os.getenv("OPS_TOKEN", "").strip()
    report = Report()
    if not token:
        report.check("OPS_TOKEN in the environment", False, "not set")
        return 1
    schema = migrations_head() if args.expect_schema == "head" else args.expect_schema
    if args.expect_commit and args.wait_s:
        wait_for_release(api, token, args.expect_commit, args.wait_s)

    for name, url in (("api", api), ("frontend", frontend)):
        report.check(f"{name} over HTTPS", urlsplit(url).scheme == "https", urlsplit(url).netloc)

    code, text = request(f"{api}/health")
    report.check("API /health", code == 200 and parse(text).get("status") == "ok", f"HTTP {code}")
    code, text = request(f"{api}/health/db")
    report.check("API /health/db", code == 200 and parse(text).get("status") == "ok", f"HTTP {code}")
    code, text = request(f"{api}/api/v1/auth/me")
    report.check("API closed without the service key", code == 401 and parse(text).get("code") == "unauthorized", f"HTTP {code}")
    code, _ = request(f"{api}/ops/status")
    report.check("/ops/status closed without the ops token", code == 401, f"HTTP {code} (404 = OPS_TOKEN not set on the API)")

    code, text = request(f"{api}/ops/status", headers={"authorization": f"Bearer {token}"})
    status = parse(text)
    if report.check("/ops/status with the ops token", code == 200, f"HTTP {code}, status {status.get('status')}"):
        commit, workers = status.get("commit", ""), status.get("workers", {})
        if args.expect_commit:
            report.check("API commit", same_commit(args.expect_commit, commit), f"{commit}, expected {args.expect_commit[:12]}")
        else:
            report.check("API commit is known", commit not in ("", "unknown"), commit)
        if schema:
            report.check("schema version", status.get("schema_version") == schema, f"{status.get('schema_version')}, expected {schema}")
        else:
            report.check("schema version", False, f"{status.get('schema_version')}; pass --expect-schema or install alembic")
        report.check("worker alive", workers.get("alive", 0) >= 1, f"alive {workers.get('alive')}, last beat {workers.get('last_heartbeat_age_s')} s ago")
        commits = workers.get("commits", [])
        report.check("workers run the API's commit", bool(commits) and all(same_commit(commit, w) for w in commits), f"{commits}")
        report.check("status ok", status.get("status") == "ok", f"{status.get('status')}, due {status.get('jobs', {}).get('due')}")
        config = status.get("config", {})
        report.check(
            "configuration",
            bool(config) and not config.get("problems"),
            f"ai_mode={config.get('ai_mode')} big={config.get('big_model_provider')} problems={config.get('problems')}",
        )

    code, text = request(f"{frontend}/")
    report.check("frontend /", code == 200, f"HTTP {code}")
    report.check("ops token absent from the page", token not in text)
    # The dashboard server reaches the API with the right service key: a stranger's login is refused by the API
    # (not_authenticated), not by the key check (unauthorized). The address is never registered.
    origin = f"{urlsplit(frontend).scheme}://{urlsplit(frontend).netloc}"
    code, text = request(
        f"{frontend}/api/auth/login",
        method="POST",
        headers={"origin": origin, "x-plumo-request": "1"},
        body={"email": f"smoke-{secrets.token_hex(4)}@example.invalid", "password": secrets.token_urlsafe(16)},
    )
    report.check("dashboard server reaches the API with the service key", code == 401 and parse(text).get("code") == "not_authenticated",
                 f"HTTP {code}, code {parse(text).get('code')}")

    print(f"{'passed' if not report.failed else f'{report.failed} failed'}")
    return 1 if report.failed else 0


if __name__ == "__main__":
    sys.exit(main())
