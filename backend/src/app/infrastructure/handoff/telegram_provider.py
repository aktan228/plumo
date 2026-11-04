"""Telegram notification to the manager when a dialog needs a human.

Runs in the worker from a `notify_handoff` job, after the handoff is committed. A failure
uses ProviderTransientError only when a retry is safe (connection failure or 429).
Ambiguous outcomes use ProviderDeliveryUnknown; explicit refusals use ProviderUnavailable.
"""

import html
import logging
import os

import httpx

from app.domain.errors import ProviderDeliveryUnknown, ProviderTransientError, ProviderUnavailable
from app.infrastructure.channels.base import ChannelError
from app.infrastructure.channels.telegram import _result
from app.domain.models import HandoffRequest

logger = logging.getLogger("plumo.handoff")

_REASONS = {
    "hot_lead": "🔥 Горячий клиент",
    "ready_for_meeting": "📅 Готов к встрече",
    "user_requested_human": "🙋 Просит менеджера",
    "no_knowledge": "❓ Вопрос вне базы",
    "customer_dissatisfied": "😠 Клиент недоволен",
    "agent_unclear_twice": "🤷 Агент не понял дважды",
    "model_unavailable": "⚠️ Модель недоступна, клиент ждёт ответа",
}
_ROLES = {"user": "Клиент", "assistant": "Plumo", "manager": "Менеджер"}


class TelegramHandoffProvider:
    def __init__(
        self,
        *,
        token: str | None = None,
        chat_id: str | None = None,
        dashboard_url: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.token = (token if token is not None else os.getenv("TELEGRAM_BOT_TOKEN", "")).strip()
        self.chat_id = (chat_id or "").strip()
        self.dashboard_url = (dashboard_url or os.getenv("DASHBOARD_URL", "")).rstrip("/")
        if not self.token:
            raise ProviderUnavailable("The manager bot token is required")
        self._client = httpx.AsyncClient(timeout=10.0, transport=transport)

    async def notify(self, handoff: HandoffRequest) -> None:
        if not self.chat_id:
            raise ProviderUnavailable("A tenant-specific recipient is required")
        await self.notify_to(handoff, self.chat_id)

    async def notify_to(self, handoff: HandoffRequest, chat_id: str) -> None:
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        body = {
            "chat_id": chat_id,
            "text": render(handoff, self.dashboard_url),
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        try:
            response = await self._client.post(url, json=body)
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout):
            logger.warning("telegram_unreachable", extra={"handoff_id": str(handoff.id)})
            raise ProviderTransientError("Telegram is unreachable") from None
        except httpx.HTTPError:
            raise ProviderDeliveryUnknown("Telegram delivery outcome is unknown") from None
        try:
            result = _result(response, sends=True)
        except ChannelError as exc:
            if exc.kind == "ambiguous":
                raise ProviderDeliveryUnknown("Telegram delivery outcome is unknown") from None
            if exc.retryable:
                raise ProviderTransientError("Telegram temporarily refused the notification") from None
            raise ProviderUnavailable("Telegram refused the notification") from None
        if not isinstance(result, dict) or type(result.get("message_id")) is not int or result["message_id"] <= 0:
            raise ProviderDeliveryUnknown("Telegram delivery outcome is unknown")

    async def aclose(self) -> None:
        await self._client.aclose()


def render(handoff: HandoffRequest, dashboard_url: str = "") -> str:
    """Short card a manager can act on from the phone lock screen."""

    title = _REASONS.get(handoff.reason, f"Передача: {handoff.reason}")
    lines = [f"<b>{html.escape(title)}</b>"]
    if handoff.summary:
        lines.append(html.escape(handoff.summary[:300]))
    recent = handoff.recent_messages[-4:]
    if recent:
        lines.append("")
        for item in recent:
            who = _ROLES.get(str(item.get("role")), "?")
            lines.append(f"<b>{who}:</b> {html.escape(str(item.get('text') or '')[:200])}")
    lines.append("")
    if dashboard_url:
        lines.append(f'<a href="{html.escape(dashboard_url, quote=True)}/dashboard?conversation={handoff.conversation_id}#chats">Открыть диалог</a>')
    lines.append(f"<code>{handoff.id}</code>")
    return "\n".join(lines)
