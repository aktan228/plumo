"""Transport adapters. They normalize events and do not contain sales logic."""

from datetime import UTC, datetime
from uuid import UUID

from app.domain.errors import InvalidMessage
from app.domain.models import AgentResponse, InboundMessage


class _MockAdapter:
    channel = ""

    def normalize_outbound(self, response: AgentResponse) -> dict:
        return {
            "channel": self.channel,
            "text": response.response_text,
            "customer_id": str(response.customer_id),
            "conversation_id": str(response.conversation_id),
            "handoff_required": response.handoff_required,
            "handoff_reason": response.handoff_reason,
            "route": response.route,
            "route_reason": response.route_reason,
            "model_used": response.model_used,
        }


class MockWhatsAppAdapter(_MockAdapter):
    channel = "whatsapp"

    def normalize_inbound(self, event: dict) -> InboundMessage:
        external = str(event.get("from") or event.get("wa_id") or "")
        text = str(event.get("text") or event.get("body") or "")
        return _message(self.channel, external, text, event.get("id"), event.get("timestamp"), event)


class MockTelegramAdapter(_MockAdapter):
    channel = "telegram"

    def normalize_inbound(self, event: dict) -> InboundMessage:
        message = event.get("message") or event
        chat = message.get("chat") or {}
        external = str(chat.get("id") or event.get("from_id") or "")
        text = str(message.get("text") or "")
        return _message(self.channel, external, text, message.get("message_id"), message.get("date"), event)


class MockInstagramAdapter(_MockAdapter):
    channel = "instagram"

    def normalize_inbound(self, event: dict) -> InboundMessage:
        sender = event.get("sender") or {}
        message = event.get("message") or event
        external = str(sender.get("id") or event.get("sender_id") or "")
        text = str(message.get("text") or "")
        return _message(self.channel, external, text, message.get("mid"), event.get("timestamp"), event)


class MockVoiceAdapter(_MockAdapter):
    channel = "voice"

    def normalize_inbound(self, event: dict) -> InboundMessage:
        text = event.get("text") or event.get("transcript")
        if not text:
            raise InvalidMessage("voice adapter expects text; send audio_id to /api/v1/voice/respond")
        external = str(event.get("caller") or event.get("from") or "")
        return _message(self.channel, external, str(text), event.get("call_id"), event.get("timestamp"), event)


def mock_channels() -> dict[str, _MockAdapter]:
    adapters = (
        MockWhatsAppAdapter(),
        MockTelegramAdapter(),
        MockInstagramAdapter(),
        MockVoiceAdapter(),
    )
    return {item.channel: item for item in adapters}


def _message(channel: str, external: str, text: str, message_id, timestamp, event: dict) -> InboundMessage:
    if not external:
        raise InvalidMessage(f"{channel} event has no external user id")
    parsed = _timestamp(timestamp)
    return InboundMessage(
        channel=channel,
        external_user_id=external,
        text=text,
        message_id=str(message_id) if message_id is not None else None,
        timestamp=parsed,
        business_id=_business_id(event.get("business_id")),
        metadata={"provider": "mock", "channel": channel},
    )


def _timestamp(value) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=UTC)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _business_id(value) -> UUID | None:
    if not value:
        return None
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except ValueError:
        return None
