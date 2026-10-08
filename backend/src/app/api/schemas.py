"""HTTP schemas. Database rows are not returned from the API."""

from datetime import datetime as DateTime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import Channel


class ErrorOut(BaseModel):
    error: str
    message: str
    correlation_id: str | None = None
    details: list[dict[str, Any]] | None = None


class MessageIn(BaseModel):
    """Normalized message. Channel adapters should POST this shape, or their own event to /channels."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "channel": "whatsapp",
                    "external_user_id": "+996555123456",
                    "text": "Еще продается квартира за 85000?",
                    "message_id": "wamid.1",
                    "language_hint": "ru",
                }
            ]
        }
    )

    channel: Channel
    external_user_id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=4000)
    message_id: str | None = Field(default=None, max_length=128)
    customer_id: UUID | None = None
    timestamp: DateTime | None = None
    language_hint: str | None = Field(default=None, max_length=16)
    metadata: dict[str, Any] = Field(default_factory=dict)
    business_id: UUID | None = None


class ActionOut(BaseModel):
    type: str
    payload: dict[str, Any] = Field(default_factory=dict)


class KnowledgeSourceOut(BaseModel):
    id: UUID
    title: str
    category: str


class UsageOut(BaseModel):
    input_tokens: int
    output_tokens: int
    estimated_cost: float
    latency_ms: int


class AgentResponseOut(BaseModel):
    """What the core returns to any channel."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "response_text": "Да, объект за 85 000 USD ещё доступен.",
                    "customer_id": "33333333-3333-4333-8333-333333333331",
                    "conversation_id": "44444444-4444-4444-8444-444444444441",
                    "model_used": "mock_small",
                    "route": "small",
                    "route_reason": "knowledge_base_simple_question",
                    "confidence": 0.93,
                    "actions": [],
                    "handoff_required": False,
                    "handoff_reason": None,
                    "knowledge_sources": [
                        {"id": "22222222-2222-4222-8222-222222222221", "title": "Квартира на Чуй", "category": "property"}
                    ],
                    "usage": {
                        "input_tokens": 12,
                        "output_tokens": 30,
                        "estimated_cost": 0.001,
                        "latency_ms": 8,
                    },
                    "latency_ms": 8,
                    "logs": ["route:small:knowledge_base_simple_question"],
                    "language": "ru",
                    "correlation_id": "req-1",
                    "handoff_id": None,
                }
            ]
        }
    )

    response_text: str
    customer_id: UUID
    conversation_id: UUID
    model_used: str
    route: str
    route_reason: str
    confidence: float
    actions: list[ActionOut]
    handoff_required: bool
    handoff_reason: str | None
    knowledge_sources: list[KnowledgeSourceOut]
    usage: UsageOut
    latency_ms: int
    logs: list[str]
    language: str
    correlation_id: str | None = None
    handoff_id: UUID | None = None
    send_reply: bool = Field(
        default=True,
        description="False: ничего не отправлять клиенту, диалог ведёт менеджер.",
    )
    duplicate: bool = Field(
        default=False,
        description="True: канал прислал то же сообщение повторно, ответ взят из истории.",
    )


class ManagerMessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000, examples=["Добрый день! Это Азамат, менеджер. Квартира на Чуй свободна, когда удобно посмотреть?"])
    author: str | None = Field(default=None, max_length=100, examples=["Азамат"])


class TranscriptOut(BaseModel):
    text: str
    language: str
    audio_id: str


class TranscribeIn(BaseModel):
    audio_id: str = Field(min_length=1, max_length=128, examples=["mock_audio_apt"])


class VoiceRespondIn(BaseModel):
    audio_id: str = Field(min_length=1, max_length=128, examples=["mock_audio_apt"])
    external_user_id: str = Field(min_length=1, max_length=128, examples=["+996555123456"])
    channel: Channel = Channel.voice
    language_hint: str | None = None
    business_id: UUID | None = None


class VoiceRespondOut(BaseModel):
    transcript: TranscriptOut
    audio: TranscriptOut
    response: AgentResponseOut


class CustomerOut(BaseModel):
    id: UUID
    phone: str | None
    language: str
    status: str
    need: str | None
    preferred_contact_channel: str | None
    merged_into_id: UUID | None
    created_at: DateTime
    updated_at: DateTime


class MessageOut(BaseModel):
    id: UUID
    conversation_id: UUID
    customer_id: UUID
    role: str
    text: str
    timestamp: DateTime
    metadata: dict[str, Any]


class ConversationOut(BaseModel):
    id: UUID
    customer_id: UUID
    channel: str
    started_at: DateTime
    ended_at: DateTime | None
    summary: str | None
    created_at: DateTime
    updated_at: DateTime


class SummaryOut(BaseModel):
    customer_id: UUID
    summary: str
    need: str | None
    language: str
    status: str
    important_facts: list[str]
    updated_at: DateTime


class HistoryOut(BaseModel):
    customer: CustomerOut
    summary: SummaryOut | None
    conversations: list[ConversationOut]
    messages: list[MessageOut]


class ConversationDetailOut(BaseModel):
    conversation: ConversationOut
    messages: list[MessageOut]


class HandoffOut(BaseModel):
    id: UUID
    customer_id: UUID
    conversation_id: UUID
    reason: str
    priority: str
    summary: str
    recent_messages: list[dict[str, Any]]
    status: str
    created_at: DateTime
    updated_at: DateTime


class KnowledgeIn(BaseModel):
    business_id: UUID | None = None
    category: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1, max_length=8000)
    metadata: dict[str, Any] = Field(default_factory=dict)
    active: bool = True


class KnowledgeOut(BaseModel):
    id: UUID
    business_id: UUID
    category: str
    title: str
    content: str
    metadata: dict[str, Any]
    active: bool
    created_at: DateTime
    updated_at: DateTime


class MeetingIn(BaseModel):
    customer_id: UUID
    business_id: UUID | None = None
    text: str = ""
    datetime: DateTime | None = None
    date: str | None = None
    time: str | None = None
    notes: str | None = None


class MeetingOut(BaseModel):
    id: UUID
    customer_id: UUID
    business_id: UUID
    datetime: DateTime
    status: str
    notes: str | None
    created_at: DateTime


class MetricsOut(BaseModel):
    total_conversations: int
    total_messages: int
    handled_without_human: int
    handed_off: int
    meetings_scheduled: int
    average_first_response_time_ms: float
    average_response_time_ms: float
    small_model_percentage: float
    big_model_percentage: float
    russian_percentage: float
    kyrgyz_percentage: float
    mixed_percentage: float
    average_dialog_cost: float
    handoff_rate: float
    voice_calls: int = 0
    voice_minutes: float = 0.0
    voice_cost_per_minute: float = 0.0


class ChannelEventOut(BaseModel):
    channel: str
    text: str
    external_user_id: str
    customer_id: UUID
    conversation_id: UUID
    handoff_required: bool
    handoff_reason: str | None = None
    route: str
    route_reason: str
    model_used: str
    correlation_id: str | None = None
