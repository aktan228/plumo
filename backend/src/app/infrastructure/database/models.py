"""SQLAlchemy models. JSONB is only used for metadata, contacts and action payloads."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.models import utcnow
from app.infrastructure.database.base import Base


class BusinessRow(Base):
    __tablename__ = "businesses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    working_hours: Mapped[str] = mapped_column(String(200), default="")
    contacts: Mapped[dict] = mapped_column(JSONB, default=dict)
    rules: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class KnowledgeItemRow(Base):
    __tablename__ = "knowledge_items"
    __table_args__ = (UniqueConstraint("business_id", "title", name="uq_knowledge_business_title"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("businesses.id"))
    category: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(300))
    content: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CustomerRow(Base):
    __tablename__ = "customers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    phone: Mapped[str | None] = mapped_column(String(32), unique=True, nullable=True)
    language: Mapped[str] = mapped_column(String(16), default="unknown")
    status: Mapped[str] = mapped_column(String(32), default="new")
    need: Mapped[str | None] = mapped_column(String(255), nullable=True)
    preferred_contact_channel: Mapped[str | None] = mapped_column(String(32), nullable=True)
    merged_into_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CustomerChannelRow(Base):
    __tablename__ = "customer_channels"
    __table_args__ = (UniqueConstraint("channel", "external_id", name="uq_channel_external"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customers.id"))
    channel: Mapped[str] = mapped_column(String(32))
    external_id: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ConversationRow(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customers.id"), index=True)
    channel: Mapped[str] = mapped_column(String(32))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MessageRow(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id"), index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customers.id"), index=True)
    role: Mapped[str] = mapped_column(String(16))
    text: Mapped[str] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CustomerSummaryRow(Base):
    __tablename__ = "customer_summaries"

    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customers.id"), primary_key=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    need: Mapped[str | None] = mapped_column(String(255), nullable=True)
    language: Mapped[str] = mapped_column(String(16), default="unknown")
    status: Mapped[str] = mapped_column(String(32), default="new")
    important_facts: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class HandoffRequestRow(Base):
    __tablename__ = "handoff_requests"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customers.id"), index=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id"), index=True)
    reason: Mapped[str] = mapped_column(String(64))
    priority: Mapped[str] = mapped_column(String(16))
    summary: Mapped[str] = mapped_column(Text, default="")
    recent_messages: Mapped[list] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String(16), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MeetingRow(Base):
    __tablename__ = "meetings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customers.id"), index=True)
    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("businesses.id"))
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class InteractionLogRow(Base):
    __tablename__ = "interaction_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    request_id: Mapped[str] = mapped_column(String(64), index=True)
    correlation_id: Mapped[str] = mapped_column(String(64), index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customers.id"), index=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id"), index=True)
    channel: Mapped[str] = mapped_column(String(32))
    language: Mapped[str] = mapped_column(String(16))
    input_text: Mapped[str] = mapped_column(Text)
    route: Mapped[str] = mapped_column(String(16))
    route_reason: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(64))
    confidence: Mapped[float] = mapped_column()
    knowledge_sources: Mapped[list] = mapped_column(JSONB, default=list)
    response_text: Mapped[str] = mapped_column(Text)
    handoff: Mapped[bool] = mapped_column(Boolean, default=False)
    handoff_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    actions: Mapped[list] = mapped_column(JSONB, default=list)
    latency_ms: Mapped[int] = mapped_column()
    estimated_cost: Mapped[Decimal] = mapped_column(Numeric(12, 6))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class UsageLogRow(Base):
    __tablename__ = "ai_usage_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    interaction_log_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("interaction_logs.id"), nullable=True
    )
    request_id: Mapped[str] = mapped_column(String(64), index=True)
    model: Mapped[str] = mapped_column(String(64))
    input_tokens: Mapped[int] = mapped_column()
    output_tokens: Mapped[int] = mapped_column()
    estimated_cost: Mapped[Decimal] = mapped_column(Numeric(12, 6))
    latency_ms: Mapped[int] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class VoiceCallRow(Base):
    __tablename__ = "voice_calls"
    __table_args__ = (UniqueConstraint("provider", "provider_call_id", name="uq_voice_call_provider_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    provider: Mapped[str] = mapped_column(String(32))
    provider_call_id: Mapped[str] = mapped_column(String(128))
    customer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("customers.id"), nullable=True, index=True)
    caller: Mapped[str | None] = mapped_column(String(32), nullable=True)
    called: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(16), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_s: Mapped[int] = mapped_column(default=0)
    cost: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=0)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
