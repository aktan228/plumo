"""Domain records passed between services. Persistence mapping lives in infrastructure."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID


def utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class Business:
    id: UUID
    name: str
    description: str
    working_hours: str
    contacts: dict[str, Any]
    rules: str
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class KnowledgeItem:
    id: UUID
    business_id: UUID
    category: str
    title: str
    content: str
    metadata: dict[str, Any]
    active: bool
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class KnowledgeHit:
    item: KnowledgeItem
    score: float


@dataclass(slots=True)
class Customer:
    id: UUID
    phone: str | None
    language: str
    status: str
    need: str | None
    preferred_contact_channel: str | None
    merged_into_id: UUID | None
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class CustomerChannel:
    id: UUID
    customer_id: UUID
    channel: str
    external_id: str
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class Conversation:
    id: UUID
    customer_id: UUID
    channel: str
    started_at: datetime
    ended_at: datetime | None
    summary: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class Message:
    id: UUID
    conversation_id: UUID
    customer_id: UUID
    role: str
    text: str
    timestamp: datetime
    metadata: dict[str, Any]
    created_at: datetime


@dataclass(slots=True)
class CustomerSummary:
    customer_id: UUID
    summary: str
    need: str | None
    language: str
    status: str
    important_facts: list[str]
    updated_at: datetime


@dataclass(slots=True)
class InboundMessage:
    """Normalized input. The core does not know the transport behind `channel`."""

    channel: str
    external_user_id: str
    text: str
    message_id: str | None = None
    customer_id: UUID | None = None
    timestamp: datetime | None = None
    language_hint: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    business_id: UUID | None = None
    correlation_id: str | None = None
    request_id: str | None = None


@dataclass(slots=True)
class Action:
    type: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ActionResult:
    type: str
    status: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RouteDecision:
    model: str
    reason: str
    confidence: float


@dataclass(slots=True)
class Usage:
    input_tokens: int
    output_tokens: int
    estimated_cost: float
    latency_ms: int


@dataclass(slots=True)
class KnowledgeSource:
    id: UUID
    title: str
    category: str


@dataclass(slots=True)
class AgentContext:
    """Everything a model is allowed to see for one turn. Built without a specific LLM."""

    agent_instructions: str
    business: Business
    knowledge: list[KnowledgeHit]
    customer: Customer
    summary: CustomerSummary | None
    recent_messages: list[Message]
    current_message: str
    language: str
    channel: str = "whatsapp"


@dataclass(slots=True)
class LLMGeneration:
    text: str
    actions: list[Action]
    handoff_required: bool
    handoff_reason: str | None
    confidence: float
    model_used: str
    input_tokens: int
    output_tokens: int
    estimated_cost: float


@dataclass(frozen=True, slots=True)
class Classification:
    label: str
    confidence: float


@dataclass(slots=True)
class SummaryDraft:
    summary: str
    need: str | None
    important_facts: list[str]
    status: str | None


@dataclass(slots=True)
class ExtractedCustomerData:
    phone: str | None = None
    need: str | None = None
    language: str | None = None


@dataclass(frozen=True, slots=True)
class ValidationResult:
    safe: bool
    reason: str | None = None


@dataclass(slots=True)
class QuestionAssessment:
    """Whether a factual question can be answered from business data already in context."""

    factual: bool
    answerable: bool
    topic: str | None = None


@dataclass(slots=True)
class HandoffDecision:
    required: bool
    reason: str | None = None
    priority: str = "normal"


@dataclass(slots=True)
class HandoffRequest:
    id: UUID
    customer_id: UUID
    conversation_id: UUID
    reason: str
    priority: str
    summary: str
    recent_messages: list[dict[str, Any]]
    status: str
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class Meeting:
    id: UUID
    customer_id: UUID
    business_id: UUID
    scheduled_at: datetime
    status: str
    notes: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class InteractionLog:
    id: UUID
    request_id: str
    correlation_id: str
    customer_id: UUID
    conversation_id: UUID
    channel: str
    language: str
    input_text: str
    route: str
    route_reason: str
    model: str
    confidence: float
    knowledge_sources: list[dict[str, Any]]
    response_text: str
    handoff: bool
    handoff_reason: str | None
    actions: list[dict[str, Any]]
    latency_ms: int
    estimated_cost: float
    created_at: datetime


@dataclass(slots=True)
class UsageLog:
    id: UUID
    interaction_log_id: UUID | None
    request_id: str
    model: str
    input_tokens: int
    output_tokens: int
    estimated_cost: float
    latency_ms: int
    created_at: datetime


@dataclass(slots=True)
class AgentResponse:
    response_text: str
    customer_id: UUID
    conversation_id: UUID
    model_used: str
    route: str
    route_reason: str
    confidence: float
    actions: list[Action]
    handoff_required: bool
    handoff_reason: str | None
    knowledge_sources: list[KnowledgeSource]
    usage: Usage
    latency_ms: int
    logs: list[str]
    language: str
    correlation_id: str | None = None
    handoff_id: UUID | None = None
    # False: do not send anything to the customer (a manager owns the dialog).
    send_reply: bool = True
    # True: the channel re-delivered a message already answered.
    duplicate: bool = False


@dataclass(slots=True)
class ActionContext:
    customer: Customer
    conversation: Conversation
    business: Business
    language: str
    recent_messages: list[Message]
    summary_text: str


@dataclass(slots=True)
class AudioInput:
    audio_id: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Transcript:
    text: str
    language: str
    audio_id: str


@dataclass(slots=True)
class AudioOutput:
    audio_id: str
    text: str


@dataclass(slots=True)
class CallTurn:
    """One customer utterance from the voice platform."""

    text: str
    caller: str | None
    call_id: str | None
    called: str | None = None
    business_id: str | None = None


@dataclass(slots=True)
class CallReport:
    """What the platform reports after hang-up."""

    call_id: str
    caller: str | None
    called: str | None
    status: str
    started_at: datetime
    duration_s: int
    provider_cost: float | None
    transcript: list[dict[str, Any]] = field(default_factory=list)
    raw_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class VoiceCall:
    """One phone call handled by the voice platform. Turns live in `messages`."""

    id: UUID
    provider: str
    provider_call_id: str
    customer_id: UUID | None
    caller: str | None
    called: str | None
    status: str
    started_at: datetime
    ended_at: datetime | None
    duration_s: int
    cost: float
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class MetricsSnapshot:
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


@dataclass(slots=True)
class CustomerHistory:
    customer: Customer
    conversations: list[Conversation]
    messages: list[Message]
    summary: CustomerSummary | None
