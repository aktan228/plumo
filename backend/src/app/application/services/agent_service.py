"""Orchestrates one inbound message. It does not implement a model."""

import json
import logging
import time
from uuid import UUID, uuid4

from app.application.services.context_builder import ContextBuilder
from app.application.services.customer_resolver import CustomerResolver
from app.application.services.grounded_reply import is_unusable_reply, quote_knowledge
from app.application.services.handoff_service import evaluate_handoff
from app.application.services.memory_service import MemoryService, read_unclear_count, write_unclear_count
from app.application.services.response_validator import ResponseValidator
from app.correlation import get_correlation_id, get_request_id
from app.domain.enums import PHONE_CHANNELS, ActionType, Channel, MessageRole
from app.domain.errors import BusinessNotFound, CustomerNotFound, InvalidMessage
from app.domain.events import MESSAGE_PROCESSED, MESSAGE_RECEIVED, DomainEvent
from app.domain.models import (
    Action,
    ActionContext,
    AgentResponse,
    Conversation,
    InboundMessage,
    InteractionLog,
    KnowledgeSource,
    LLMGeneration,
    Message,
    RouteDecision,
    Usage,
    UsageLog,
    utcnow,
)
from app.domain.phrases import ROLE_PHRASE_KY, ROLE_PHRASE_RU, unknown_phrase
from app.domain.ports import (
    ActionExecutor,
    BusinessStore,
    ConversationStore,
    EventBus,
    KnowledgeRetriever,
    LanguageDetector,
    LLMProvider,
    LogStore,
    MessageStore,
    Router,
)
from app.domain.text_signals import analyze_message
from app.scrub import scrub_mapping, scrub_text

logger = logging.getLogger("plumo.agent")


