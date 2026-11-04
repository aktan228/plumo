"""Explicit operator command: configure the dedicated manager bot webhook. Never runs at startup."""
import asyncio
import os
from urllib.parse import urlsplit

from app.application.services.manager_recipient import manager_configured, manager_token
from app.config import get_settings
from app.infrastructure.channels.telegram import TelegramClient
from app.infrastructure.logging.setup import setup_logging


async def main():
    setup_logging("WARNING")
    if not manager_configured():
        raise SystemExit("Set MANAGER_BOT_TOKEN, MANAGER_BOT_USERNAME and MANAGER_WEBHOOK_SECRET first.")
    base = get_settings().public_base_url.strip().rstrip("/")
    parsed = urlsplit(base)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise SystemExit("PUBLIC_BASE_URL must be the public HTTPS API address.")
    client = TelegramClient(manager_token())
    try:
        account = await client.get_me()
        if (account.username or "").lower() != os.environ["MANAGER_BOT_USERNAME"].lower():
            raise SystemExit("MANAGER_BOT_USERNAME does not match the configured token.")
        target = f"{base}/api/v1/webhooks/manager-telegram"
        previous = await client.get_webhook_info()
        if previous.get("url") not in (None, "", target):
            raise SystemExit("The bot has another webhook. Use a dedicated notification bot; no changes made.")
        await client.set_webhook(target, os.environ["MANAGER_WEBHOOK_SECRET"])
        print("Manager bot webhook configured. Verify a binding from the dashboard.")
    except Exception:
        raise SystemExit("Telegram setup failed. Check token, API address and availability; no secrets are printed.") from None
    finally:
        await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
