"""Initial Plumo schema.

Revision ID: 001_initial
Revises:
Create Date: 2026-10-04
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "businesses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("working_hours", sa.String(200), nullable=False),
        sa.Column("contacts", postgresql.JSONB(), nullable=False),
        sa.Column("rules", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "knowledge_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("businesses.id"), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("business_id", "title", name="uq_knowledge_business_title"),
    )
    op.create_index("ix_knowledge_items_business_active", "knowledge_items", ["business_id", "active"])
    op.create_table(
        "customers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("phone", sa.String(32), nullable=True, unique=True),
        sa.Column("language", sa.String(16), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("need", sa.String(255), nullable=True),
        sa.Column("preferred_contact_channel", sa.String(32), nullable=True),
        sa.Column("merged_into_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("customers.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "customer_channels",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("external_id", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("channel", "external_id", name="uq_channel_external"),
    )
    op.create_index("ix_customer_channels_customer", "customer_channels", ["customer_id"])
    op.create_table(
        "conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_conversations_customer", "conversations", ["customer_id"])
    op.create_table(
        "messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("conversations.id"), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_messages_conversation", "messages", ["conversation_id"])
    op.create_index("ix_messages_customer", "messages", ["customer_id"])
    op.create_table(
        "customer_summaries",
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("customers.id"), primary_key=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("need", sa.String(255), nullable=True),
        sa.Column("language", sa.String(16), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("important_facts", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "handoff_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("conversations.id"), nullable=False),
        sa.Column("reason", sa.String(64), nullable=False),
        sa.Column("priority", sa.String(16), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("recent_messages", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_handoff_requests_status", "handoff_requests", ["status"])
    op.create_table(
        "meetings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("businesses.id"), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "interaction_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("correlation_id", sa.String(64), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("conversations.id"), nullable=False),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("language", sa.String(16), nullable=False),
        sa.Column("input_text", sa.Text(), nullable=False),
        sa.Column("route", sa.String(16), nullable=False),
        sa.Column("route_reason", sa.String(64), nullable=False),
        sa.Column("model", sa.String(64), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("knowledge_sources", postgresql.JSONB(), nullable=False),
        sa.Column("response_text", sa.Text(), nullable=False),
        sa.Column("handoff", sa.Boolean(), nullable=False),
        sa.Column("handoff_reason", sa.String(64), nullable=True),
        sa.Column("actions", postgresql.JSONB(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("estimated_cost", sa.Numeric(12, 6), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_interaction_logs_customer", "interaction_logs", ["customer_id"])
    op.create_index("ix_interaction_logs_correlation", "interaction_logs", ["correlation_id"])
    op.create_table(
        "ai_usage_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "interaction_log_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("interaction_logs.id"),
            nullable=True,
        ),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("model", sa.String(64), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("estimated_cost", sa.Numeric(12, 6), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ai_usage_logs_request", "ai_usage_logs", ["request_id"])


def downgrade() -> None:
    op.drop_table("ai_usage_logs")
    op.drop_table("interaction_logs")
    op.drop_table("meetings")
    op.drop_table("handoff_requests")
    op.drop_table("customer_summaries")
    op.drop_table("messages")
    op.drop_table("conversations")
    op.drop_table("customer_channels")
    op.drop_table("customers")
    op.drop_table("knowledge_items")
    op.drop_table("businesses")
