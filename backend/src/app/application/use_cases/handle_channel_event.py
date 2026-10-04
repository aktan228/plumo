"""Turn a raw channel payload into a normalized agent call."""

from app.correlation import get_correlation_id, get_request_id
from app.domain.errors import ProviderUnavailable
from app.domain.models import AgentResponse


class HandleChannelEvent:
    def __init__(self, channels: dict, agent) -> None:
        self.channels = channels
        self.agent = agent

    async def execute(self, channel: str, event: dict) -> dict:
        adapter = self.channels.get(channel)
        if adapter is None:
            raise ProviderUnavailable(f"channel '{channel}' is not registered")
        message = adapter.normalize_inbound(event)
        message.correlation_id = get_correlation_id() or None
        message.request_id = get_request_id() or None
        response: AgentResponse = await self.agent.process_message(message)
        payload = adapter.normalize_outbound(response)
        payload["external_user_id"] = message.external_user_id
        payload["correlation_id"] = response.correlation_id
        return payload
