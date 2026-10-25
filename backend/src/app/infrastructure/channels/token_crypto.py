"""Authenticated encryption bound to a business and connection, using the existing server secret."""

import base64
import hashlib
import hmac
import os

from cryptography.fernet import Fernet, InvalidToken

from app.infrastructure.channels.base import ChannelError


def cipher(business_id, connection_id):
    secret = os.getenv("CHANNEL_SECRET_KEY", "").strip()
    if not secret:
        raise ChannelError("auth", "secret_key_missing", "channel encryption key is not configured")
    context = f"plumo:bot-token:v1:{business_id}:{connection_id}".encode()
    key = hmac.new(secret.encode(), context, hashlib.sha256).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_token(token, business_id, connection_id):
    return "v1." + cipher(business_id, connection_id).encrypt(token.encode()).decode()


def decrypt_token(value, business_id, connection_id):
    try:
        if not value.startswith("v1."):
            raise ValueError("version")
        return cipher(business_id, connection_id).decrypt(value[3:].encode()).decode()
    except (InvalidToken, ValueError, UnicodeError):
        raise ChannelError("auth", "credential_decryption_failed", "Stored bot token cannot be opened; enter it again") from None
