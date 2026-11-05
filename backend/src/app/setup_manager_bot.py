"""Compatibility only: point the service bot at the older /webhooks/manager-telegram endpoint.

The recommended setup is `python -m app.manager_bot` (docs/manager-notifications.md). This
command stays for a stand that was configured for the older Dashboard webhook. Never runs at startup.
"""
import asyncio
import os
import re
from urllib.parse import urlsplit

from app.application.services.manager_recipient import manager_configured, manager_token
from app.application.services.manager_recipients import service_bot_username
from app.config import get_settings
from app.infrastructure.channels.telegram import TelegramClient
from app.infrastructure.logging.setup import setup_logging


async def main():
    setup_logging("WARNING")
    secret = os.getenv("MANAGER_WEBHOOK_SECRET", "").strip()
    if not manager_configured() or not re.fullmatch(r"[A-Za-z0-9_-]{32,256}", secret):
        raise SystemExit("Set the service bot token and username and MANAGER_WEBHOOK_SECRET first.")
    base = get_settings().public_base_url.strip().rstrip("/")
    parsed = urlsplit(base)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise SystemExit("PUBLIC_BASE_URL must be the public HTTPS API address.")
    client = TelegramClient(manager_token())
    try:
        account = await client.get_me()
        if (account.username or "").lower() != (service_bot_username() or "").lower():
            raise SystemExit("The bot username does not match the configured token.")
        target = f"{base}/api/v1/webhooks/manager-telegram"
        previous = await client.get_webhook_info()
        if previous.get("url") not in (None, "", target):
            raise SystemExit("The bot has another webhook. Use a dedicated notification bot; no changes made.")
        await client.set_webhook(target, secret)
        print("Manager bot webhook configured. Verify a binding from the dashboard.")
    except Exception:
        raise SystemExit("Telegram setup failed. Check token, API address and availability; no secrets are printed.") from None
    finally:
        await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
