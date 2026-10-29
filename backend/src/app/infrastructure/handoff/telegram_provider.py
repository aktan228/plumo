"""Telegram notification to the manager when a dialog needs a human.

Runs in the worker from a `notify_handoff` job, after the handoff is committed. The chat
is the business's confirmed recipient (`manager_recipients`), passed in by the caller; this
class knows only the service bot's token. A failure is raised so the job retries:
ProviderTransientError for a network error, 429 or 5xx, ProviderUnavailable for any other
refusal (chat not found, bot blocked by the manager, revoked token).
"""

import html
import logging
import os

import httpx

from app.domain.errors import DeliveryUnknown, ProviderTransientError, ProviderUnavailable
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
        dashboard_url: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.token = (token if token is not None else os.getenv("TELEGRAM_BOT_TOKEN", "")).strip()
        self.dashboard_url = (dashboard_url or os.getenv("DASHBOARD_URL", "")).rstrip("/")
        if not self.token:
            raise ProviderUnavailable("TELEGRAM_BOT_TOKEN of the service bot is required")
        self._client = httpx.AsyncClient(timeout=10.0, transport=transport)

    async def notify(self, handoff: HandoffRequest, chat_id: str) -> None:
        await self._send(chat_id, render(handoff, self.dashboard_url), "HTML", str(handoff.id))

    async def send_text(self, chat_id: str, text: str) -> None:
        await self._send(chat_id, text, None, "")

    async def _send(self, chat_id: str, text: str, parse_mode: str | None, handoff_id: str) -> None:
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        body: dict = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
        if parse_mode:
            body["parse_mode"] = parse_mode
        try:
            response = await self._client.post(url, json=body)
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout) as exc:
            # The request never left: safe to repeat.
            logger.warning("telegram_unreachable", extra={"handoff_id": handoff_id})
            raise ProviderTransientError("Telegram is unreachable") from exc
        except httpx.HTTPError as exc:
            # Sent, but no answer: Telegram may have delivered it.
            logger.warning("telegram_no_answer", extra={"handoff_id": handoff_id})
            raise DeliveryUnknown("Telegram did not answer after the request was sent") from exc
        if response.status_code >= 400:
            logger.warning("telegram_notify_failed", extra={"status": response.status_code, "handoff_id": handoff_id})
            if response.status_code == 429 or response.status_code >= 500:
                raise ProviderTransientError(f"Telegram answered {response.status_code}", retry_after=_retry_after(response))
            raise ProviderUnavailable(f"Telegram refused the notification: {response.status_code}")

    async def aclose(self) -> None:
        await self._client.aclose()


def _retry_after(response: httpx.Response) -> float | None:
    try:
        value = response.json().get("parameters", {}).get("retry_after")
    except (ValueError, AttributeError):
        return None
    return float(value) if isinstance(value, (int, float)) and value >= 0 else None


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
        # The dashboard opens this dialog after sign-in; another business's dialog answers 404.
        lines.append(f'<a href="{dashboard_url}/dashboard?conversation={handoff.conversation_id}">Открыть диалог</a>')
    lines.append(f"<code>{handoff.id}</code>")
    return "\n".join(lines)
