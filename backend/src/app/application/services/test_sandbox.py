"""Adapters for the real agent pipeline with no live customer or channel writes."""

from dataclasses import dataclass, field
from math import isfinite
from uuid import uuid4

from pydantic import TypeAdapter

from app.application.services.customer_resolver import CustomerResolver
from app.application.services.memory_service import MemoryService
from app.container import build_agent
from app.domain.models import ActionResult, Conversation, Customer, CustomerSummary, Message, utcnow
from app.infrastructure.ai.mock_llm import MockLLMProvider
from app.infrastructure.events.bus import InMemoryEventBus


@dataclass
class TestState:
    customer: Customer
    conversation: Conversation
    summary: CustomerSummary | None = None
    messages: list[Message] = field(default_factory=list)


STATE = TypeAdapter(TestState)


def initial_state(business_id):
    now, customer_id = utcnow(), uuid4()
    return TestState(
        Customer(customer_id, None, "unknown", "new", None, "cli", None, now, now, business_id),
        Conversation(uuid4(), customer_id, "cli", now, None, None, now, now, business_id),
    )


class TestCustomers:
    def __init__(self, state):
        self.state = state

    async def get(self, ident):
        return self.state.customer if ident == self.state.customer.id else None

    async def get_by_channel(self, business_id, channel, external_id):
        return self.state.customer if business_id == self.state.customer.business_id else None

    async def save(self, customer):
        self.state.customer = customer
        return customer


class TestSummaries:
    def __init__(self, state):
        self.state = state

    async def get(self, ident):
        return self.state.summary

    async def upsert(self, summary):
        self.state.summary = summary
        return summary


class TestConversations:
    def __init__(self, state):
        self.state = state

    async def get_open(self, customer_id, channel):
        return self.state.conversation

    async def touch_summary(self, ident, summary):
        self.state.conversation.summary = summary

    async def release_expired_pause(self, ident, since):
        return None


class TestMessages:
    def __init__(self, state):
        self.state = state

    async def add(self, message):
        self.state.messages.append(message)
        return message

    async def list_context(self, customer_id, limit=20):
        return self.state.messages[-limit:]

    async def list_for_conversation(self, ident):
        return self.state.messages

    async def find_by_external_id(self, conversation_id, external_id):
        return next((m for m in self.state.messages if m.metadata.get("external_message_id") == external_id), None)


class TestLogs:
    async def add_interaction(self, entry):
        return entry

    async def add_usage(self, entry):
        return entry


class TestHandoffs:
    """The sandbox never stores a handoff: nothing is open, nothing is accepted."""

    async def find_open(self, conversation_id, reason):
        return None

    async def find_accepted(self, conversation_id, since=None):
        return None


class TestActions:
    def __init__(self, state):
        self.state = state

    async def execute(self, actions, ctx):
        results = []
        for action in actions:
            if action.type == "handoff":
                self.state.conversation.mode = "human"
                self.state.conversation.mode_version += 1
            results.append(ActionResult(action.type, "executed", {"simulated": True, **action.payload}))
        return results


class TestLLM:
    """Bound model generations across both tiers; auxiliary memory stays local."""

    def __init__(self, provider, meter):
        self.provider, self.meter = provider, meter
        self.local = MockLLMProvider("test_memory", "small")

    async def generate_response(self, context, route):
        from app.domain.errors import ProviderTransientError, ProviderUnavailable

        if self.meter["calls"] >= 2:
            raise ProviderTransientError("test generation limit")
        self.meter["calls"] += 1
        try:
            generation = await self.provider.generate_response(context, route)
        except ProviderTransientError:
            raise ProviderTransientError("test model temporarily unavailable") from None
        except ProviderUnavailable:
            raise ProviderUnavailable("test model unavailable") from None
        if not isfinite(generation.estimated_cost) or generation.estimated_cost < 0:
            raise ProviderUnavailable("test model cost unavailable")
        self.meter["cost"] += generation.estimated_cost
        return generation

    async def summarize(self, messages, previous):
        return await self.local.summarize(messages, previous)

    async def extract_customer_data(self, text):
        return await self.local.extract_customer_data(text)


def test_agent(session, runtime, state):
    agent = build_agent(session, runtime)
    events = InMemoryEventBus()
    customers = TestCustomers(state)
    agent.resolver = CustomerResolver(customers, events)
    agent.memory = MemoryService(customers, TestSummaries(state))
    agent.conversations = TestConversations(state)
    agent.messages = TestMessages(state)
    agent.actions = TestActions(state)
    agent.logs = TestLogs()
    agent.events = events
    agent.handoffs = TestHandoffs()
    agent.chat_budget_s = min(22.0, runtime.settings.chat_turn_budget_s)
    meter = {"calls": 0, "cost": 0.0}
    providers = {}

    def llm(tier):
        if tier not in providers:
            providers[tier] = TestLLM(runtime.providers.llm(tier), meter)
        return providers[tier]

    agent.llm_for_tier = llm
    return agent, meter
