"""Composition root. This is the only place that wires adapters to services."""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.application.services.action_executor import MockActionExecutor
from app.application.services.agent_service import AgentService
from app.application.services.call_service import CallService
from app.application.services.context_builder import ContextBuilder
from app.application.services.customer_resolver import CustomerResolver
from app.application.services.handoff_service import HandoffService
from app.application.services.knowledge_retriever import SimpleKnowledgeRetriever
from app.application.services.meeting_service import MeetingService
from app.application.services.memory_service import MemoryService
from app.application.services.metrics_service import MetricsService
from app.application.services.response_validator import ResponseValidator
from app.application.services.router import RuleBasedRouter
from app.application.services.voice_service import VoiceService
from app.application.use_cases.handle_channel_event import HandleChannelEvent
from app.config import Settings
from app.domain.errors import ProviderUnavailable
from app.domain.events import (
    CONVERSATION_COMPLETED,
    CUSTOMER_CREATED,
    CUSTOMER_MERGED,
    HANDOFF_REQUESTED,
    MEETING_SCHEDULED,
    MESSAGE_PROCESSED,
    MESSAGE_RECEIVED,
)
from app.domain.ports import Router
from app.infrastructure.ai.factory import AIProviderFactory
from app.infrastructure.ai.openrouter_llm import OpenRouterLLMProvider
from app.infrastructure.channels.mock_adapters import mock_channels
from app.infrastructure.database.repositories import (
    BusinessRepository,
    ConversationRepository,
    CustomerRepository,
    HandoffRepository,
    KnowledgeRepository,
    LogRepository,
    MeetingRepository,
    MessageRepository,
    MetricsRepository,
    SummaryRepository,
    VoiceCallRepository,
)
from app.infrastructure.database.session import create_engine, create_session_factory
from app.infrastructure.events.bus import InMemoryEventBus, log_event
from app.infrastructure.handoff.mock_provider import MockHandoffProvider


@dataclass
class Runtime:
    settings: Settings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    providers: AIProviderFactory
    router: Router
    handoff_provider: MockHandoffProvider
    channels: dict
    events: InMemoryEventBus
    validator: ResponseValidator
    context_builder: ContextBuilder
    owns_engine: bool = True


def build_runtime(settings: Settings, engine: AsyncEngine | None = None) -> Runtime:
    owns_engine = engine is None
    engine = engine or create_engine(settings.database_url)
    events = InMemoryEventBus()
    for name in (
        MESSAGE_RECEIVED,
        CUSTOMER_CREATED,
        CUSTOMER_MERGED,
        MESSAGE_PROCESSED,
        HANDOFF_REQUESTED,
        MEETING_SCHEDULED,
        CONVERSATION_COMPLETED,
    ):
        events.subscribe(name, log_event)
    router = _router(settings)
    providers = AIProviderFactory(settings)
    _register_llm_providers(providers, settings)
    return Runtime(
        settings=settings,
        engine=engine,
        session_factory=create_session_factory(engine),
        providers=providers,
        router=router,
        handoff_provider=_handoff_provider(settings),
        channels=_channels(settings),
        events=events,
        validator=ResponseValidator(),
        context_builder=ContextBuilder(),
        owns_engine=owns_engine,
    )


def build_agent(session: AsyncSession, runtime: Runtime) -> AgentService:
    customers = CustomerRepository(session)
    summaries = SummaryRepository(session)
    conversations = ConversationRepository(session)
    messages = MessageRepository(session)
    businesses = BusinessRepository(session)
    knowledge = KnowledgeRepository(session)
    handoffs = HandoffRepository(session)
    meetings = MeetingRepository(session)
    logs = LogRepository(session)
    memory = MemoryService(customers, summaries)
    meeting_service = MeetingService(meetings, runtime.events)
    handoff_service = HandoffService(handoffs, customers, runtime.handoff_provider, runtime.events)
    return AgentService(
        resolver=CustomerResolver(customers, runtime.events),
        memory=memory,
        conversations=conversations,
        messages=messages,
        businesses=businesses,
        retriever=SimpleKnowledgeRetriever(knowledge),
        context_builder=runtime.context_builder,
        router=runtime.router,
        llm_for_tier=runtime.providers.llm,
        language_detector=runtime.providers.language(),
        validator=runtime.validator,
        actions=MockActionExecutor(meeting_service, handoff_service, customers),
        logs=logs,
        events=runtime.events,
        confidence_threshold=runtime.settings.small_model_confidence_threshold,
        default_language=runtime.settings.default_language,
        default_business_id=runtime.settings.default_business_id or None,
    )


def build_voice(session: AsyncSession, runtime: Runtime) -> VoiceService:
    return VoiceService(runtime.providers.stt(), runtime.providers.tts(), build_agent(session, runtime))


def build_calls(session: AsyncSession, runtime: Runtime, agent: AgentService | None = None) -> CallService:
    return CallService(
        agent=agent or build_agent(session, runtime),
        customers=CustomerRepository(session),
        messages=MessageRepository(session),
        calls=VoiceCallRepository(session),
        provider=runtime.settings.voice_platform,
        usd_per_minute=runtime.settings.voice_usd_per_minute,
    )


def build_channel_handler(session: AsyncSession, runtime: Runtime) -> HandleChannelEvent:
    return HandleChannelEvent(runtime.channels, build_agent(session, runtime))


def build_handoffs(session: AsyncSession, runtime: Runtime) -> HandoffService:
    return HandoffService(
        HandoffRepository(session),
        CustomerRepository(session),
        runtime.handoff_provider,
        runtime.events,
    )


def build_meetings(session: AsyncSession, runtime: Runtime) -> MeetingService:
    return MeetingService(MeetingRepository(session), runtime.events)


def build_metrics(session: AsyncSession) -> MetricsService:
    return MetricsService(MetricsRepository(session))


def _router(settings: Settings) -> Router:
    if settings.router in ("rules", "rule", "rule_based"):
        return RuleBasedRouter()
    raise ProviderUnavailable(
        f"router '{settings.router}' is not registered. Keep ROUTER=rules or add an MLRouter."
    )


def _handoff_provider(settings: Settings) -> MockHandoffProvider:
    if settings.mock_mode or settings.handoff_provider == "mock":
        return MockHandoffProvider()
    raise ProviderUnavailable(
        f"handoff provider '{settings.handoff_provider}' is not registered."
    )


def _register_llm_providers(providers: AIProviderFactory, settings: Settings) -> None:
    if settings.mock_mode:
        return
    names = {settings.small_model_provider, settings.big_model_provider}
    if not any(name.startswith("openrouter") for name in names):
        return
    small = OpenRouterLLMProvider(
        "openrouter_small",
        settings.openrouter_small_model,
        base_url=settings.openrouter_base_url,
    )
    big = OpenRouterLLMProvider(
        "openrouter_big",
        settings.openrouter_big_model,
        base_url=settings.openrouter_base_url,
    )
    providers.register_llm("openrouter_small", small)
    providers.register_llm("openrouter_big", big)
    providers.register_llm("openrouter", big)


def _channels(settings: Settings) -> dict:
    del settings
    return mock_channels()
