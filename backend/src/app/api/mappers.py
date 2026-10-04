"""Map domain records to API schemas."""

from app.api.schemas import (
    ActionOut,
    AgentResponseOut,
    ConversationOut,
    CustomerOut,
    HandoffOut,
    KnowledgeOut,
    KnowledgeSourceOut,
    MeetingOut,
    MessageOut,
    MetricsOut,
    SummaryOut,
    UsageOut,
)
from app.domain.models import (
    AgentResponse,
    Conversation,
    Customer,
    CustomerSummary,
    HandoffRequest,
    KnowledgeItem,
    Meeting,
    Message,
    MetricsSnapshot,
)


def agent_out(response: AgentResponse) -> AgentResponseOut:
    return AgentResponseOut(
        response_text=response.response_text,
        customer_id=response.customer_id,
        conversation_id=response.conversation_id,
        model_used=response.model_used,
        route=response.route,
        route_reason=response.route_reason,
        confidence=response.confidence,
        actions=[ActionOut(type=item.type, payload=item.payload) for item in response.actions],
        handoff_required=response.handoff_required,
        handoff_reason=response.handoff_reason,
        knowledge_sources=[
            KnowledgeSourceOut(id=item.id, title=item.title, category=item.category)
            for item in response.knowledge_sources
        ],
        usage=UsageOut(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            estimated_cost=response.usage.estimated_cost,
            latency_ms=response.usage.latency_ms,
        ),
        latency_ms=response.latency_ms,
        logs=response.logs,
        language=response.language,
        correlation_id=response.correlation_id,
        handoff_id=response.handoff_id,
    )


def customer_out(customer: Customer) -> CustomerOut:
    return CustomerOut(
        id=customer.id,
        phone=customer.phone,
        language=customer.language,
        status=customer.status,
        need=customer.need,
        preferred_contact_channel=customer.preferred_contact_channel,
        merged_into_id=customer.merged_into_id,
        created_at=customer.created_at,
        updated_at=customer.updated_at,
    )


def message_out(message: Message) -> MessageOut:
    return MessageOut(
        id=message.id,
        conversation_id=message.conversation_id,
        customer_id=message.customer_id,
        role=message.role,
        text=message.text,
        timestamp=message.timestamp,
        metadata=message.metadata,
    )


def conversation_out(conversation: Conversation) -> ConversationOut:
    return ConversationOut(
        id=conversation.id,
        customer_id=conversation.customer_id,
        channel=conversation.channel,
        started_at=conversation.started_at,
        ended_at=conversation.ended_at,
        summary=conversation.summary,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


def summary_out(summary: CustomerSummary) -> SummaryOut:
    return SummaryOut(
        customer_id=summary.customer_id,
        summary=summary.summary,
        need=summary.need,
        language=summary.language,
        status=summary.status,
        important_facts=summary.important_facts,
        updated_at=summary.updated_at,
    )


def handoff_out(handoff: HandoffRequest) -> HandoffOut:
    return HandoffOut(
        id=handoff.id,
        customer_id=handoff.customer_id,
        conversation_id=handoff.conversation_id,
        reason=handoff.reason,
        priority=handoff.priority,
        summary=handoff.summary,
        recent_messages=handoff.recent_messages,
        status=handoff.status,
        created_at=handoff.created_at,
        updated_at=handoff.updated_at,
    )


def knowledge_out(item: KnowledgeItem) -> KnowledgeOut:
    return KnowledgeOut(
        id=item.id,
        business_id=item.business_id,
        category=item.category,
        title=item.title,
        content=item.content,
        metadata=item.metadata,
        active=item.active,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def meeting_out(meeting: Meeting) -> MeetingOut:
    return MeetingOut(
        id=meeting.id,
        customer_id=meeting.customer_id,
        business_id=meeting.business_id,
        datetime=meeting.scheduled_at,
        status=meeting.status,
        notes=meeting.notes,
        created_at=meeting.created_at,
    )


def metrics_out(snapshot: MetricsSnapshot) -> MetricsOut:
    return MetricsOut(
        total_conversations=snapshot.total_conversations,
        total_messages=snapshot.total_messages,
        handled_without_human=snapshot.handled_without_human,
        handed_off=snapshot.handed_off,
        meetings_scheduled=snapshot.meetings_scheduled,
        average_first_response_time_ms=snapshot.average_first_response_time_ms,
        average_response_time_ms=snapshot.average_response_time_ms,
        small_model_percentage=snapshot.small_model_percentage,
        big_model_percentage=snapshot.big_model_percentage,
        russian_percentage=snapshot.russian_percentage,
        kyrgyz_percentage=snapshot.kyrgyz_percentage,
        mixed_percentage=snapshot.mixed_percentage,
        average_dialog_cost=snapshot.average_dialog_cost,
        handoff_rate=snapshot.handoff_rate,
    )
