"""Orchestrates one inbound message. It does not implement a model."""

import asyncio
import json
import logging
import time
from dataclasses import replace
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from app.application.services.context_builder import ContextBuilder, assistant_name
from app.application.services.customer_resolver import CustomerResolver
from app.application.services.grounded_reply import is_unusable_reply, is_weasel_reply, quote_knowledge
from app.application.services.handoff_service import evaluate_handoff
from app.application.services.memory_service import MemoryService, read_unclear_count, write_unclear_count
from app.application.services.response_validator import ResponseValidator
from app.correlation import get_correlation_id, get_request_id
from app.domain.agent_settings import configured_text, published_settings
from app.domain.enums import PHONE_CHANNELS, ActionType, Channel, ConversationMode, InboundKind, MessageRole, RouteModel
from app.domain.errors import (
    BusinessNotFound,
    CustomerNotFound,
    DuplicateMessage,
    InvalidMessage,
    ProviderTransientError,
    ProviderUnavailable,
)
from app.domain.events import MESSAGE_PROCESSED, MESSAGE_RECEIVED, DomainEvent
from app.domain.models import (
    Action,
    ActionContext,
    AgentResponse,
    Conversation,
    InboundMessage,
    InteractionLog,
    KnowledgeSource,
    HandoffDecision,
    LLMGeneration,
    Message,
    RouteDecision,
    Usage,
    UsageLog,
    utcnow,
)
from app.domain.phrases import (
    drop_reintroduction,
    fallback_phrase,
    fit_for_voice,
    human_phrase,
    unknown_phrase,
    unsupported_phrase,
    with_ai_disclosure,
)
from app.domain.scheduling import has_slot
from app.domain.ports import (
    ActionExecutor,
    BusinessStore,
    ConversationStore,
    EventBus,
    HandoffStore,
    KnowledgeRetriever,
    LanguageDetector,
    LogStore,
    MessageStore,
    Router,
)
from app.domain.spoken_numbers import spoken_to_digits
from app.domain.text_signals import analyze_message, find_phones, phone_from_id
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
        handoffs: HandoffStore | None = None,
        voice_budget_s: float = 7.0,
        chat_budget_s: float = 25.0,
        small_enabled: bool = True,
        manager_pause_hours: float = 24.0,
        stt_low_confidence: float = 0.6,
        voice_hedge_after_s: float = 3.0,
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
        self.handoffs = handoffs
        # Seconds the model calls of one turn may take. A caller hears silence
        # while we wait, so voice gets a short budget and a canned line after it.
        self.voice_budget_s = voice_budget_s
        self.chat_budget_s = chat_budget_s
        # Until the local small model exists its turns go to the big one; the
        # router's own label stays in route_reason for training the classifier.
        self.small_enabled = small_enabled
        self.manager_pause_hours = manager_pause_hours
        self.stt_low_confidence = stt_low_confidence
        # Voice only: a second request for the same turn after this many seconds. 0 = off.
        self.voice_hedge_after_s = voice_hedge_after_s

    async def process_message(self, message: InboundMessage) -> AgentResponse:
        started = time.perf_counter()
        steps: list[str] = []
        timings: dict[str, int] = {}
        mark = started

        def lap(name: str) -> None:
            nonlocal mark
            now = time.perf_counter()
            timings[name] = int((now - mark) * 1000)
            mark = now

        message = self._prepare(message)
        correlation_id = message.correlation_id or get_correlation_id() or str(uuid4())
        request_id = message.request_id or get_request_id() or message.message_id or str(uuid4())

        business = await self._business(message.business_id)
        customer = await self.resolver.resolve_customer(message, business.id)
        customer = await self.resolver.remember_contact_phone(customer, message.text)
        language = await self._language(message, business)
        customer = await self.memory.update_language(customer, language)
        steps.append(f"customer:{customer.id}")

        conversation = await self._conversation(customer.id, message, business.id)
        if message.message_id:
            seen = await self.messages.find_by_external_id(conversation.id, message.message_id)
            if seen is not None:
                # Webhook retry: answer with the stored reply, do not run or bill twice.
                return await self._replay(seen, customer.id, language, correlation_id, started)
        try:
            incoming = await self._store_user_message(message, customer.id, conversation.id)
        except DuplicateMessage:
            # The same retry is being processed right now by another request.
            seen = await self.messages.find_by_external_id(conversation.id, message.message_id or "")
            if seen is None:
                raise
            return await self._replay(seen, customer.id, language, correlation_id, started)
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

        conversation, paused = await self._pause_reason(conversation, message)
        if paused:
            # A manager owns this dialog, or the agent is off on the connection.
            # The message is in history; the agent stays quiet.
            return _paused_response(
                customer.id, conversation.id, language, correlation_id, started, paused, conversation.mode_version
            )
        if message.kind in (InboundKind.start, InboundKind.unsupported):
            return await self._service_reply(
                message, business, customer.id, conversation, language, correlation_id, started
            )

        summary = await self.memory.get_summary(customer.id)
        history = await self.messages.list_context(customer.id, limit=20)
        recent = "\n".join(item.text for item in history[-4:])
        knowledge = await self.retriever.retrieve(business.id, message.text, recent=recent)
        context = self.context_builder.build(
            business=business,
            knowledge=knowledge,
            customer=customer,
            summary=summary,
            recent_messages=history,
            current_message=message.text,
            language=language,
            current_message_id=incoming.id,
            channel=message.channel,
        )
        context.stt_confidence = _stt_confidence(message.metadata)
        steps.append("knowledge:" + ",".join(hit.item.title for hit in knowledge))
        lap("prepare_ms")

        route = await self.router.select_model(context)
        if context.stt_confidence is not None and context.stt_confidence < self.stt_low_confidence:
            # Misheard speech is the big model's job: it copes with fragments and mixed language.
            route = RouteDecision(RouteModel.big, "uncertain_stt", route.confidence)
        generations: list[LLMGeneration] = []
        budget = self.voice_budget_s if message.channel == Channel.voice else self.chat_budget_s
        generation, route = await self._generate(context, route, generations, started + budget)
        model_failed = not generations and not generation.model_used.startswith("rules:")
        steps.append(f"route:{route.model}:{route.reason}")
        lap("model_ms")

        signals = analyze_message(message.text)
        if not signals.meeting and has_slot(message.text) and _asked_for_slot(history):
            # "В субботу в 15:00" answers our "какой день вам удобен?": same meeting request.
            signals = replace(signals, meeting=True)
            steps.append("meeting_slot_answer")
        assessment = self.validator.assess(message.text, context)
        # Rotates fixed lines inside one dialog so the agent does not repeat itself.
        seed = f"{conversation.id}:{len(history)}"
        slot_named = signals.meeting and has_slot(message.text)
        intent = _intent(
            signals, slot_named, mid_dialog=bool(context.recent_messages), phone_given=bool(find_phones(message.text))
        )
        if signals.human_request:
            already_open = await self.handoffs.find_open(conversation.id, "user_requested_human") is not None
            response_text = human_phrase(language, message.channel, seed, again=already_open)
            steps.append("human_phrase_again" if already_open else "human_phrase")
        elif assessment.factual and not assessment.answerable and (
            not context.knowledge or assessment.topic == "installment" or configured_text(business.profile, "fallback")
        ):
            response_text = self._unknown_reply(context, assessment.topic, language, seed)
        else:
            response_text = generation.text
        wants_listings = bool(
            context.knowledge
            and not (assessment.factual and not assessment.answerable and configured_text(business.profile, "fallback"))
            and (
                assessment.factual
                or signals.money
                or signals.catalog
                or signals.recommend
            )
            and assessment.topic != "installment"
        )
        if is_unusable_reply(response_text) or (wants_listings and is_weasel_reply(response_text)):
            if wants_listings:
                response_text = quote_knowledge(context)
                steps.append("grounded_fallback")
            elif not assessment.factual:
                response_text = fallback_phrase(intent, language, seed)
                steps.append(f"fallback:{intent}")

        if message.channel == Channel.voice:
            plain = drop_reintroduction(response_text, assistant_name(business))
            if plain != response_text:
                response_text = plain
                steps.append("voice_no_reintro")
        if message.channel == Channel.voice:
            shorter = fit_for_voice(response_text)
            if shorter != response_text:
                response_text = shorter
                steps.append("voice_trimmed")

        # A meeting row needs a slot the customer actually named. "Запишите нас"
        # alone becomes a question about the day plus a handoff, not 15:00 tomorrow.
        actions = [
            item
            for item in generation.actions
            if item.type != ActionType.handoff
            and (item.type != ActionType.schedule_meeting or slot_named or _payload_has_slot(item.payload))
        ]
        if slot_named and not any(item.type == ActionType.schedule_meeting for item in actions):
            actions.append(Action(ActionType.schedule_meeting, {"text": message.text}))
        if customer.phone is None and customer.contact_phone is None and message.channel not in PHONE_CHANNELS:
            if signals.meeting or (assessment.answerable and assessment.factual):
                actions.append(Action(ActionType.request_phone, {}))
        extracted = await self.llm_for_tier("small").extract_customer_data(message.text)
        if extracted.need:
            actions.append(Action(ActionType.update_customer, {"need": extracted.need, "language": language}))

        extra = json.dumps([item.payload for item in actions], ensure_ascii=False, default=str)
        validation = self.validator.validate(response_text, context, extra=extra)
        if not validation.safe and wants_listings:
            response_text = quote_knowledge(context)
            validation = self.validator.validate(response_text, context, extra=extra)
            steps.append("grounded_fallback")
        if not validation.safe:
            if assessment.factual:
                response_text = self._unknown_reply(context, assessment.topic, language, seed)
            else:
                response_text = fallback_phrase(intent, language, seed)
            steps.append(f"validator:{validation.reason}")
            validation = self.validator.validate(response_text, context, extra=extra)
        if not response_text.strip():
            # Model down or out of time and no listing to quote: never send silence.
            if assessment.factual:
                response_text = self._unknown_reply(context, assessment.topic, language, seed)
            else:
                response_text = fallback_phrase(intent, language, seed)
            steps.append("empty_draft_fallback")
            validation = self.validator.validate(response_text, context, extra=extra)

        unclear = read_unclear_count(summary.important_facts if summary else [])
        if signals.unclear_confirmation or (not assessment.factual and generation.confidence < 0.55):
            unclear += 1
        elif assessment.answerable or generation.confidence >= self.confidence_threshold:
            unclear = 0

        decision = evaluate_handoff(signals, assessment, generation, validation, unclear, model_failed=model_failed)
        if not decision.required and response_text == generation.text and (
            generation.handoff_required or _promises_followup(response_text)
        ):
            # The model said "уточню у менеджера" for a fact the lexicon did not
            # catch (guarantee, delivery terms...). The promise needs a real task,
            # whether or not the model remembered to set its handoff flag.
            # A customer leaving a number is the next sales step, not a missing fact.
            if find_phones(message.text):
                decision = HandoffDecision(required=True, reason="ready_for_meeting", priority="high")
            else:
                decision = HandoffDecision(required=True, reason="no_knowledge", priority="normal")
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
        if generation.memory and response_text == generation.text and validation.safe:
            # The model's own note is richer than the heuristic one. It is kept
            # only when its reply went out unchanged: a draft the validator
            # rejected may carry the same invented fact into memory.
            draft.summary = generation.memory
            draft.need = generation.need or draft.need
            steps.append("memory:model")
        draft.important_facts = write_unclear_count(draft.important_facts, unclear)
        await self.memory.write_summary(customer, draft, language)
        await self.conversations.touch_summary(conversation.id, draft.summary)

        if message.channel != Channel.voice and not any(
            item.role == MessageRole.assistant and item.conversation_id == conversation.id for item in history
        ):
            # A call opens with the platform greeting that already says "ИИ-ассистент".
            # A chat has no such greeting, so the first reply carries it.
            disclosed = with_ai_disclosure(response_text, language, assistant_name(business), business.name)
            if disclosed != response_text:
                response_text = disclosed
                steps.append("ai_disclosure")

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

        lap("post_ms")
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
            timings=timings,
            stt_confidence=context.stt_confidence,
            business_id=business.id,
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
            mode_version=conversation.mode_version,
            reply_message_id=assistant.id,
        )

    async def _pause_reason(self, conversation: Conversation, message: InboundMessage) -> tuple[Conversation, str | None]:
        """Why the agent must not answer this turn, or None.

        A takeover older than MANAGER_PAUSE_HOURS (when > 0) is released here:
        the dialog goes back to `ai` with a new mode version.
        """

        if conversation.mode == ConversationMode.human:
            since = self._pause_since()
            if since is None:
                return conversation, "manager_active"
            released = await self.conversations.release_expired_pause(conversation.id, since)
            if released is None:
                return conversation, "manager_active"
            conversation = released
            logger.info("manager_pause_expired", extra={"conversation_id": str(conversation.id)})
        if not message.auto_reply:
            return conversation, "agent_disabled"
        return conversation, None

    async def _service_reply(
        self,
        message: InboundMessage,
        business,
        customer_id: UUID,
        conversation: Conversation,
        language: str,
        correlation_id: str,
        started: float,
    ) -> AgentResponse:
        """Telegram /start and unsupported attachments: a fixed line, no model call.

        The unsupported notice is not repeated back to back, so a customer who
        sends three photos gets it once.
        """

        history = await self.messages.list_for_conversation(conversation.id)
        said_before = any(item.role == MessageRole.assistant for item in history)
        kind = str(message.kind)
        if kind == InboundKind.unsupported:
            last = next((item for item in reversed(history) if item.role == MessageRole.assistant), None)
            if last is not None and last.metadata.get("service") == InboundKind.unsupported:
                return _paused_response(
                    customer_id, conversation.id, language, correlation_id, started, "notice_already_sent",
                    conversation.mode_version, handoff=False,
                )
            text = unsupported_phrase(language)
        else:
            text = fallback_phrase("greeting", language, str(conversation.id))
            greeting = configured_text(business.profile, "greeting", 1000)
            if greeting and not said_before and message.channel != Channel.voice:
                customer = await self._reload_customer(customer_id)
                context = self.context_builder.build(business=business, customer=customer,
                    knowledge=await self.retriever.retrieve(business.id, message.text), summary=None,
                    recent_messages=history, current_message=message.text, language=language, channel=message.channel)
                if self.validator.validate(greeting, context).safe:
                    text = greeting
        if not said_before:
            text = with_ai_disclosure(text, language, assistant_name(business), business.name)
        now = utcnow()
        assistant = Message(
            id=uuid4(),
            conversation_id=conversation.id,
            customer_id=customer_id,
            role=MessageRole.assistant,
            text=text,
            timestamp=now,
            metadata={"service": kind, "model": f"rules:{kind}", "route": "rules", "handoff": False},
            created_at=now,
        )
        await self.messages.add(assistant)
        latency_ms = int((time.perf_counter() - started) * 1000)
        return AgentResponse(
            response_text=text,
            customer_id=customer_id,
            conversation_id=conversation.id,
            model_used=f"rules:{kind}",
            route="rules",
            route_reason=kind,
            confidence=1.0,
            actions=[],
            handoff_required=False,
            handoff_reason=None,
            knowledge_sources=[],
            usage=Usage(0, 0, 0.0, latency_ms),
            latency_ms=latency_ms,
            logs=[f"service:{kind}"],
            language=language,
            correlation_id=correlation_id,
            mode_version=conversation.mode_version,
            reply_message_id=assistant.id,
        )

    async def _generate(
        self,
        context,
        route: RouteDecision,
        generations: list[LLMGeneration],
        deadline: float,
    ) -> tuple[LLMGeneration, RouteDecision]:
        if route.reason == "greeting" and context.channel != Channel.voice and not any(
            item.role == MessageRole.assistant for item in context.recent_messages
        ):
            greeting = configured_text(context.business.profile, "greeting", 1000)
            if greeting and self.validator.validate(greeting, context).safe:
                return LLMGeneration(greeting, [], False, None, 1.0, "rules:business_greeting", 0, 0, 0.0), route
        if route.reason == "human_request" or (
            route.reason in FIXED_REPLY_REASONS
            and getattr(context, "channel", None) == Channel.voice
            and len(context.current_message.split()) <= 2
        ):
            # The reply is a fixed line chosen below; a 3-5 s model call would only be thrown away.
            return LLMGeneration("", [], False, None, 1.0, "rules:fixed_reply", 0, 0, 0.0), route
        if str(route.model) == "small" and not self.small_enabled:
            route = RouteDecision(RouteModel.big, f"{route.reason}:no_small"[:64], route.confidence)
        generation = await self._call(str(route.model), context, route, generations, deadline)
        if str(route.model) == "small" and generation.confidence < self.confidence_threshold:
            route = RouteDecision("big", "low_confidence_fallback", generation.confidence)
            generation = await self._call("big", context, route, generations, deadline)
        if is_unusable_reply(generation.text) and not generation.model_used.endswith((":timeout", ":unavailable")):
            # Free and small models sometimes answer "User Safety: safe" or
            # nothing. One retry is cheaper than a canned line mid-sale.
            route = RouteDecision("big", "unusable_retry", generation.confidence)
            generation = await self._call("big", context, route, generations, deadline)
        return generation, route

    async def _call(
        self,
        tier: str,
        context,
        route: RouteDecision,
        generations: list[LLMGeneration],
        deadline: float,
    ) -> LLMGeneration:
        """One model call within the turn's budget. Failure or timeout is an empty draft, not a 503."""

        remaining = deadline - time.perf_counter()
        if remaining < 0.5:
            return LLMGeneration("", [], False, None, 0.0, f"{tier}:timeout", 0, 0, 0.0)
        hedge_after = self.voice_hedge_after_s if getattr(context, "channel", None) == Channel.voice else 0.0
        try:
            generation = await self._first_reply(self.llm_for_tier(tier), context, route, remaining, hedge_after)
        except TimeoutError:
            logger.warning("model_timeout", extra={"tier": tier, "budget_s": round(remaining, 2)})
            return LLMGeneration("", [], False, None, 0.0, f"{tier}:timeout", 0, 0, 0.0)
        except ProviderTransientError as exc:
            logger.warning("model_transient_error", extra={"tier": tier, "error": exc.message})
            return LLMGeneration("", [], False, None, 0.0, f"{tier}:unavailable", 0, 0, 0.0)
        except ProviderUnavailable as exc:
            # Bad key, no credits, every model retired. The customer still gets
            # a fixed line and a manager; the error level makes it visible to us.
            logger.error("model_unavailable", extra={"tier": tier, "error": exc.message})
            return LLMGeneration("", [], False, None, 0.0, f"{tier}:unavailable", 0, 0, 0.0)
        generations.append(generation)
        return generation

    @staticmethod
    async def _first_reply(llm, context, route: RouteDecision, timeout: float, hedge_after: float) -> LLMGeneration:
        """The model's reply within `timeout`. A slow call gets a twin after `hedge_after` seconds.

        A provider sometimes takes 5+ s on one request out of dozens. On a call that
        is dead air, so a second identical request races the first and the earlier
        answer wins. It costs one extra call, and only on slow turns.
        """

        started = time.perf_counter()
        tasks = {asyncio.ensure_future(llm.generate_response(context, route))}
        try:
            if 0 < hedge_after < timeout - 1.0:
                done, _ = await asyncio.wait(tasks, timeout=hedge_after)
                if not done:
                    logger.info("model_hedged", extra={"after_s": hedge_after})
                    tasks.add(asyncio.ensure_future(llm.generate_response(context, route)))
            error: BaseException | None = None
            while tasks:
                left = timeout - (time.perf_counter() - started)
                if left <= 0:
                    break
                done, tasks = await asyncio.wait(tasks, timeout=left, return_when=asyncio.FIRST_COMPLETED)
                if not done:
                    break
                for task in done:
                    if task.exception() is None:
                        return task.result()
                    error = task.exception()
            if error is not None and not tasks:
                raise error
            raise TimeoutError
        finally:
            for task in tasks:
                task.cancel()

    def _pause_since(self) -> datetime | None:
        if self.manager_pause_hours <= 0:
            return None
        return utcnow() - timedelta(hours=self.manager_pause_hours)

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
        if message.channel == Channel.voice:
            # Speech recognition writes "восемьдесят пять тысяч"; retrieval and
            # the validator match digits. The heard text stays in metadata.
            spoken = spoken_to_digits(text)
            if spoken != text:
                metadata["stt_text"] = text
                text = spoken
        if len(json.dumps(metadata, default=str)) > 8000:
            raise InvalidMessage("metadata is too large")
        message.text = text
        message.metadata = metadata
        return message

    def _unknown_reply(self, context, topic, language, seed):
        fallback = configured_text(context.business.profile, "fallback", 1000)
        if fallback and self.validator.validate(fallback, context).safe:
            return fallback
        return unknown_phrase(topic, language, seed)

    async def _language(self, message: InboundMessage, business=None) -> str:
        detected = await self.language_detector.detect(message.text)
        hint = (message.language_hint or "").strip().lower()
        if detected == "mixed":
            return "mixed"
        if detected != "unknown":
            return detected
        if hint in ("ru", "ky", "en", "mixed"):
            return hint
        configured = published_settings(business.profile) if business else {}
        return configured.get("language", self.default_language)

    async def _replay(self, seen: Message, customer_id: UUID, language: str, correlation_id: str, started: float) -> AgentResponse:
        reply = await self.messages.reply_after(seen)
        meta = reply.metadata if reply else {}
        return AgentResponse(
            response_text=reply.text if reply else "",
            customer_id=customer_id,
            conversation_id=seen.conversation_id,
            model_used=str(meta.get("model") or "none"),
            route=str(meta.get("route") or "duplicate"),
            route_reason="duplicate_message",
            confidence=1.0,
            actions=[],
            handoff_required=bool(meta.get("handoff")),
            handoff_reason=None,
            knowledge_sources=[],
            usage=Usage(0, 0, 0.0, int((time.perf_counter() - started) * 1000)),
            latency_ms=int((time.perf_counter() - started) * 1000),
            logs=["duplicate_message"],
            language=language,
            correlation_id=correlation_id,
            send_reply=reply is not None,
            duplicate=True,
        )

    async def resolve_business(self, explicit: UUID | None = None, called: str | None = None):
        """Business for a turn: explicit id, the dialled number, configured default, or the only one.

        A business lists its Plumo numbers in `contacts.voice_numbers`.
        """

        if explicit is None and called:
            dialled = phone_from_id(called)
            if dialled:
                for business in await self.businesses.list_all():
                    numbers = (business.contacts or {}).get("voice_numbers") or []
                    if dialled in {phone_from_id(str(item)) for item in numbers}:
                        return business
        return await self._business(explicit)

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
        # Several businesses and no id: guessing would put one company's
        # customer into another's history.
        raise BusinessNotFound("business_id is required")

    async def _conversation(self, customer_id: UUID, message: InboundMessage, business_id: UUID) -> Conversation:
        existing = await self.conversations.get_open(customer_id, message.channel)
        if existing is not None:
            return existing
        now = utcnow()
        conversation = Conversation(
            id=uuid4(),
            customer_id=customer_id,
            channel=message.channel,
            started_at=now,
            ended_at=None,
            summary=None,
            created_at=now,
            updated_at=now,
            business_id=business_id,
            connection_id=message.connection_id,
            external_chat_id=message.reply_to,
            contact_name=message.contact_name,
            contact_handle=message.contact_handle,
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


def _paused_response(
    customer_id: UUID,
    conversation_id: UUID,
    language: str,
    correlation_id: str,
    started: float,
    reason: str = "manager_active",
    mode_version: int | None = None,
    *,
    handoff: bool | None = None,
) -> AgentResponse:
    latency_ms = int((time.perf_counter() - started) * 1000)
    # Only a manager's takeover is a handoff; a switched-off agent is a separate state.
    handoff = reason == "manager_active" if handoff is None else handoff
    return AgentResponse(
        response_text="",
        customer_id=customer_id,
        conversation_id=conversation_id,
        model_used="none",
        route="human" if reason == "manager_active" else "none",
        route_reason=reason,
        confidence=1.0,
        actions=[],
        handoff_required=handoff,
        handoff_reason=reason if handoff else None,
        knowledge_sources=[],
        usage=Usage(0, 0, 0.0, latency_ms),
        latency_ms=latency_ms,
        logs=[reason],
        language=language,
        correlation_id=correlation_id,
        send_reply=False,
        mode_version=mode_version,
    )


# Routes whose reply is always a fixed phrase (human_phrase / greeting / farewell),
# so the model is skipped. Only for a bare "привет" / "пока": "здравствуйте, ищу
# диван" carries a need the fixed line would ignore.
FIXED_REPLY_REASONS = frozenset({"human_request", "greeting", "farewell"})


_SLOT_QUESTIONS = ("какой день", "в какое время", "во сколько", "когда вам удобно", "когда удобно", "кайсы күнү", "саат канчада")


_FOLLOWUP = ("уточню", "узнаю у менеджера", "спрошу у менеджера", "менеджерден тактап")


def _promises_followup(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in _FOLLOWUP)


def _asked_for_slot(history: list[Message]) -> bool:
    """True when the agent's last line asked the customer for a day or time."""

    for item in reversed(history):
        if item.role == MessageRole.assistant:
            lowered = item.text.lower()
            return any(marker in lowered for marker in _SLOT_QUESTIONS)
    return False


def _intent(signals, slot_named: bool, mid_dialog: bool = False, phone_given: bool = False) -> str:
    if phone_given and not signals.factual:
        return "contact"
    if signals.meeting:
        return "meeting_set" if slot_named else "meeting_ask"
    if signals.farewell and not signals.factual:
        return "farewell"
    if signals.greeting and not signals.factual:
        return "greeting"
    return "continue" if mid_dialog else "other"


def _stt_confidence(metadata: dict) -> float | None:
    """Speech-recognition confidence a voice layer may attach to a turn, 0..1."""

    raw = (metadata or {}).get("stt_confidence")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(1.0, value))


def _payload_has_slot(payload: dict) -> bool:
    return any(str(payload.get(key) or "").strip() for key in ("datetime", "date", "time"))


def _handoff_id(results) -> UUID | None:
    for result in results:
        raw = result.payload.get("handoff_id")
        if result.type == ActionType.handoff and raw:
            return UUID(str(raw))
    return None
