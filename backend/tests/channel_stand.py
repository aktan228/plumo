"""Test stand helpers: Telegram and Meta faked at the HTTP level, real webhooks, worker and dashboard API."""

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

import httpx
from httpx import AsyncClient
from sqlalchemy import text

from app.container import Runtime
from app.domain.models import Business, ChannelConnection
from app.infrastructure.channels.gateway import telegram_webhook_secret
from app.infrastructure.database.channel_repositories import ConnectionRepository
from app.infrastructure.database.session import create_session_factory
from app.worker import Worker

TG_TOKEN = "123456789:AAtest-token-value_abcdefghijk"
IG_TOKEN = "IGQVJtest-instagram-token-value"
APP_SECRET = "ig-app-secret"


class FakeProviders:
    """Telegram Bot API and graph.instagram.com in memory. Tests queue failures per method."""

    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.calls: list[str] = []
        self.failures: dict[str, list] = {}
        self.webhook_url = ""
        self.bot = {"id": 777000, "is_bot": True, "first_name": "Plumo Test", "username": "plumo_test_bot"}
        self.ig_account = {"user_id": "17841400000000001", "username": "plumo.test", "name": "Plumo Test"}
        self._next_id = 100
        # Telegram files by file_id: the bytes getFile + /file/bot<token>/<path> return.
        self.files: dict[str, bytes] = {}

    def fail(self, method: str, *responses) -> None:
        """Queue responses for `method`: (status, body) tuples or exceptions to raise."""

        self.failures.setdefault(method, []).extend(responses)

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.telegram.org" and request.url.path.startswith("/file/"):
            self.calls.append("download")
            queued = self.failures.get("download")
            if queued:
                item = queued.pop(0)
                if isinstance(item, Exception):
                    raise item
                return httpx.Response(item[0], json=item[1])
            file_id = request.url.path.rsplit("/", 1)[-1]
            content = self.files.get(file_id)
            return httpx.Response(200, content=content) if content is not None else httpx.Response(404)
        if request.url.host == "api.telegram.org":
            method = request.url.path.rsplit("/", 1)[-1]
            body = json.loads(request.content or b"{}")
        else:
            method = "ig:" + request.url.path.split("/", 2)[-1]
            body = json.loads(request.content) if request.content else {}
        self.calls.append(method)
        queued = self.failures.get(method)
        if queued:
            item = queued.pop(0)
            if isinstance(item, Exception):
                raise item
            status, payload = item
            return httpx.Response(status, json=payload)
        return self._ok(method, body)

    def _ok(self, method: str, body: dict) -> httpx.Response:
        if method == "getMe":
            return httpx.Response(200, json={"ok": True, "result": self.bot})
        if method == "getWebhookInfo":
            return httpx.Response(200, json={"ok": True, "result": {"url": self.webhook_url, "pending_update_count": 0}})
        if method == "setWebhook":
            self.webhook_url = body["url"]
            return httpx.Response(200, json={"ok": True, "result": True})
        if method == "deleteWebhook":
            self.webhook_url = ""
            return httpx.Response(200, json={"ok": True, "result": True})
        if method == "getFile":
            content = self.files.get(body["file_id"])
            if content is None:
                return httpx.Response(400, json={"ok": False, "description": "Bad Request: invalid file_id"})
            path = f"voice/{body['file_id']}"
            return httpx.Response(200, json={"ok": True, "result": {"file_id": body["file_id"], "file_unique_id": "u", "file_size": len(content), "file_path": path}})
        if method == "sendMessage":
            self._next_id += 1
            self.sent.append({"channel": "telegram", "chat_id": str(body["chat_id"]), "text": body["text"]})
            return httpx.Response(200, json={"ok": True, "result": {"message_id": self._next_id}})
        if method == "ig:me":
            return httpx.Response(200, json=self.ig_account)
        if method == "ig:me/subscribed_apps":
            return httpx.Response(200, json={"success": True})
        if method == "ig:me/messages":
            self._next_id += 1
            self.sent.append({"channel": "instagram", "chat_id": body["recipient"]["id"], "text": body["message"]["text"]})
            return httpx.Response(200, json={"recipient_id": body["recipient"]["id"], "message_id": f"mid.{self._next_id}"})
        return httpx.Response(404, json={"ok": False, "description": f"unexpected {method}"})


