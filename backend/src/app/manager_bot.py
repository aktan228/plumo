"""Point the service bot (manager notifications) at this server. Run once per stand.

    python -m app.manager_bot              # setWebhook to PUBLIC_BASE_URL, prints the bot's username
    python -m app.manager_bot --check      # only shows where the webhook points now

Needs TELEGRAM_BOT_TOKEN (the service bot, not a business bot), CHANNEL_SECRET_KEY and
PUBLIC_BASE_URL. Put the printed username into TELEGRAM_BOT_USERNAME so the dashboard can
give managers a one-tap link.
"""

import argparse
import asyncio
import os
import sys

from app.application.services.manager_recipients import manager_webhook_secret
from app.config import get_settings
from app.infrastructure.channels.base import ChannelError
from app.infrastructure.channels.gateway import channel_secret_key
from app.infrastructure.channels.telegram import TelegramClient

PATH = "/api/v1/webhooks/telegram-manager"


async def main(check: bool) -> int:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    key = channel_secret_key()
    base = get_settings().webhook_base_url
    missing = [name for name, value in (("TELEGRAM_BOT_TOKEN", token), ("CHANNEL_SECRET_KEY", key), ("PUBLIC_BASE_URL", base)) if not value]
    if missing and not (check and token):
        print(f"Missing: {', '.join(missing)}")
        return 1
    client = TelegramClient(token)
    try:
        bot = await client.get_me()
        print(f"Service bot: @{bot.username}  (TELEGRAM_BOT_USERNAME={bot.username})")
        if not check:
            await client.set_webhook(base + PATH, manager_webhook_secret(key))
        info = await client.get_webhook_info()
        print(f"Webhook: {info.get('url') or '(none)'}  pending updates: {info.get('pending_update_count', 0)}")
        if info.get("last_error_message"):
            print(f"Last Telegram error: {info['last_error_message']}")
    except ChannelError as exc:
        print(f"Telegram refused: {exc.code}")
        return 1
    finally:
        await client.aclose()
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Plumo service bot webhook")
    parser.add_argument("--check", action="store_true", help="show the current webhook, change nothing")
    sys.exit(asyncio.run(main(parser.parse_args().check)))
