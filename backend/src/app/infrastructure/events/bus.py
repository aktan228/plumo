"""In-process bus. Swap the class when a broker appears; keep DomainEvent."""

import inspect
import logging
from collections import defaultdict

from app.domain.events import DomainEvent

logger = logging.getLogger("plumo.events")


class InMemoryEventBus:
    def __init__(self) -> None:
        self._handlers: dict[str, list] = defaultdict(list)

    def subscribe(self, name: str, handler) -> None:
        self._handlers[name].append(handler)

    async def publish(self, event: DomainEvent) -> None:
        for handler in list(self._handlers.get(event.name, [])):
            result = handler(event)
            if inspect.isawaitable(result):
                await result


def log_event(event: DomainEvent) -> None:
    logger.info(event.name, extra={"event": event.name, "payload": event.payload})
