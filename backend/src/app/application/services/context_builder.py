"""Assemble the only context a model is allowed to see."""

from app.domain.models import AgentContext, Business, Customer, CustomerSummary, KnowledgeHit, Message
from app.domain.phrases import AGENT_INSTRUCTIONS

RECENT_LIMIT = 8


class ContextBuilder:
    """LLM-agnostic context. Replace the model, not this builder."""

    def build(
        self,
        *,
        business: Business,
        knowledge: list[KnowledgeHit],
        customer: Customer,
        summary: CustomerSummary | None,
        recent_messages: list[Message],
        current_message: str,
        language: str,
        current_message_id=None,
    ) -> AgentContext:
        recent = list(recent_messages)
        if current_message_id is not None:
            recent = [item for item in recent if item.id != current_message_id]
        elif recent and recent[-1].role == "user" and recent[-1].text == current_message:
            recent = recent[:-1]
        return AgentContext(
            agent_instructions=AGENT_INSTRUCTIONS,
            business=business,
            knowledge=knowledge,
            customer=customer,
            summary=summary,
            recent_messages=recent[-RECENT_LIMIT:],
            current_message=current_message,
            language=language,
        )
