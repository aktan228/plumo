"""Voice calls handled by the voice platform.

Revision ID: 002_voice_calls
Revises: 001_initial
Create Date: 2026-10-08
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "002_voice_calls"
down_revision = "001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "voice_calls",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("provider_call_id", sa.String(128), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("customers.id"), nullable=True),
        sa.Column("caller", sa.String(32), nullable=True),
        sa.Column("called", sa.String(32), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_s", sa.Integer(), nullable=False),
        sa.Column("cost", sa.Numeric(12, 6), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("provider", "provider_call_id", name="uq_voice_call_provider_id"),
    )
    op.create_index("ix_voice_calls_customer_id", "voice_calls", ["customer_id"])
    op.create_index("ix_voice_calls_status", "voice_calls", ["status"])


def downgrade() -> None:
    op.drop_index("ix_voice_calls_status", table_name="voice_calls")
    op.drop_index("ix_voice_calls_customer_id", table_name="voice_calls")
    op.drop_table("voice_calls")
