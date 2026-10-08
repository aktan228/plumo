"""SQLAlchemy repositories. They map rows to domain records and never leave the session open."""

from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import CustomerStatus
from app.domain.errors import CustomerNotFound, HandoffNotFound, InvalidState
from app.domain.models import (
    Business,
    Conversation,
    Customer,
    CustomerSummary,
    HandoffRequest,
    InteractionLog,
    KnowledgeItem,
    Meeting,
    Message,
    MetricsSnapshot,
    UsageLog,
    VoiceCall,
    utcnow,
)
from app.infrastructure.database.models import (
    BusinessRow,
    ConversationRow,
    CustomerChannelRow,
    CustomerRow,
    CustomerSummaryRow,
    HandoffRequestRow,
    InteractionLogRow,
    KnowledgeItemRow,
    MeetingRow,
    MessageRow,
    UsageLogRow,
    VoiceCallRow,
)


class CustomerRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, customer_id: UUID) -> Customer | None:
        row = await self.session.get(CustomerRow, customer_id)
        return _customer(row) if row else None

    async def get_by_phone(self, phone: str) -> Customer | None:
        stmt = select(CustomerRow).where(
            CustomerRow.phone == phone,
            CustomerRow.status != CustomerStatus.merged,
        )
        row = await self.session.scalar(stmt)
        return _customer(row) if row else None

    async def get_by_channel(self, channel: str, external_id: str) -> Customer | None:
        stmt = (
            select(CustomerRow)
            .join(CustomerChannelRow, CustomerChannelRow.customer_id == CustomerRow.id)
            .where(
                CustomerChannelRow.channel == channel,
                CustomerChannelRow.external_id == external_id,
            )
        )
        row = await self.session.scalar(stmt)
        if row is None:
            return None
        customer = _customer(row)
        if customer.merged_into_id is None:
            return customer
        return await self._live(customer.id)

    async def add(self, customer: Customer) -> Customer:
        self.session.add(_customer_row(customer))
        await self.session.flush()
        return customer

    async def save(self, customer: Customer) -> Customer:
        row = await self.session.get(CustomerRow, customer.id)
        if row is None:
            raise CustomerNotFound(f"customer {customer.id} was not found")
        row.phone = customer.phone
        row.language = customer.language
        row.status = customer.status
        row.need = customer.need
        row.preferred_contact_channel = customer.preferred_contact_channel
        row.merged_into_id = customer.merged_into_id
        row.updated_at = customer.updated_at
        await self.session.flush()
        return _customer(row)

    async def link_channel(self, customer_id: UUID, channel: str, external_id: str) -> None:
        stmt = select(CustomerChannelRow).where(
            CustomerChannelRow.channel == channel,
            CustomerChannelRow.external_id == external_id,
        )
        existing = await self.session.scalar(stmt)
        now = utcnow()
        if existing is not None:
            if existing.customer_id != customer_id:
                raise InvalidState("channel is already linked to another customer")
            return
        self.session.add(
            CustomerChannelRow(
                id=_new_id(),
                customer_id=customer_id,
                channel=channel,
                external_id=external_id,
                created_at=now,
                updated_at=now,
            )
        )
        await self.session.flush()

    async def merge(self, source_id: UUID, target_id: UUID) -> Customer:
        source = await self._live(source_id)
        target = await self._live(target_id)
        if source.id == target.id:
            return source

        now = utcnow()
        await self.session.execute(
            update(ConversationRow)
            .where(ConversationRow.customer_id == source.id)
            .values(customer_id=target.id, updated_at=now)
        )
        await self.session.execute(
            update(MessageRow).where(MessageRow.customer_id == source.id).values(customer_id=target.id)
        )
        await self.session.execute(
            update(CustomerChannelRow)
            .where(CustomerChannelRow.customer_id == source.id)
            .values(customer_id=target.id, updated_at=now)
        )
        await self.session.execute(
            update(HandoffRequestRow)
            .where(HandoffRequestRow.customer_id == source.id)
            .values(customer_id=target.id, updated_at=now)
        )
        await self.session.execute(
            update(MeetingRow)
            .where(MeetingRow.customer_id == source.id)
            .values(customer_id=target.id, updated_at=now)
        )
        await self.session.execute(
            update(InteractionLogRow)
            .where(InteractionLogRow.customer_id == source.id)
            .values(customer_id=target.id)
        )
        await self._merge_summaries(source.id, target.id, now)

        source_row = await self.session.get(CustomerRow, source.id)
        target_row = await self.session.get(CustomerRow, target.id)
        if source_row is None or target_row is None:
            raise CustomerNotFound("customer disappeared during merge")
        if target_row.phone is None and source_row.phone:
            moved = source_row.phone
            source_row.phone = None
            await self.session.flush()
            target_row.phone = moved
        else:
            source_row.phone = None
        if target_row.need is None and source_row.need:
            target_row.need = source_row.need
        if target_row.language in ("", "unknown") and source_row.language not in ("", "unknown"):
            target_row.language = source_row.language
        if target_row.preferred_contact_channel is None:
            target_row.preferred_contact_channel = source_row.preferred_contact_channel
        source_row.status = CustomerStatus.merged
        source_row.merged_into_id = target_row.id
        source_row.updated_at = now
        target_row.updated_at = now
        await self.session.flush()
        return _customer(target_row)

    async def _live(self, customer_id: UUID) -> Customer:
        current = await self.get(customer_id)
        if current is None:
            raise CustomerNotFound(f"customer {customer_id} was not found")
        seen: set[UUID] = set()
        while current.merged_into_id and current.merged_into_id not in seen:
            seen.add(current.id)
            nxt = await self.get(current.merged_into_id)
            if nxt is None:
                break
            current = nxt
        return current

    async def _merge_summaries(self, source_id: UUID, target_id: UUID, now) -> None:
        source = await self.session.get(CustomerSummaryRow, source_id)
        if source is None:
            return
        target = await self.session.get(CustomerSummaryRow, target_id)
        if target is None:
            self.session.add(
                CustomerSummaryRow(
                    customer_id=target_id,
                    summary=source.summary,
                    need=source.need,
                    language=source.language,
                    status=source.status,
                    important_facts=list(source.important_facts or []),
                    created_at=source.created_at,
                    updated_at=now,
                )
            )
            await self.session.delete(source)
            await self.session.flush()
            return
        facts = list(dict.fromkeys([*(target.important_facts or []), *(source.important_facts or [])]))
        if source.summary and source.summary not in (target.summary or ""):
            target.summary = f"{target.summary}\n{source.summary}".strip()
        target.important_facts = facts
        if not target.need and source.need:
            target.need = source.need
        target.updated_at = now
        await self.session.delete(source)
        await self.session.flush()


class ConversationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, conversation_id: UUID) -> Conversation | None:
        row = await self.session.get(ConversationRow, conversation_id)
        return _conversation(row) if row else None

    async def get_open(self, customer_id: UUID, channel: str) -> Conversation | None:
        stmt = (
            select(ConversationRow)
            .where(
                ConversationRow.customer_id == customer_id,
                ConversationRow.channel == channel,
                ConversationRow.ended_at.is_(None),
            )
            .order_by(ConversationRow.started_at.desc())
            .limit(1)
        )
        row = await self.session.scalar(stmt)
        return _conversation(row) if row else None

    async def add(self, conversation: Conversation) -> Conversation:
        self.session.add(_conversation_row(conversation))
        await self.session.flush()
        return conversation

    async def list_for_customer(self, customer_id: UUID) -> list[Conversation]:
        stmt = (
            select(ConversationRow)
            .where(ConversationRow.customer_id == customer_id)
            .order_by(ConversationRow.started_at.asc())
        )
        rows = (await self.session.scalars(stmt)).all()
        return [_conversation(row) for row in rows]

    async def touch_summary(self, conversation_id: UUID, summary: str) -> None:
        row = await self.session.get(ConversationRow, conversation_id)
        if row is None:
            return
        row.summary = summary
        row.updated_at = utcnow()
        await self.session.flush()


class MessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, message: Message) -> Message:
        self.session.add(_message_row(message))
        await self.session.flush()
        return message

    async def list_for_conversation(self, conversation_id: UUID) -> list[Message]:
        stmt = (
            select(MessageRow)
            .where(MessageRow.conversation_id == conversation_id)
            .order_by(MessageRow.timestamp.asc())
        )
        rows = (await self.session.scalars(stmt)).all()
        return [_message(row) for row in rows]

    async def list_for_customer(self, customer_id: UUID, limit: int = 100) -> list[Message]:
        stmt = (
            select(MessageRow)
            .where(MessageRow.customer_id == customer_id)
            .order_by(MessageRow.timestamp.desc())
            .limit(limit)
        )
        rows = list((await self.session.scalars(stmt)).all())
        rows.reverse()
        return [_message(row) for row in rows]

    async def find_by_external_id(self, conversation_id: UUID, external_id: str) -> Message | None:
        stmt = (
            select(MessageRow)
            .where(
                MessageRow.conversation_id == conversation_id,
                MessageRow.role == "user",
                MessageRow.metadata_json["external_message_id"].astext == external_id,
            )
            .limit(1)
        )
        row = await self.session.scalar(stmt)
        return _message(row) if row else None

    async def reply_after(self, message: Message) -> Message | None:
        """The assistant turn written right after `message`, if any."""

        stmt = (
            select(MessageRow)
            .where(
                MessageRow.conversation_id == message.conversation_id,
                MessageRow.role == "assistant",
                MessageRow.created_at >= message.created_at,
            )
            .order_by(MessageRow.created_at.asc())
            .limit(1)
        )
        row = await self.session.scalar(stmt)
        return _message(row) if row else None


class KnowledgeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, item_id: UUID) -> KnowledgeItem | None:
        row = await self.session.get(KnowledgeItemRow, item_id)
        return _knowledge(row) if row else None

    async def list_active(self, business_id: UUID) -> list[KnowledgeItem]:
        stmt = (
            select(KnowledgeItemRow)
            .where(
                KnowledgeItemRow.business_id == business_id,
                KnowledgeItemRow.active.is_(True),
            )
            .order_by(KnowledgeItemRow.title.asc())
        )
        rows = (await self.session.scalars(stmt)).all()
        return [_knowledge(row) for row in rows]

    async def list_items(self, business_id: UUID | None = None) -> list[KnowledgeItem]:
        stmt = select(KnowledgeItemRow).order_by(KnowledgeItemRow.title.asc())
        if business_id is not None:
            stmt = stmt.where(KnowledgeItemRow.business_id == business_id)
        rows = (await self.session.scalars(stmt)).all()
        return [_knowledge(row) for row in rows]

    async def add(self, item: KnowledgeItem) -> KnowledgeItem:
        self.session.add(_knowledge_row(item))
        await self.session.flush()
        return item

    async def get_by_title(self, business_id: UUID, title: str) -> KnowledgeItem | None:
        stmt = select(KnowledgeItemRow).where(
            KnowledgeItemRow.business_id == business_id,
            KnowledgeItemRow.title == title,
        )
        row = await self.session.scalar(stmt)
        return _knowledge(row) if row else None


class BusinessRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, business_id: UUID) -> Business | None:
        row = await self.session.get(BusinessRow, business_id)
        return _business(row) if row else None

    async def get_by_name(self, name: str) -> Business | None:
        row = await self.session.scalar(select(BusinessRow).where(BusinessRow.name == name))
        return _business(row) if row else None

    async def list_all(self) -> list[Business]:
        rows = (await self.session.scalars(select(BusinessRow).order_by(BusinessRow.name.asc()))).all()
        return [_business(row) for row in rows]

    async def add(self, business: Business) -> Business:
        self.session.add(_business_row(business))
        await self.session.flush()
        return business


class SummaryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, customer_id: UUID) -> CustomerSummary | None:
        row = await self.session.get(CustomerSummaryRow, customer_id)
        return _summary(row) if row else None

    async def upsert(self, summary: CustomerSummary) -> CustomerSummary:
        row = await self.session.get(CustomerSummaryRow, summary.customer_id)
        if row is None:
            self.session.add(_summary_row(summary))
        else:
            row.summary = summary.summary
            row.need = summary.need
            row.language = summary.language
            row.status = summary.status
            row.important_facts = list(summary.important_facts)
            row.updated_at = summary.updated_at
        await self.session.flush()
        return summary


class HandoffRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, handoff: HandoffRequest) -> HandoffRequest:
        self.session.add(_handoff_row(handoff))
        await self.session.flush()
        return handoff

    async def get(self, handoff_id: UUID) -> HandoffRequest | None:
        row = await self.session.get(HandoffRequestRow, handoff_id)
        return _handoff(row) if row else None

    async def list_requests(self, status: str | None, limit: int) -> list[HandoffRequest]:
        stmt = select(HandoffRequestRow).order_by(HandoffRequestRow.created_at.desc()).limit(limit)
        if status:
            stmt = stmt.where(HandoffRequestRow.status == status)
        rows = (await self.session.scalars(stmt)).all()
        return [_handoff(row) for row in rows]

    async def save(self, handoff: HandoffRequest) -> HandoffRequest:
        row = await self.session.get(HandoffRequestRow, handoff.id)
        if row is None:
            raise HandoffNotFound(f"handoff {handoff.id} was not found")
        row.status = handoff.status
        row.updated_at = handoff.updated_at
        row.summary = handoff.summary
        row.priority = handoff.priority
        await self.session.flush()
        return _handoff(row)

    async def find_open(self, conversation_id: UUID, reason: str) -> HandoffRequest | None:
        stmt = select(HandoffRequestRow).where(
            HandoffRequestRow.conversation_id == conversation_id,
            HandoffRequestRow.reason == reason,
            HandoffRequestRow.status.in_(("PENDING", "ACCEPTED")),
        )
        row = await self.session.scalar(stmt)
        return _handoff(row) if row else None

    async def find_accepted(self, conversation_id: UUID) -> HandoffRequest | None:
        stmt = (
            select(HandoffRequestRow)
            .where(
                HandoffRequestRow.conversation_id == conversation_id,
                HandoffRequestRow.status == "ACCEPTED",
            )
            .limit(1)
        )
        row = await self.session.scalar(stmt)
        return _handoff(row) if row else None


class MeetingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, meeting: Meeting) -> Meeting:
        self.session.add(_meeting_row(meeting))
        await self.session.flush()
        return meeting

    async def get(self, meeting_id: UUID) -> Meeting | None:
        row = await self.session.get(MeetingRow, meeting_id)
        return _meeting(row) if row else None

    async def list_for_customer(self, customer_id: UUID) -> list[Meeting]:
        stmt = (
            select(MeetingRow)
            .where(MeetingRow.customer_id == customer_id)
            .order_by(MeetingRow.scheduled_at.asc())
        )
        rows = (await self.session.scalars(stmt)).all()
        return [_meeting(row) for row in rows]


class LogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add_interaction(self, entry: InteractionLog) -> InteractionLog:
        self.session.add(_interaction_row(entry))
        await self.session.flush()
        return entry

    async def add_usage(self, entry: UsageLog) -> UsageLog:
        self.session.add(_usage_row(entry))
        await self.session.flush()
        return entry


class VoiceCallRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_provider_id(self, provider: str, provider_call_id: str) -> VoiceCall | None:
        stmt = select(VoiceCallRow).where(
            VoiceCallRow.provider == provider,
            VoiceCallRow.provider_call_id == provider_call_id,
        )
        row = await self.session.scalar(stmt)
        return _voice_call(row) if row else None

    async def save(self, call: VoiceCall) -> VoiceCall:
        row = await self.session.get(VoiceCallRow, call.id)
        if row is None:
            row = VoiceCallRow(id=call.id, created_at=call.created_at)
            self.session.add(row)
        row.provider = call.provider
        row.provider_call_id = call.provider_call_id
        row.customer_id = call.customer_id
        row.caller = _clip(call.caller, 32)
        row.called = _clip(call.called, 32)
        row.status = call.status
        row.started_at = call.started_at
        row.ended_at = call.ended_at
        row.duration_s = call.duration_s
        row.cost = Decimal(str(call.cost))
        row.metadata_json = dict(call.metadata)
        row.updated_at = call.updated_at
        await self.session.flush()
        return call


class MetricsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def collect(self) -> MetricsSnapshot:
        conversations = await self._count(ConversationRow)
        messages = await self._count(MessageRow)
        handed_off = await self._count(HandoffRequestRow)
        meetings = await self._count(MeetingRow)
        handled = await self._handled_without_human()
        conv_with_handoff = await self._distinct(HandoffRequestRow.conversation_id)
        total_logs, by_language, by_route, avg_latency, avg_first, avg_cost = await self._log_stats()
        calls, call_seconds, call_cost = await self._voice_stats()
        minutes = call_seconds / 60
        return MetricsSnapshot(
            total_conversations=conversations,
            total_messages=messages,
            handled_without_human=handled,
            handed_off=handed_off,
            meetings_scheduled=meetings,
            average_first_response_time_ms=avg_first,
            average_response_time_ms=avg_latency,
            small_model_percentage=_percent(by_route.get("small", 0), total_logs),
            big_model_percentage=_percent(by_route.get("big", 0), total_logs),
            russian_percentage=_percent(by_language.get("ru", 0), total_logs),
            kyrgyz_percentage=_percent(by_language.get("ky", 0), total_logs),
            mixed_percentage=_percent(by_language.get("mixed", 0), total_logs),
            average_dialog_cost=avg_cost,
            handoff_rate=(conv_with_handoff / conversations) if conversations else 0.0,
            voice_calls=calls,
            voice_minutes=round(minutes, 2),
            voice_cost_per_minute=round(call_cost / minutes, 6) if minutes else 0.0,
        )

    async def _voice_stats(self) -> tuple[int, float, float]:
        """Completed calls only: an unfinished call has no duration or cost yet."""

        row = (
            await self.session.execute(
                select(
                    func.count(),
                    func.coalesce(func.sum(VoiceCallRow.duration_s), 0),
                    func.coalesce(func.sum(VoiceCallRow.cost), 0),
                ).where(VoiceCallRow.status == "completed")
            )
        ).one()
        return int(row[0]), float(row[1]), float(row[2])

    async def _count(self, model) -> int:
        value = await self.session.scalar(select(func.count()).select_from(model))
        return int(value or 0)

    async def _distinct(self, column) -> int:
        value = await self.session.scalar(select(func.count(func.distinct(column))))
        return int(value or 0)

    async def _handled_without_human(self) -> int:
        assistant = select(MessageRow.conversation_id).where(MessageRow.role == "assistant").distinct()
        handed = select(HandoffRequestRow.conversation_id).distinct()
        stmt = (
            select(func.count())
            .select_from(ConversationRow)
            .where(ConversationRow.id.in_(assistant), ConversationRow.id.notin_(handed))
        )
        value = await self.session.scalar(stmt)
        return int(value or 0)

    async def _log_stats(self) -> tuple[int, dict[str, int], dict[str, int], float, float, float]:
        total = int(await self.session.scalar(select(func.count()).select_from(InteractionLogRow)) or 0)
        languages = dict(
            (
                await self.session.execute(
                    select(InteractionLogRow.language, func.count()).group_by(InteractionLogRow.language)
                )
            ).all()
        )
        routes = dict(
            (
                await self.session.execute(
                    select(InteractionLogRow.route, func.count()).group_by(InteractionLogRow.route)
                )
            ).all()
        )
        avg_latency = float(await self.session.scalar(select(func.avg(InteractionLogRow.latency_ms))) or 0)
        first = (
            select(
                InteractionLogRow.conversation_id.label("conversation_id"),
                func.min(InteractionLogRow.created_at).label("first_at"),
            )
            .group_by(InteractionLogRow.conversation_id)
            .subquery()
        )
        avg_first = await self.session.scalar(
            select(func.avg(InteractionLogRow.latency_ms))
            .select_from(InteractionLogRow)
            .join(
                first,
                (InteractionLogRow.conversation_id == first.c.conversation_id)
                & (InteractionLogRow.created_at == first.c.first_at),
            )
        )
        per_dialog = (
            select(func.sum(InteractionLogRow.estimated_cost).label("cost"))
            .group_by(InteractionLogRow.conversation_id)
            .subquery()
        )
        avg_cost = await self.session.scalar(select(func.avg(per_dialog.c.cost)))
        return (
            total,
            {str(key): int(value) for key, value in languages.items()},
            {str(key): int(value) for key, value in routes.items()},
            avg_latency,
            float(avg_first or 0),
            float(avg_cost or 0),
        )


