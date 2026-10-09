"""In-process domain events. Transport can be replaced later without touching services."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.domain.models import utcnow


@dataclass(slots=True)
class DomainEvent:
    name: str
    payload: dict[str, Any]
    occurred_at: datetime = field(default_factory=utcnow)


MESSAGE_RECEIVED = "message_received"
CUSTOMER_CREATED = "customer_created"
CUSTOMER_MERGED = "customer_merged"
MESSAGE_PROCESSED = "message_processed"
HANDOFF_REQUESTED = "handoff_requested"
MEETING_SCHEDULED = "meeting_scheduled"
CONVERSATION_COMPLETED = "conversation_completed"
