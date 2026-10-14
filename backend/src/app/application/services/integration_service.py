"""Connect, check, switch and disconnect a business's Telegram bot and Instagram account.

Secrets are prepared on the server (CHANNEL_CREDENTIALS_FILE); the dashboard
chooses one by name. A saved form never means "connected": only a verified
account with a working webhook or subscription does.
"""

import logging
import os
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from app.domain.enums import ConnectionStatus
from app.domain.errors import (
    ChannelLimit,
    ChannelUnavailable,
    CredentialNotFound,
    IntegrationConflict,
    IntegrationNotFound,
    InvalidState,
    NotConfigured,
    VersionConflict,
)
from app.domain.models import ChannelConnection, utcnow
from app.infrastructure.channels.base import AccountInfo, ChannelError
from app.infrastructure.channels.gateway import channel_secret_key, telegram_webhook_secret

logger = logging.getLogger("plumo.integrations")

CHANNELS = ("telegram", "instagram")


@dataclass(slots=True)
class ChannelOverview:
    channel: str
    status: str
    connection: ChannelConnection | None
    credentials: list[tuple[str, str]]
    # Server settings this channel needs, without values: {"public_url": True, ...}.
    requirements: dict[str, bool] = field(default_factory=dict)
    webhook_url: str | None = None