def _clip(value: str | None, size: int) -> str | None:
    """Fit a String(size) column. WhatsApp message ids and model names can exceed 64 chars."""

    return value if value is None or len(value) <= size else value[:size]


def _new_id() -> UUID:
    return uuid4()


def _percent(part: int, total: int) -> float:
    if not total:
        return 0.0
    return round(part * 100 / total, 2)


def _customer(row: CustomerRow) -> Customer:
    return Customer(
        id=row.id,
        phone=row.phone,
        language=row.language,
        status=row.status,
        need=row.need,
        preferred_contact_channel=row.preferred_contact_channel,
        merged_into_id=row.merged_into_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _customer_row(customer: Customer) -> CustomerRow:
    return CustomerRow(
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


def _business(row: BusinessRow) -> Business:
    return Business(
        id=row.id,
        name=row.name,
        description=row.description,
        working_hours=row.working_hours,
        contacts=dict(row.contacts or {}),
        rules=row.rules,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _business_row(business: Business) -> BusinessRow:
    return BusinessRow(
        id=business.id,
        name=business.name,
        description=business.description,
        working_hours=business.working_hours,
        contacts=dict(business.contacts),
        rules=business.rules,
        created_at=business.created_at,
        updated_at=business.updated_at,
    )


def _knowledge(row: KnowledgeItemRow) -> KnowledgeItem:
    return KnowledgeItem(
        id=row.id,
        business_id=row.business_id,
        category=row.category,
        title=row.title,
        content=row.content,
        metadata=dict(row.metadata_json or {}),
        active=row.active,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _knowledge_row(item: KnowledgeItem) -> KnowledgeItemRow:
    return KnowledgeItemRow(
        id=item.id,
        business_id=item.business_id,
        category=item.category,
        title=item.title,
        content=item.content,
        metadata_json=dict(item.metadata),
        active=item.active,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _conversation(row: ConversationRow) -> Conversation:
    return Conversation(
        id=row.id,
        customer_id=row.customer_id,
        channel=row.channel,
        started_at=row.started_at,
        ended_at=row.ended_at,
        summary=row.summary,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _conversation_row(conversation: Conversation) -> ConversationRow:
    return ConversationRow(
        id=conversation.id,
        customer_id=conversation.customer_id,
        channel=conversation.channel,
        started_at=conversation.started_at,
        ended_at=conversation.ended_at,
        summary=conversation.summary,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


def _message(row: MessageRow) -> Message:
    return Message(
        id=row.id,
        conversation_id=row.conversation_id,
        customer_id=row.customer_id,
        role=row.role,
        text=row.text,
        timestamp=row.timestamp,
        metadata=dict(row.metadata_json or {}),
        created_at=row.created_at,
    )


def _message_row(message: Message) -> MessageRow:
    return MessageRow(
        id=message.id,
        conversation_id=message.conversation_id,
        customer_id=message.customer_id,
        role=message.role,
        text=message.text,
        timestamp=message.timestamp,
        metadata_json=dict(message.metadata),
        created_at=message.created_at,
    )


def _summary(row: CustomerSummaryRow) -> CustomerSummary:
    return CustomerSummary(
        customer_id=row.customer_id,
        summary=row.summary,
        need=row.need,
        language=row.language,
        status=row.status,
        important_facts=list(row.important_facts or []),
        updated_at=row.updated_at,
    )


def _summary_row(summary: CustomerSummary) -> CustomerSummaryRow:
    return CustomerSummaryRow(
        customer_id=summary.customer_id,
        summary=summary.summary,
        need=summary.need,
        language=summary.language,
        status=summary.status,
        important_facts=list(summary.important_facts),
        created_at=summary.updated_at,
        updated_at=summary.updated_at,
    )


def _handoff(row: HandoffRequestRow) -> HandoffRequest:
    return HandoffRequest(
        id=row.id,
        customer_id=row.customer_id,
        conversation_id=row.conversation_id,
        reason=row.reason,
        priority=row.priority,
        summary=row.summary,
        recent_messages=list(row.recent_messages or []),
        status=row.status,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _handoff_row(handoff: HandoffRequest) -> HandoffRequestRow:
    return HandoffRequestRow(
        id=handoff.id,
        customer_id=handoff.customer_id,
        conversation_id=handoff.conversation_id,
        reason=handoff.reason,
        priority=handoff.priority,
        summary=handoff.summary,
        recent_messages=list(handoff.recent_messages),
        status=handoff.status,
        created_at=handoff.created_at,
        updated_at=handoff.updated_at,
    )


def _meeting(row: MeetingRow) -> Meeting:
    return Meeting(
        id=row.id,
        customer_id=row.customer_id,
        business_id=row.business_id,
        scheduled_at=row.scheduled_at,
        status=row.status,
        notes=row.notes,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _meeting_row(meeting: Meeting) -> MeetingRow:
    return MeetingRow(
        id=meeting.id,
        customer_id=meeting.customer_id,
        business_id=meeting.business_id,
        scheduled_at=meeting.scheduled_at,
        status=meeting.status,
        notes=meeting.notes,
        created_at=meeting.created_at,
        updated_at=meeting.updated_at,
    )


def _interaction_row(entry: InteractionLog) -> InteractionLogRow:
    return InteractionLogRow(
        id=entry.id,
        request_id=_clip(entry.request_id, 64),
        correlation_id=_clip(entry.correlation_id, 64),
        customer_id=entry.customer_id,
        conversation_id=entry.conversation_id,
        channel=entry.channel,
        language=entry.language,
        input_text=entry.input_text,
        route=entry.route,
        route_reason=_clip(entry.route_reason, 64),
        model=_clip(entry.model, 64),
        confidence=entry.confidence,
        knowledge_sources=list(entry.knowledge_sources),
        response_text=entry.response_text,
        handoff=entry.handoff,
        handoff_reason=_clip(entry.handoff_reason, 64),
        actions=list(entry.actions),
        latency_ms=entry.latency_ms,
        estimated_cost=Decimal(str(entry.estimated_cost)),
        created_at=entry.created_at,
    )


def _usage_row(entry: UsageLog) -> UsageLogRow:
    return UsageLogRow(
        id=entry.id,
        interaction_log_id=entry.interaction_log_id,
        request_id=_clip(entry.request_id, 64),
        model=_clip(entry.model, 64),
        input_tokens=entry.input_tokens,
        output_tokens=entry.output_tokens,
        estimated_cost=Decimal(str(entry.estimated_cost)),
        latency_ms=entry.latency_ms,
        created_at=entry.created_at,
    )


def _voice_call(row: VoiceCallRow) -> VoiceCall:
    return VoiceCall(
        id=row.id,
        provider=row.provider,
        provider_call_id=row.provider_call_id,
        customer_id=row.customer_id,
        caller=row.caller,
        called=row.called,
        status=row.status,
        started_at=row.started_at,
        ended_at=row.ended_at,
        duration_s=int(row.duration_s or 0),
        cost=float(row.cost or 0),
        metadata=dict(row.metadata_json or {}),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
