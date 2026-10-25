"""SQLAlchemy models. JSONB is only used for metadata, contacts and action payloads."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.models import utcnow
from app.infrastructure.database.base import Base


class BusinessRow(Base):
    __tablename__ = "businesses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    working_hours: Mapped[str] = mapped_column(String(200), default="")
    contacts: Mapped[dict] = mapped_column(JSONB, default=dict)
    rules: Mapped[str] = mapped_column(Text, default="")
    profile: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OnboardingDraftRow(Base):
    __tablename__ = "onboarding_drafts"
    __table_args__ = (CheckConstraint("step >= 0 AND step <= 5", name="ck_onboarding_step"),)

    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), primary_key=True)
    step: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    data: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=text("now()"))


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
    # One person calling two agencies is two customers: history never crosses businesses.
    __table_args__ = (UniqueConstraint("business_id", "phone", name="uq_customers_business_phone"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("businesses.id"), index=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # A number the customer typed. A callback target, not proof of identity.
    contact_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
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
    __table_args__ = (
        UniqueConstraint("business_id", "channel", "external_id", name="uq_channel_business_external"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("businesses.id"))
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
    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("businesses.id"), index=True)
    connection_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("channel_connections.id"), nullable=True, index=True
    )
    mode: Mapped[str] = mapped_column(String(16), default="ai", server_default="ai")
    mode_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    mode_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    external_chat_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    contact_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    contact_handle: Mapped[str | None] = mapped_column(String(100), nullable=True)


class MessageRow(Base):
    __tablename__ = "messages"
    # A webhook retried concurrently must not run the agent twice.
    __table_args__ = (
        UniqueConstraint("conversation_id", "external_id", name="uq_messages_conversation_external"),
        Index("ix_messages_conversation_timestamp", "conversation_id", "timestamp", "seq"),
    )
    __mapper_args__ = {"eager_defaults": True}

    seq: Mapped[int] = mapped_column(BigInteger, Identity(always=False), unique=True)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id"), index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customers.id"), index=True)
    role: Mapped[str] = mapped_column(String(16))
    text: Mapped[str] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    external_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
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
    timings: Mapped[dict] = mapped_column(JSONB, default=dict)
    stt_confidence: Mapped[float | None] = mapped_column(nullable=True)
    business_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("businesses.id"), nullable=True, index=True)
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
    business_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("businesses.id"), nullable=True, index=True)
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


class OperatorRow(Base):
    __tablename__ = "operators"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("businesses.id"), index=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    display_name: Mapped[str] = mapped_column(String(100), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuthEmailTokenRow(Base):
    __tablename__ = "auth_email_tokens"
    __table_args__ = (
        CheckConstraint("purpose IN ('verify', 'reset')", name="ck_auth_email_purpose"),
        Index("ix_auth_email_operator_created", "operator_id", "created_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    operator_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("operators.id", ondelete="CASCADE"))
    purpose: Mapped[str] = mapped_column(String(16))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OperatorSessionRow(Base):
    __tablename__ = "operator_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    operator_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("operators.id"), index=True)
    # sha256 of the cookie value: a database dump does not hand out live sessions.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ChannelConnectionRow(Base):
    __tablename__ = "channel_connections"
    __table_args__ = (
        UniqueConstraint("business_id", "channel", "external_account_id", name="uq_connection_business_account"),
        # One live connection of a channel per business, and one business per bot/account.
        Index(
            "uq_connection_active_business_channel",
            "business_id",
            "channel",
            unique=True,
            postgresql_where=text("status <> 'disconnected'"),
        ),
        Index(
            "uq_connection_active_account",
            "channel",
            "external_account_id",
            unique=True,
            postgresql_where=text("status <> 'disconnected'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("businesses.id"), index=True)
    channel: Mapped[str] = mapped_column(String(16))
    credential_ref: Mapped[str] = mapped_column(String(64))
    encrypted_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    auth_method: Mapped[str] = mapped_column(String(32), default="server_credential")
    external_account_id: Mapped[str] = mapped_column(String(64))
    display_name: Mapped[str] = mapped_column(String(200), default="")
    username: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(24))
    agent_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    # Telegram webhook secret is HMAC(CHANNEL_SECRET_KEY, id + nonce); the secret itself is not stored.
    webhook_nonce: Mapped[str | None] = mapped_column(String(64), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    last_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_check_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(String(300), nullable=True)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    disconnected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class InboundEventRow(Base):
    __tablename__ = "inbound_events"
    __table_args__ = (
        UniqueConstraint("connection_id", "external_event_id", name="uq_inbound_connection_event"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("businesses.id"), index=True)
    connection_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("channel_connections.id"))
    channel: Mapped[str] = mapped_column(String(16))
    external_event_id: Mapped[str] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(String(24))
    sender_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    data: Mapped[dict] = mapped_column(JSONB, default=dict)
    provider_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    status: Mapped[str] = mapped_column(String(16), index=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)


class OutboundMessageRow(Base):
    __tablename__ = "outbound_messages"
    __table_args__ = (
        UniqueConstraint("business_id", "idempotency_key", name="uq_outbound_business_idempotency"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("businesses.id"), index=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id"), index=True)
    connection_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("channel_connections.id"), nullable=True)
    message_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("messages.id"), nullable=True, unique=True)
    author_role: Mapped[str] = mapped_column(String(16))
    operator_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("operators.id"), nullable=True)
    text: Mapped[str] = mapped_column(Text)
    idempotency_key: Mapped[str] = mapped_column(String(128))
    mode_version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    parts_sent: Mapped[int] = mapped_column(Integer, default=0)
    provider_message_ids: Mapped[list] = mapped_column(JSONB, default=list)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class JobRow(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_status_run_at", "status", "run_at"),
        Index("ix_jobs_ordering_key_id", "ordering_key", "id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32))
    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("businesses.id"))
    # Jobs with one key run one at a time, in id order: one dialog's messages stay in sequence.
    ordering_key: Mapped[str] = mapped_column(String(200))
    inbound_event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("inbound_events.id"), nullable=True)
    outbound_message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("outbound_messages.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(16))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5)
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ConversationReadRow(Base):
    """How far an operator has read a dialog. Only moves forward."""

    __tablename__ = "conversation_reads"

    operator_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("operators.id"), primary_key=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id"), primary_key=True)
    last_read_seq: Mapped[int] = mapped_column(BigInteger, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TestBudgetRow(Base):
    __tablename__ = "test_chat_budgets"
    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), primary_key=True)
    day: Mapped[str] = mapped_column(String(10))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    sessions: Mapped[int] = mapped_column(Integer, default=0)
    charged: Mapped[Decimal] = mapped_column(Numeric(14, 6), default=0)


class TestSessionRow(Base):
    __tablename__ = "test_chat_sessions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    publication_version: Mapped[int] = mapped_column(Integer)
    state: Mapped[dict] = mapped_column(JSONB)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    paused: Mapped[bool] = mapped_column(Boolean, default=False)
    pending_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TestTurnRow(Base):
    __tablename__ = "test_chat_turns"
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("test_chat_sessions.id", ondelete="CASCADE"), primary_key=True)
    request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16))
    error: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result: Mapped[dict] = mapped_column(JSONB, default=dict)
    day: Mapped[str] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
