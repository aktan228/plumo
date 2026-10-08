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
