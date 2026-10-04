"""Ports. Application code depends on these, infrastructure implements them."""

from typing import Protocol
from uuid import UUID

from app.domain.events import DomainEvent
from app.domain.models import (
    Action,
    ActionContext,
    ActionResult,
    AgentContext,
    AudioInput,
    AudioOutput,
    Business,
    Classification,
    Conversation,
    Customer,
    CustomerSummary,
    ExtractedCustomerData,
    HandoffRequest,
    InboundMessage,
    InteractionLog,
    KnowledgeItem,
    LLMGeneration,
    Meeting,
    Message,
    MetricsSnapshot,
    RouteDecision,
    SummaryDraft,
    Transcript,
    UsageLog,
)


class LLMProvider(Protocol):
    """Text model. AgentService never imports a vendor SDK."""

    name: str

    async def generate_response(self, context: AgentContext, route: RouteDecision) -> LLMGeneration:
        """Draft a reply from the supplied context only."""

    async def classify(self, text: str, labels: list[str]) -> Classification:
        """Pick one label. Used by future routers, not by RuleBasedRouter."""

    async def summarize(self, messages: list[Message], previous: str | None) -> SummaryDraft:
        """Compress the dialog into a customer summary."""

    async def extract_customer_data(self, text: str) -> ExtractedCustomerData:
        """Pull phone, need and language out of one message."""


class STTProvider(Protocol):
    async def transcribe(self, audio: AudioInput) -> Transcript:
        """Turn an audio reference into text. Implementations must not invent a dialog."""


class TTSProvider(Protocol):
    async def synthesize(self, text: str) -> AudioOutput:
        """Turn text into an audio reference. Mock returns an id, not bytes."""


class Router(Protocol):
    async def select_model(self, context: AgentContext) -> RouteDecision:
        """Choose small or big before any model call."""


class LanguageDetector(Protocol):
    async def detect(self, text: str) -> str:
        """Return ru, ky, mixed or unknown."""


class HumanHandoffProvider(Protocol):
    async def notify(self, handoff: HandoffRequest) -> None:
        """Tell a human that a dialog is waiting. Mock only logs."""


class KnowledgeRetriever(Protocol):
    async def retrieve(self, business_id: UUID, query: str, limit: int = 5) -> list:
        """Return ranked knowledge hits for one business. Shape is list[KnowledgeHit]."""


class ActionExecutor(Protocol):
    async def execute(self, actions: list[Action], ctx: ActionContext) -> list[ActionResult]:
        """Apply structured actions. The model itself must not touch storage."""


class ChannelAdapter(Protocol):
    channel: str

    def normalize_inbound(self, event: dict) -> InboundMessage:
        """Map a transport payload to InboundMessage."""

    def normalize_outbound(self, response: object) -> dict:
        """Map AgentResponse to the transport payload."""


class EventBus(Protocol):
    def subscribe(self, name: str, handler) -> None:
        """Register a handler. Handler may be sync or async."""

    async def publish(self, event: DomainEvent) -> None:
        """Deliver one event to local subscribers."""


class CustomerStore(Protocol):
    async def get(self, customer_id: UUID) -> Customer | None: ...

    async def get_by_phone(self, phone: str) -> Customer | None: ...

    async def get_by_channel(self, channel: str, external_id: str) -> Customer | None: ...

    async def add(self, customer: Customer) -> Customer: ...

    async def save(self, customer: Customer) -> Customer: ...

    async def link_channel(self, customer_id: UUID, channel: str, external_id: str) -> None: ...

    async def merge(self, source_id: UUID, target_id: UUID) -> Customer: ...


class ConversationStore(Protocol):
    async def get(self, conversation_id: UUID) -> Conversation | None: ...

    async def get_open(self, customer_id: UUID, channel: str) -> Conversation | None: ...

    async def add(self, conversation: Conversation) -> Conversation: ...

    async def list_for_customer(self, customer_id: UUID) -> list[Conversation]: ...

    async def touch_summary(self, conversation_id: UUID, summary: str) -> None: ...


class MessageStore(Protocol):
    async def add(self, message: Message) -> Message: ...

    async def list_for_conversation(self, conversation_id: UUID) -> list[Message]: ...

    async def list_for_customer(self, customer_id: UUID, limit: int = 100) -> list[Message]: ...


class KnowledgeStore(Protocol):
    async def get(self, item_id: UUID) -> KnowledgeItem | None: ...

    async def list_active(self, business_id: UUID) -> list[KnowledgeItem]: ...

    async def list_items(self, business_id: UUID | None = None) -> list[KnowledgeItem]: ...

    async def add(self, item: KnowledgeItem) -> KnowledgeItem: ...


class BusinessStore(Protocol):
    async def get(self, business_id: UUID) -> Business | None: ...

    async def get_by_name(self, name: str) -> Business | None: ...

    async def list_all(self) -> list[Business]: ...

    async def add(self, business: Business) -> Business: ...


class SummaryStore(Protocol):
    async def get(self, customer_id: UUID) -> CustomerSummary | None: ...

    async def upsert(self, summary: CustomerSummary) -> CustomerSummary: ...


class HandoffStore(Protocol):
    async def add(self, handoff: HandoffRequest) -> HandoffRequest: ...

    async def get(self, handoff_id: UUID) -> HandoffRequest | None: ...

    async def list_requests(self, status: str | None, limit: int) -> list[HandoffRequest]: ...

    async def save(self, handoff: HandoffRequest) -> HandoffRequest: ...

    async def find_open(self, conversation_id: UUID, reason: str) -> HandoffRequest | None: ...


class MeetingStore(Protocol):
    async def add(self, meeting: Meeting) -> Meeting: ...

    async def get(self, meeting_id: UUID) -> Meeting | None: ...

    async def list_for_customer(self, customer_id: UUID) -> list[Meeting]: ...


class LogStore(Protocol):
    async def add_interaction(self, entry: InteractionLog) -> InteractionLog: ...

    async def add_usage(self, entry: UsageLog) -> UsageLog: ...


class MetricsStore(Protocol):
    async def collect(self) -> MetricsSnapshot: ...
