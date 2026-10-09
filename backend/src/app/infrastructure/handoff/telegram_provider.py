"""Telegram notification to the manager when a dialog needs a human.

The handoff row is already stored when this runs. A Telegram outage must not
break the customer's reply, so failures are logged, not raised.
"""

import html
import logging
import os

import httpx

from app.domain.errors import ProviderUnavailable
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
        self.chat_id = (chat_id if chat_id is not None else os.getenv("TELEGRAM_MANAGER_CHAT_ID", "")).strip()
        self.dashboard_url = (dashboard_url or os.getenv("DASHBOARD_URL", "")).rstrip("/")
        if not self.token or not self.chat_id:
            raise ProviderUnavailable("TELEGRAM_BOT_TOKEN and TELEGRAM_MANAGER_CHAT_ID are required")
        self._client = httpx.AsyncClient(timeout=10.0, transport=transport)

    async def notify(self, handoff: HandoffRequest) -> None:
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        body = {
            "chat_id": self.chat_id,
            "text": render(handoff, self.dashboard_url),
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        try:
            response = await self._client.post(url, json=body)
            if response.status_code >= 400:
                logger.warning("telegram_notify_failed", extra={"status": response.status_code, "handoff_id": str(handoff.id)})
        except httpx.HTTPError:
            logger.warning("telegram_unreachable", extra={"handoff_id": str(handoff.id)})

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
        lines.append(f'<a href="{dashboard_url}/conversations/{handoff.conversation_id}">Открыть диалог</a>')
    lines.append(f"<code>{handoff.id}</code>")
    return "\n".join(lines)