class FakeSTT:
    """api.elevenlabs.io/v1/speech-to-text in memory: transcripts by audio bytes, queued failures."""

    def __init__(self) -> None:
        self.transcripts: dict[bytes, dict] = {}
        self.failures: list = []
        self.requests: list[dict] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = request.read()
        self.requests.append({"key": request.headers.get("xi-api-key"), "size": len(body), "query": dict(request.url.params)})
        if self.failures:
            item = self.failures.pop(0)
            if isinstance(item, Exception):
                raise item
            return httpx.Response(item, json={"detail": {"status": "error", "message": "fake failure"}})
        for audio, result in self.transcripts.items():
            if audio in body:
                return httpx.Response(200, json=result)
        return httpx.Response(200, json={"text": "", "language_code": "rus", "language_probability": 0.5, "words": []})


@dataclass
class Stand:
    client: AsyncClient
    runtime: Runtime
    providers: FakeProviders
    business: Business
    engine: object
    worker: Worker
    app: object
    tokens: dict = field(default_factory=dict)

    @property
    def factory(self):
        return create_session_factory(self.engine)

    async def telegram(self, *, agent_enabled: bool = True, business_id: UUID | None = None) -> ChannelConnection:
        now = datetime.now(UTC)
        connection = ChannelConnection(
            id=uuid4(),
            business_id=business_id or self.business.id,
            channel="telegram",
            credential_ref="tg-test" if business_id is None else "tg-other",
            external_account_id=str(self.providers.bot["id"]) if business_id is None else str(uuid4().int)[:9],
            display_name="Plumo Test",
            username="plumo_test_bot",
            status="connected",
            agent_enabled=agent_enabled,
            version=1,
            created_at=now,
            updated_at=now,
            webhook_nonce=uuid4().hex,
        )
        async with self.factory() as session:
            saved = await ConnectionRepository(session).save(connection)
            await session.commit()
        return saved

    async def instagram(self, *, agent_enabled: bool = True) -> ChannelConnection:
        now = datetime.now(UTC)
        connection = ChannelConnection(
            id=uuid4(),
            business_id=self.business.id,
            channel="instagram",
            credential_ref="ig-test",
            external_account_id=self.providers.ig_account["user_id"],
            display_name="Plumo Test",
            username="plumo.test",
            status="connected",
            agent_enabled=agent_enabled,
            version=1,
            created_at=now,
            updated_at=now,
        )
        async with self.factory() as session:
            saved = await ConnectionRepository(session).save(connection)
            await session.commit()
        return saved

    async def tg_update(self, connection: ChannelConnection, update_id: int, text: str | None = "Здравствуйте", *, chat_id: int = 5550001, secret: str | None = None, **message):
        body = {
            "update_id": update_id,
            "message": {
                "message_id": update_id,
                "date": 1760000000,
                "chat": {"id": chat_id, "type": "private"},
                "from": {"id": chat_id, "is_bot": False, "first_name": "Айгуль"},
                **({"text": text} if text is not None else {}),
                **message,
            },
        }
        header = secret if secret is not None else telegram_webhook_secret(connection.id, connection.webhook_nonce)
        return await self.client.post(
            f"/api/v1/webhooks/telegram/{connection.id}",
            json=body,
            headers={"X-Telegram-Bot-Api-Secret-Token": header},
        )

    async def ig_webhook(self, payload: dict, *, secret: str = APP_SECRET):
        import hashlib
        import hmac

        raw = json.dumps(payload).encode()
        signature = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
        return await self.client.post(
            "/api/v1/webhooks/instagram",
            content=raw,
            headers={"X-Hub-Signature-256": signature, "Content-Type": "application/json"},
        )

    async def sql(self, statement: str, **params):
        async with self.factory() as session:
            result = await session.execute(text(statement), params)
            rows = result.all() if result.returns_rows else None
            await session.commit()
            return rows
