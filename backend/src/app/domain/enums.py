"""Stable string enums stored in the database and returned by the API."""

from enum import StrEnum


class Channel(StrEnum):
    whatsapp = "whatsapp"
    instagram = "instagram"
    telegram = "telegram"
    voice = "voice"
    cli = "cli"


class Language(StrEnum):
    ru = "ru"
    ky = "ky"
    mixed = "mixed"
    unknown = "unknown"


class MessageRole(StrEnum):
    user = "user"
    assistant = "assistant"
    manager = "manager"
    system = "system"


class CustomerStatus(StrEnum):
    new = "new"
    active = "active"
    hot = "hot"
    handed_off = "handed_off"
    merged = "merged"


class HandoffStatus(StrEnum):
    pending = "PENDING"
    accepted = "ACCEPTED"
    resolved = "RESOLVED"
    cancelled = "CANCELLED"


class HandoffPriority(StrEnum):
    low = "low"
    normal = "normal"
    high = "high"
    urgent = "urgent"


class MeetingStatus(StrEnum):
    proposed = "PROPOSED"
    confirmed = "CONFIRMED"
    cancelled = "CANCELLED"
    completed = "COMPLETED"


class RouteModel(StrEnum):
    small = "small"
    big = "big"


class ActionType(StrEnum):
    schedule_meeting = "schedule_meeting"
    request_phone = "request_phone"
    handoff = "handoff"
    update_customer = "update_customer"


PHONE_CHANNELS = frozenset({Channel.whatsapp, Channel.voice})


class CallStatus(StrEnum):
    started = "started"
    completed = "completed"
    failed = "failed"


class ConversationMode(StrEnum):
    """Who may answer the customer right now. A pending handoff keeps the agent on."""

    ai = "ai"
    human = "human"


class ConnectionStatus(StrEnum):
    not_connected = "not_connected"
    connecting = "connecting"
    connected = "connected"
    action_required = "action_required"
    error = "error"
    disconnected = "disconnected"


class InboundKind(StrEnum):
    """What a stored channel event is. Only text, start and unsupported reach the agent."""

    text = "text"
    start = "start"
    unsupported = "unsupported"
    ignored = "ignored"


class InboundStatus(StrEnum):
    queued = "queued"
    processed = "processed"
    ignored = "ignored"
    failed = "failed"


class OutboundStatus(StrEnum):
    """Delivery of one reply. `sent` means the provider accepted it, not that it was read."""

    queued = "queued"
    sending = "sending"
    sent = "sent"
    failed = "failed"
    unknown = "unknown"
    cancelled = "cancelled"


# A reply in one of these states never reached the customer for sure: the model must not
# see it as said.
OUTBOUND_NOT_DELIVERED = frozenset({OutboundStatus.failed, OutboundStatus.unknown, OutboundStatus.cancelled})


class JobStatus(StrEnum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"


class JobKind(StrEnum):
    process_inbound = "process_inbound"
    send_outbound = "send_outbound"
    notify_handoff = "notify_handoff"