class AgentService:
    """Run the sales pipeline from a normalized message to a normalized response.

    Customer resolution, memory, knowledge, routing, validation, actions and
    logs live here. The text itself comes from an `LLMProvider`.
    """

    def __init__(
        self,
        *,
        resolver: CustomerResolver,
        memory: MemoryService,
        conversations: ConversationStore,
        messages: MessageStore,
        businesses: BusinessStore,
        retriever: KnowledgeRetriever,
        context_builder: ContextBuilder,
        router: Router,
        llm_for_tier,
        language_detector: LanguageDetector,
        validator: ResponseValidator,
        actions: ActionExecutor,
        logs: LogStore,
        events: EventBus,
        confidence_threshold: float = 0.7,
        default_language: str = "ru",
        default_business_id: str | None = None,
    ) -> None:
        self.resolver = resolver
        self.memory = memory
        self.conversations = conversations
        self.messages = messages
        self.businesses = businesses
        self.retriever = retriever
        self.context_builder = context_builder
        self.router = router
        self.llm_for_tier = llm_for_tier
        self.language_detector = language_detector
        self.validator = validator
        self.actions = actions
        self.logs = logs
        self.events = events
        self.confidence_threshold = confidence_threshold
        self.default_language = default_language
        self.default_business_id = default_business_id

    async def process_message(self, message: InboundMessage) -> AgentResponse:
        started = time.perf_counter()
        steps: list[str] = []
        message = self._prepare(message)
        correlation_id = message.correlation_id or get_correlation_id() or str(uuid4())
        request_id = message.request_id or get_request_id() or message.message_id or str(uuid4())

        customer = await self.resolver.resolve_customer(message)
        customer = await self.resolver.absorb_phone_from_text(customer, message.text)
        language = await self._language(message)
        customer = await self.memory.update_language(customer, language)
        steps.append(f"customer:{customer.id}")

        business = await self._business(message.business_id)
        conversation = await self._conversation(customer.id, message.channel)
        incoming = await self._store_user_message(message, customer.id, conversation.id)
        await self.events.publish(
            DomainEvent(
                MESSAGE_RECEIVED,
                {
                    "customer_id": str(customer.id),
                    "conversation_id": str(conversation.id),
                    "channel": message.channel,
                    "correlation_id": correlation_id,
                },
            )
        )

        summary = await self.memory.get_summary(customer.id)
        history = await self.messages.list_for_customer(customer.id, limit=20)
        knowledge = await self.retriever.retrieve(business.id, message.text)
        context = self.context_builder.build(
            business=business,
            knowledge=knowledge,
            customer=customer,
            summary=summary,
            recent_messages=history,
            current_message=message.text,
            language=language,
            current_message_id=incoming.id,
        )
        steps.append("knowledge:" + ",".join(hit.item.title for hit in knowledge))

        route = await self.router.select_model(context)
        generations: list[LLMGeneration] = []
        generation, route = await self._generate(context, route, generations)
        steps.append(f"route:{route.model}:{route.reason}")

        signals = analyze_message(message.text)
        assessment = self.validator.assess(message.text, context)
        if signals.human_request:
            response_text = _human_phrase(language)
        elif assessment.factual and not assessment.answerable and not context.knowledge:
            response_text = unknown_phrase(assessment.topic, language)
        elif assessment.factual and not assessment.answerable and assessment.topic == "installment":
            response_text = unknown_phrase(assessment.topic, language)
        else:
            response_text = generation.text
        if is_unusable_reply(response_text):
            if assessment.factual and context.knowledge:
                response_text = quote_knowledge(context)
                steps.append("grounded_fallback")
            elif not assessment.factual:
                response_text = ROLE_PHRASE_KY if language == "ky" else ROLE_PHRASE_RU
                steps.append("role_fallback")

        actions = [item for item in generation.actions if item.type != ActionType.handoff]
        if signals.meeting and not any(item.type == ActionType.schedule_meeting for item in actions):
            actions.append(Action(ActionType.schedule_meeting, {"text": message.text}))
        if customer.phone is None and message.channel not in PHONE_CHANNELS:
            if signals.meeting or (assessment.answerable and assessment.factual):
                actions.append(Action(ActionType.request_phone, {}))
        extracted = await self.llm_for_tier("small").extract_customer_data(message.text)
        if extracted.need:
            actions.append(Action(ActionType.update_customer, {"need": extracted.need, "language": language}))

        extra = json.dumps([item.payload for item in actions], ensure_ascii=False, default=str)
        validation = self.validator.validate(response_text, context, extra=extra)
        if not validation.safe and context.knowledge and assessment.factual:
            response_text = quote_knowledge(context)
            validation = self.validator.validate(response_text, context, extra=extra)
            steps.append("grounded_fallback")
        if not validation.safe:
            if assessment.factual:
                response_text = unknown_phrase(assessment.topic, language)
            else:
                response_text = ROLE_PHRASE_KY if language == "ky" else ROLE_PHRASE_RU
            steps.append(f"validator:{validation.reason}")

        unclear = read_unclear_count(summary.important_facts if summary else [])
        if signals.unclear_confirmation or (not assessment.factual and generation.confidence < 0.55):
            unclear += 1
        elif assessment.answerable or generation.confidence >= self.confidence_threshold:
            unclear = 0

        decision = evaluate_handoff(signals, assessment, generation, validation, unclear)
        if decision.required and decision.reason:
            actions.append(
                Action(
                    ActionType.handoff,
                    {"reason": decision.reason, "priority": decision.priority},
                )
            )
            steps.append(f"handoff:{decision.reason}")

        action_ctx = ActionContext(
            customer=customer,
            conversation=conversation,
            business=business,
            language=language,
            recent_messages=history,
            summary_text=summary.summary if summary else message.text,
        )
        results = await self.actions.execute(actions, action_ctx)
        customer = await self._reload_customer(customer.id)

        small = self.llm_for_tier("small")
        draft = await small.summarize(history + [_as_assistant_preview(conversation, customer.id, response_text)], summary.summary if summary else None)
        draft.important_facts = write_unclear_count(draft.important_facts, unclear)
        await self.memory.write_summary(customer, draft, language)
        await self.conversations.touch_summary(conversation.id, draft.summary)

        assistant = Message(
            id=uuid4(),
            conversation_id=conversation.id,
            customer_id=customer.id,
            role=MessageRole.assistant,
            text=response_text,
            timestamp=utcnow(),
            metadata=scrub_mapping(
                {
                    "route": route.model,
                    "route_reason": route.reason,
                    "model": generation.model_used,
                    "handoff": decision.required,
                }
            ),
            created_at=utcnow(),
        )
        await self.messages.add(assistant)

        latency_ms = int((time.perf_counter() - started) * 1000)
        sources = [
            KnowledgeSource(id=hit.item.id, title=hit.item.title, category=hit.item.category) for hit in knowledge
        ]
        cost = round(sum(item.estimated_cost for item in generations), 6)
        usage = Usage(
            input_tokens=sum(item.input_tokens for item in generations),
            output_tokens=sum(item.output_tokens for item in generations),
            estimated_cost=cost,
            latency_ms=latency_ms,
        )
        handoff_id = _handoff_id(results)
        interaction = InteractionLog(
            id=uuid4(),
            request_id=request_id,
            correlation_id=correlation_id,
            customer_id=customer.id,
            conversation_id=conversation.id,
            channel=message.channel,
            language=language,
            input_text=scrub_text(message.text),
            route=str(route.model),
            route_reason=route.reason,
            model=generation.model_used,
            confidence=generation.confidence,
            knowledge_sources=[
                {"id": str(source.id), "title": source.title, "category": source.category} for source in sources
            ],
            response_text=scrub_text(response_text),
            handoff=decision.required,
            handoff_reason=decision.reason,
            actions=[
                {"type": result.type, "status": result.status, "payload": result.payload} for result in results
            ],
            latency_ms=latency_ms,
            estimated_cost=cost,
            created_at=utcnow(),
        )
        await self.logs.add_interaction(interaction)
        for item in generations:
            await self.logs.add_usage(
                UsageLog(
                    id=uuid4(),
                    interaction_log_id=interaction.id,
                    request_id=request_id,
                    model=item.model_used,
                    input_tokens=item.input_tokens,
                    output_tokens=item.output_tokens,
                    estimated_cost=item.estimated_cost,
                    latency_ms=latency_ms,
                    created_at=utcnow(),
                )
            )

        logger.info(
            "message_processed",
            extra={
                "customer_id": str(customer.id),
                "conversation_id": str(conversation.id),
                "channel": message.channel,
                "route": route.model,
                "route_reason": route.reason,
                "model": generation.model_used,
                "handoff": decision.required,
                "latency_ms": latency_ms,
                "estimated_cost": cost,
            },
        )
        await self.events.publish(
            DomainEvent(
                MESSAGE_PROCESSED,
                {
                    "customer_id": str(customer.id),
                    "conversation_id": str(conversation.id),
                    "route": route.model,
                    "correlation_id": correlation_id,
                },
            )
        )
        steps.append(f"model:{generation.model_used}")
        steps.append(f"cost:{cost}")
        return AgentResponse(
            response_text=response_text,
            customer_id=customer.id,
            conversation_id=conversation.id,
            model_used=generation.model_used,
            route=str(route.model),
            route_reason=route.reason,
            confidence=generation.confidence,
            actions=[Action(result.type, result.payload) for result in results if result.status == "executed"],
            handoff_required=decision.required,
            handoff_reason=decision.reason,
            knowledge_sources=sources,
            usage=usage,
            latency_ms=latency_ms,
            logs=steps,
            language=language,
            correlation_id=correlation_id,
            handoff_id=handoff_id,
        )

    async def _generate(
        self,
        context,
        route: RouteDecision,
        generations: list[LLMGeneration],
    ) -> tuple[LLMGeneration, RouteDecision]:
        provider: LLMProvider = self.llm_for_tier(str(route.model))
        generation = await provider.generate_response(context, route)
        generations.append(generation)
        if str(route.model) == "small" and generation.confidence < self.confidence_threshold:
            route = RouteDecision("big", "low_confidence_fallback", generation.confidence)
            provider = self.llm_for_tier("big")
            generation = await provider.generate_response(context, route)
            generations.append(generation)
        return generation, route

    def _prepare(self, message: InboundMessage) -> InboundMessage:
        try:
            Channel(message.channel)
        except ValueError as exc:
            raise InvalidMessage(f"unsupported channel: {message.channel}") from exc
        text = (message.text or "").strip()
        if not text:
            raise InvalidMessage("text is empty")
        if len(text) > 4000:
            raise InvalidMessage("text is too long")
        metadata = scrub_mapping(message.metadata)
        if len(json.dumps(metadata, default=str)) > 8000:
            raise InvalidMessage("metadata is too large")
        message.text = text
        message.metadata = metadata
        return message

    async def _language(self, message: InboundMessage) -> str:
        detected = await self.language_detector.detect(message.text)
        hint = (message.language_hint or "").strip().lower()
        if detected == "mixed":
            return "mixed"
        if detected != "unknown":
            return detected
        if hint in ("ru", "ky", "mixed"):
            return hint
        return self.default_language

    async def _business(self, explicit: UUID | None):
        if explicit is not None:
            business = await self.businesses.get(explicit)
            if business is None:
                raise BusinessNotFound(f"business {explicit} was not found")
            return business
        if self.default_business_id:
            business = await self.businesses.get(UUID(self.default_business_id))
            if business is None:
                raise BusinessNotFound("configured business was not found")
            return business
        rows = await self.businesses.list_all()
        if len(rows) == 1:
            return rows[0]
        named = await self.businesses.get_by_name("Demo Realty")
        if named is not None:
            return named
        raise BusinessNotFound("business_id is required")

    async def _conversation(self, customer_id: UUID, channel: str) -> Conversation:
        existing = await self.conversations.get_open(customer_id, channel)
        if existing is not None:
            return existing
        now = utcnow()
        conversation = Conversation(
            id=uuid4(),
            customer_id=customer_id,
            channel=channel,
            started_at=now,
            ended_at=None,
            summary=None,
            created_at=now,
            updated_at=now,
        )
        return await self.conversations.add(conversation)

    async def _store_user_message(self, message: InboundMessage, customer_id: UUID, conversation_id: UUID) -> Message:
        now = utcnow()
        metadata = dict(message.metadata)
        if message.message_id:
            metadata["external_message_id"] = message.message_id
        stored = Message(
            id=uuid4(),
            conversation_id=conversation_id,
            customer_id=customer_id,
            role=MessageRole.user,
            text=message.text,
            timestamp=message.timestamp or now,
            metadata=metadata,
            created_at=now,
        )
        return await self.messages.add(stored)

    async def _reload_customer(self, customer_id: UUID):
        customer = await self.resolver.customers.get(customer_id)
        if customer is None:
            raise CustomerNotFound("customer disappeared during processing")
        return customer


def _human_phrase(language: str) -> str:
    if language == "ky":
        return "Макул, суроону менеджерге берем."
    return "Конечно, передам диалог менеджеру."


def _as_assistant_preview(conversation: Conversation, customer_id: UUID, text: str) -> Message:
    now = utcnow()
    return Message(
        id=uuid4(),
        conversation_id=conversation.id,
        customer_id=customer_id,
        role=MessageRole.assistant,
        text=text,
        timestamp=now,
        metadata={},
        created_at=now,
    )


def _handoff_id(results) -> UUID | None:
    for result in results:
        raw = result.payload.get("handoff_id")
        if result.type == ActionType.handoff and raw:
            return UUID(str(raw))
    return None