class IntegrationService:
    def __init__(self, *, session, connections, outbound, gateway, settings) -> None:
        self.session = session
        self.connections = connections
        self.outbound = outbound
        self.gateway = gateway
        self.settings = settings

    # ---- read -------------------------------------------------------------------------

    async def overview(self, business_id: UUID) -> list[ChannelOverview]:
        rows = await self.connections.list_for_business(business_id)
        result = []
        for channel in CHANNELS:
            mine = [item for item in rows if item.channel == channel]
            active = next((item for item in mine if item.status != ConnectionStatus.disconnected), None)
            shown = active or (mine[0] if mine else None)
            status = shown.status if shown else ConnectionStatus.not_connected
            result.append(
                ChannelOverview(
                    channel=channel,
                    status=status,
                    connection=shown,
                    credentials=[
                        (item.ref, item.label) for item in self.gateway.credentials.available(business_id, channel)
                    ],
                    requirements=self._requirements(channel),
                    webhook_url=self._instagram_callback() if channel == "instagram" else None,
                )
            )
        return result

    async def get(self, connection_id: UUID, business_id: UUID) -> ChannelConnection:
        connection = await self.connections.get_for_business(connection_id, business_id)
        if connection is None:
            raise IntegrationNotFound(f"integration {connection_id} was not found")
        return connection

    # ---- connect ----------------------------------------------------------------------

    async def connect_telegram(self, business_id: UUID, credential_ref: str, replace_webhook: bool = False) -> ChannelConnection:
        base = self._public_base()
        if not channel_secret_key():
            raise NotConfigured("CHANNEL_SECRET_KEY is not set on the server", code="secret_key_missing")
        token = self._token(business_id, "telegram", credential_ref)
        client = self.gateway.telegram(token)
        try:
            try:
                account = await client.get_me()
            except ChannelError as exc:
                raise _app_error(exc) from None
            connection = await self._claim(business_id, "telegram", credential_ref, account)
            connection.webhook_nonce = secrets.token_hex(16)
            connection = await self._save_and_commit(connection)

            url = f"{base}/api/v1/webhooks/telegram/{connection.id}"
            try:
                info = await client.get_webhook_info()
                current = str(info.get("url") or "")
                if current and current != url and not replace_webhook:
                    # Another system (or an old tunnel address) receives this bot's updates.
                    host = urlsplit(current).hostname or "?"
                    await self._problem(
                        connection,
                        ConnectionStatus.action_required,
                        "webhook_conflict",
                        f"Webhook бота уже указывает на {host}. Подтвердите замену, если это старая настройка Plumo.",
                        details={"conflict_host": host},
                    )
                    raise IntegrationConflict(
                        f"the bot's webhook points to {host}; confirm replacement to continue", code="webhook_conflict"
                    )
                await client.set_webhook(url, telegram_webhook_secret(connection.id, connection.webhook_nonce))
                info = await client.get_webhook_info()
            except ChannelError as exc:
                await self._from_channel_error(connection, exc)
                raise _app_error(exc) from None
            if str(info.get("url") or "") != url:
                await self._problem(connection, ConnectionStatus.error, "webhook_not_set", "Telegram не подтвердил webhook")
                raise ChannelUnavailable("Telegram did not confirm the webhook", code="webhook_not_set")
            connection.status = ConnectionStatus.connected
            connection.details = {
                **connection.details,
                "webhook_host": urlsplit(url).hostname,
                "pending_update_count": int(info.get("pending_update_count") or 0),
                "conflict_host": None,
            }
            _ok(connection)
            connection = await self._save_and_commit(connection)
            logger.info("telegram_connected", extra={"connection_id": str(connection.id)})
            return connection
        finally:
            await client.aclose()

    async def connect_instagram(self, business_id: UUID, credential_ref: str) -> ChannelConnection:
        self._public_base()
        if not os.getenv("INSTAGRAM_APP_SECRET", "").strip() or not os.getenv("INSTAGRAM_VERIFY_TOKEN", "").strip():
            raise NotConfigured(
                "INSTAGRAM_APP_SECRET and INSTAGRAM_VERIFY_TOKEN are not set on the server",
                code="instagram_app_not_configured",
            )
        token = self._token(business_id, "instagram", credential_ref)
        client = self.gateway.instagram(token)
        try:
            try:
                account = await client.get_me()
            except ChannelError as exc:
                raise _app_error(exc) from None
            connection = await self._claim(business_id, "instagram", credential_ref, account)
            connection.details = {
                **connection.details,
                "account_type": account.details.get("account_type"),
                "api_version": self.settings.instagram_api_version,
            }
            connection = await self._save_and_commit(connection)
            try:
                await client.subscribe_messages()
            except ChannelError as exc:
                await self._from_channel_error(connection, exc)
                raise _app_error(exc) from None
            connection.status = ConnectionStatus.connected
            _ok(connection)
            connection = await self._save_and_commit(connection)
            logger.info("instagram_connected", extra={"connection_id": str(connection.id)})
            return connection
        finally:
            await client.aclose()

    # ---- check / switch / disconnect --------------------------------------------------

    async def check(self, connection_id: UUID, business_id: UUID) -> ChannelConnection:
        connection = await self.get(connection_id, business_id)
        if connection.status == ConnectionStatus.disconnected:
            raise InvalidState("the integration is disconnected; connect it again", code="integration_disconnected")
        try:
            token = self.gateway.token(connection)
        except ChannelError as exc:
            await self._from_channel_error(connection, exc)
            return await self.get(connection_id, business_id)
        try:
            if connection.channel == "telegram":
                await self._check_telegram(connection, token)
            else:
                await self._check_instagram(connection, token)
        except ChannelError as exc:
            await self._from_channel_error(connection, exc)
        return await self.get(connection_id, business_id)

    async def _check_telegram(self, connection: ChannelConnection, token: str) -> None:
        client = self.gateway.telegram(token)
        try:
            await client.get_me()
            info = await client.get_webhook_info()
        finally:
            await client.aclose()
        expected = f"{self.settings.webhook_base_url}/api/v1/webhooks/telegram/{connection.id}"
        current = str(info.get("url") or "")
        details = {
            **connection.details,
            "pending_update_count": int(info.get("pending_update_count") or 0),
            "telegram_last_error": str(info.get("last_error_message") or "")[:200] or None,
        }
        if not current:
            await self._problem(connection, ConnectionStatus.error, "webhook_missing", "Webhook не установлен", details)
            return
        if current != expected:
            host = urlsplit(current).hostname or "?"
            details["conflict_host"] = host
            await self._problem(
                connection,
                ConnectionStatus.action_required,
                "webhook_conflict",
                f"Webhook бота указывает на {host}, а не на этот сервер. Подключите заново.",
                details,
            )
            return
        error_at = info.get("last_error_date")
        if error_at:
            failed_at = datetime.fromtimestamp(int(error_at), tz=UTC)
            recent = utcnow() - failed_at < timedelta(minutes=15)
            if recent and (connection.last_event_at is None or connection.last_event_at < failed_at):
                await self._problem(
                    connection,
                    ConnectionStatus.error,
                    "webhook_delivery_failing",
                    f"Telegram не может доставить обновления: {details['telegram_last_error'] or 'ошибка'}",
                    details,
                )
                return
        connection.status = ConnectionStatus.connected
        connection.details = details
        _ok(connection)
        await self._save_and_commit(connection)

    async def _check_instagram(self, connection: ChannelConnection, token: str) -> None:
        client = self.gateway.instagram(token)
        try:
            account = await client.get_me()
            if account.external_account_id != connection.external_account_id:
                await self._problem(
                    connection,
                    ConnectionStatus.action_required,
                    "account_changed",
                    "Токен принадлежит другому аккаунту Instagram",
                )
                return
            await client.subscribe_messages()
        finally:
            await client.aclose()
        connection.status = ConnectionStatus.connected
        _ok(connection)
        await self._save_and_commit(connection)

    async def set_agent(self, connection_id: UUID, business_id: UUID, enabled: bool, version: int | None) -> ChannelConnection:
        connection = await self.connections.lock(connection_id)
        if connection is None or connection.business_id != business_id:
            raise IntegrationNotFound(f"integration {connection_id} was not found")
        if version is not None and version != connection.version:
            raise VersionConflict("the integration was changed meanwhile; reload")
        if connection.status == ConnectionStatus.disconnected:
            raise InvalidState("the integration is disconnected", code="integration_disconnected")
        if connection.agent_enabled != enabled:
            connection.agent_enabled = enabled
            connection.version += 1
            connection = await self.connections.save(connection)
        await self.session.commit()
        return connection

    async def disconnect(self, connection_id: UUID, business_id: UUID) -> ChannelConnection:
        """Stop receiving and sending. History stays; queued replies are cancelled, not kept for later."""

        connection = await self.connections.lock(connection_id)
        if connection is None or connection.business_id != business_id:
            raise IntegrationNotFound(f"integration {connection_id} was not found")
        if connection.status == ConnectionStatus.disconnected:
            await self.session.commit()
            return connection
        warning = await self._release_provider(connection)
        now = utcnow()
        connection.status = ConnectionStatus.disconnected
        connection.agent_enabled = False
        connection.webhook_nonce = None
        connection.disconnected_at = now
        connection.version += 1
        connection.details = {**connection.details, "disconnect_warning": warning}
        connection = await self.connections.save(connection)
        cancelled = await self.outbound.cancel_queued_for_connection(connection.id, "channel_disconnected")
        await self.session.commit()
        logger.info(
            "integration_disconnected", extra={"connection_id": str(connection.id), "cancelled_replies": cancelled}
        )
        return connection

    async def _release_provider(self, connection: ChannelConnection) -> str | None:
        """Remove only our own webhook/subscription. A failure here does not block the disconnect."""

        try:
            token = self.gateway.token(connection)
        except ChannelError:
            return "credential_missing"
        try:
            if connection.channel == "telegram":
                client = self.gateway.telegram(token)
                try:
                    info = await client.get_webhook_info()
                    ours = f"/api/v1/webhooks/telegram/{connection.id}"
                    if str(info.get("url") or "").endswith(ours):
                        await client.delete_webhook()
                finally:
                    await client.aclose()
            else:
                client = self.gateway.instagram(token)
                try:
                    await client.unsubscribe()
                finally:
                    await client.aclose()
        except ChannelError as exc:
            return exc.code
        return None

    # ---- helpers ----------------------------------------------------------------------

    async def _claim(self, business_id: UUID, channel: str, credential_ref: str, account: AccountInfo) -> ChannelConnection:
        """The row for this account: reuse it on reconnect, refuse another business's account."""

        other = await self.connections.active_by_account(channel, account.external_account_id)
        if other is not None and other.business_id != business_id:
            raise IntegrationConflict("this account is connected to another business", code="account_in_use")
        current = await self.connections.active(business_id, channel)
        if current is not None and current.external_account_id != account.external_account_id:
            raise IntegrationConflict(
                f"another {channel} account is connected; disconnect it first", code="already_connected"
            )
        connection = current or await self.connections.find_account(business_id, channel, account.external_account_id)
        now = utcnow()
        if connection is None:
            connection = ChannelConnection(
                id=uuid4(),
                business_id=business_id,
                channel=channel,
                credential_ref=credential_ref,
                external_account_id=account.external_account_id,
                display_name=account.display_name,
                username=account.username,
                status=ConnectionStatus.connecting,
                agent_enabled=False,
                version=1,
                created_at=now,
                updated_at=now,
            )
        elif connection.status == ConnectionStatus.disconnected:
            # Reconnect: history comes back, old queued replies stay cancelled, the agent starts off.
            connection.agent_enabled = False
            connection.disconnected_at = None
            connection.version += 1
        connection.credential_ref = credential_ref
        connection.display_name = account.display_name
        connection.username = account.username
        connection.status = ConnectionStatus.connecting
        connection.details = {key: value for key, value in connection.details.items() if key != "disconnect_warning"}
        return connection

    async def _save_and_commit(self, connection: ChannelConnection) -> ChannelConnection:
        saved = await self.connections.save(connection)
        await self.session.commit()
        return saved

    async def _problem(self, connection, status: str, code: str, message: str, details: dict | None = None) -> None:
        now = utcnow()
        connection.status = status
        connection.last_check_at = now
        connection.last_check_ok = False
        connection.last_error_code = code
        connection.last_error_message = message
        connection.last_error_at = now
        if details is not None:
            connection.details = details
        connection.version += 1
        await self._save_and_commit(connection)

    async def _from_channel_error(self, connection: ChannelConnection, exc: ChannelError) -> None:
        status = ConnectionStatus.action_required if exc.needs_action else ConnectionStatus.error
        await self._problem(connection, status, exc.code, _human(exc))

    def _token(self, business_id: UUID, channel: str, ref: str) -> str:
        credential = self.gateway.credentials.get(ref, business_id, channel)
        if credential is None:
            raise CredentialNotFound(f"no prepared {channel} credential '{ref}' for this business")
        token = credential.secret()
        if not token:
            raise NotConfigured(f"credential '{ref}' has no token on the server", code="credential_empty")
        return token

    def _public_base(self) -> str:
        base = self.settings.webhook_base_url
        if not base.startswith("https://"):
            raise NotConfigured("PUBLIC_BASE_URL must be a public https:// address", code="public_url_missing")
        return base

    def _instagram_callback(self) -> str | None:
        base = self.settings.webhook_base_url
        return f"{base}/api/v1/webhooks/instagram" if base else None

    def _requirements(self, channel: str) -> dict[str, bool]:
        ready = {
            "public_url": self.settings.webhook_base_url.startswith("https://"),
            "credentials_file": self.gateway.credentials.configured,
        }
        if channel == "telegram":
            ready["secret_key"] = bool(channel_secret_key())
        else:
            ready["app_secret"] = bool(os.getenv("INSTAGRAM_APP_SECRET", "").strip())
            ready["verify_token"] = bool(os.getenv("INSTAGRAM_VERIFY_TOKEN", "").strip())
        return ready


