"""One entry point for the services: which client serves a connection, and how to send text."""

import base64
import hashlib
import hmac
import os
from uuid import UUID

import httpx

from app.domain.models import ChannelConnection
from app.infrastructure.channels.base import ChannelError
from app.infrastructure.channels.credentials import ChannelCredential, CredentialStore
from app.infrastructure.channels.instagram import InstagramClient
from app.infrastructure.channels.telegram import TelegramClient


class ChannelGateway:
    """Builds provider clients from server credentials. Tests pass an httpx transport."""

    def __init__(
        self,
        credentials: CredentialStore,
        *,
        instagram_api_version: str = "v25.0",
        timeout_s: float = 15.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.credentials = credentials
        self.instagram_api_version = instagram_api_version
        self.timeout_s = timeout_s
        self.transport = transport

    def telegram(self, token: str) -> TelegramClient:
        return TelegramClient(token, timeout_s=self.timeout_s, transport=self.transport)

    def instagram(self, token: str) -> InstagramClient:
        return InstagramClient(
            token, api_version=self.instagram_api_version, timeout_s=self.timeout_s, transport=self.transport
        )

    def credential(self, connection: ChannelConnection) -> ChannelCredential:
        found = self.credentials.get(connection.credential_ref, connection.business_id, connection.channel)
        if found is None:
            raise ChannelError("auth", "credential_missing", "server credential is no longer available")
        return found

    def token(self, connection: ChannelConnection) -> str:
        secret = self.credential(connection).secret()
        if not secret:
            raise ChannelError("auth", "credential_empty", "server credential has no token")
        return secret

    async def send_text(self, connection: ChannelConnection, chat_id: str, text: str) -> str:
        token = self.token(connection)
        if connection.channel == "telegram":
            client = self.telegram(token)
            try:
                return await client.send_message(chat_id, text)
            finally:
                await client.aclose()
        if connection.channel == "instagram":
            client = self.instagram(token)
            try:
                return await client.send_message(chat_id, text)
            finally:
                await client.aclose()
        raise ChannelError("bad_request", "channel_unsupported", f"no adapter for {connection.channel}")


def channel_secret_key() -> str:
    return os.getenv("CHANNEL_SECRET_KEY", "").strip()


def telegram_webhook_secret(connection_id: UUID, nonce: str, key: str | None = None) -> str:
    """Secret for setWebhook, derived instead of stored: HMAC(CHANNEL_SECRET_KEY, id + nonce).

    Base64url without padding fits Telegram's A-Za-z0-9_- rule (43 characters).
    """

    secret_key = key if key is not None else channel_secret_key()
    if not secret_key:
        raise ValueError("CHANNEL_SECRET_KEY is not set")
    digest = hmac.new(secret_key.encode(), f"telegram:{connection_id}:{nonce}".encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")
