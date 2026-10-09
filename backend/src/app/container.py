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
from app.domain.ports import HumanHandoffProvider, Router
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
from app.infrastructure.handoff.telegram_provider import TelegramHandoffProvider


@dataclass
class Runtime:
    settings: Settings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    providers: AIProviderFactory
    router: Router
    handoff_provider: HumanHandoffProvider
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
        handoffs=handoffs,
        voice_budget_s=runtime.settings.voice_turn_budget_s,
        chat_budget_s=runtime.settings.chat_turn_budget_s,
        small_enabled=runtime.providers.small_enabled,
        manager_pause_hours=runtime.settings.manager_pause_hours,
        stt_low_confidence=runtime.settings.stt_low_confidence,
        voice_hedge_after_s=runtime.settings.voice_hedge_after_s,
    )


def build_voice(session: AsyncSession, runtime: Runtime) -> VoiceService:
    return VoiceService(runtime.providers.stt(), runtime.providers.tts(), build_agent(session, runtime))


def build_calls(session: AsyncSession, runtime: Runtime, agent: AgentService | None = None) -> CallService:
    return CallService(
        agent=agent or build_agent(session, runtime),
        customers=CustomerRepository(session),
        messages=MessageRepository(session),
        calls=VoiceCallRepository(session),
        conversations=ConversationRepository(session),
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


def _handoff_provider(settings: Settings) -> HumanHandoffProvider:
    # Telegram is not an AI provider: it works in AI_MODE=mock too, so a demo
    # on the mock model still pings the real manager chat.
    if settings.handoff_provider == "telegram":
        return TelegramHandoffProvider()
    if settings.mock_mode or settings.handoff_provider == "mock":
        return MockHandoffProvider()
    raise ProviderUnavailable(
        f"handoff provider '{settings.handoff_provider}' is not registered."
    )


def _register_llm_providers(providers: AIProviderFactory, settings: Settings) -> None:
    if settings.mock_mode:
        return
    # Only the vendors named in SMALL/BIG_MODEL_PROVIDER are built: each one
    # needs its own key, and a missing unused key must not break startup.
    wanted = {settings.big_model_provider}
    if settings.small_model_enabled:
        wanted.add(settings.small_model_provider)
    for name in sorted(wanted):
        provider = _llm_provider(name, settings)
        if provider is not None:
            providers.register_llm(name, provider)


def _llm_provider(name: str, settings: Settings):
    family, _, tier = name.rpartition("_")
    if tier not in ("small", "big"):
        family, tier = name, "big"
    if family == "openrouter":
        model = settings.openrouter_small_model if tier == "small" else settings.openrouter_big_model
        return OpenRouterLLMProvider(
            name,
            model,
            base_url=settings.openrouter_base_url,
            extra_body=_openrouter_reasoning(model, settings.llm_reasoning_effort),
            fallback_models=_split(settings.openrouter_fallback_models),
            max_retries=settings.llm_max_retries,
        )
    if family == "gemini":
        # Google AI Studio directly: no gateway fee. Thinking is off, it only
        # adds latency and tokens to a short sales reply.
        model = settings.gemini_small_model if tier == "small" else settings.gemini_big_model
        return OpenRouterLLMProvider(
            name,
            model,
            api_key_env="GEMINI_API_KEY",
            base_url=settings.gemini_base_url,
            vendor="Gemini",
            extra_body=_gemini_reasoning(model, settings.llm_reasoning_effort),
            fallback_models=_split(settings.gemini_fallback_models),
            max_retries=settings.llm_max_retries,
        )
    if family == "anthropic":
        from app.infrastructure.ai.anthropic_llm import AnthropicLLMProvider

        model = settings.anthropic_small_model if tier == "small" else settings.anthropic_big_model
        return AnthropicLLMProvider(name, model, effort=settings.anthropic_effort, max_retries=settings.llm_max_retries)
    if family == "local":
        # Self-hosted model (vLLM, Ollama, llama.cpp, LM Studio) behind an
        # OpenAI-compatible endpoint. Planned home of the fine-tuned small model.
        model = settings.local_small_model if tier == "small" else settings.local_big_model
        return OpenRouterLLMProvider(
            name,
            model,
            api_key_env="LOCAL_LLM_API_KEY",
            base_url=settings.local_llm_base_url,
            vendor="Local",
            require_key=False,
            price=(0.0, 0.0),
            timeout_s=settings.local_llm_timeout_s,
        )
    if family == "openai_compat":
        # Any OpenAI-compatible API: DeepSeek, OpenAI, Groq, a local LiteLLM.
        model = settings.llm_small_model if tier == "small" else settings.llm_big_model
        return OpenRouterLLMProvider(
            name,
            model,
            api_key_env="LLM_API_KEY",
            base_url=settings.llm_base_url,
            vendor="LLM",
            max_retries=settings.llm_max_retries,
        )
    return None


def _gemini_reasoning(model: str, override: str) -> dict | None:
    """Gemini OpenAI-compatible `reasoning_effort`: "none" exists only on 2.5 Flash.

    Gemini 3 cannot switch thinking off; "minimal" is the cheapest level.
    A fallback model of another generation keeps the first model's setting,
    so fallbacks should stay within Gemini 3.
    """

    effort = override.strip()
    if not effort:
        if "2.5-flash" in model:
            effort = "none"
        elif "gemini-3" in model:
            effort = "minimal"
    return {"reasoning_effort": effort} if effort else None


def _openrouter_reasoning(model: str, override: str) -> dict | None:
    """OpenRouter unified `reasoning.effort`, mapped to Google's thinkingLevel."""

    effort = override.strip()
    if not effort and "gemini-3" in model:
        effort = "minimal"
    elif not effort and "claude-haiku" in model:
        # Haiku thinks by default: 2.4-3.2 s per reply against 1.3-1.7 s with it off.
        effort = "none"
    return {"reasoning": {"effort": effort}} if effort else None


def _split(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def _channels(settings: Settings) -> dict:
    del settings
    return mock_channels()