def _ok(connection: ChannelConnection) -> None:
    connection.last_check_at = utcnow()
    connection.last_check_ok = True
    connection.last_error_code = None
    connection.last_error_message = None
    connection.version += 1


_HUMAN = {
    "token_invalid": "Токен недействителен или отозван. Замените его на сервере и подключите снова.",
    "credential_missing": "Серверная конфигурация больше недоступна этому бизнесу.",
    "credential_empty": "В серверной конфигурации нет токена.",
    "missing_permission": "У приложения нет нужных прав или роли для этого аккаунта.",
    "subscription_failed": "Meta не подтвердила подписку на сообщения.",
}


def _human(exc: ChannelError) -> str:
    if exc.code in _HUMAN:
        return _HUMAN[exc.code]
    if exc.kind in ("transient", "ambiguous", "rate_limited"):
        return "Сервис канала временно недоступен. Повторите проверку позже."
    return exc.message


def _app_error(exc: ChannelError):
    if exc.kind == "auth":
        return ChannelLimit(_human(exc), code="invalid_credential")
    if exc.kind == "permission":
        return ChannelLimit(_human(exc), code="missing_permission")
    if exc.kind in ("transient", "ambiguous", "rate_limited"):
        return ChannelUnavailable(_human(exc), code=exc.code)
    return ChannelLimit(_human(exc), code=exc.code)
