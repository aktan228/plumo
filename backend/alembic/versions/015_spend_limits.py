"""Daily spend and call limits for channel traffic (J-04).

spend_budgets: per scope (`business:<id>`, `service`) and UTC day — calls, reserved, spent.
spend_reservations: one hold per inbound event, so a redelivered event is not charged twice.

Revision ID: 015_spend_limits
Revises: 014_handoff_notify_status
Create Date: 2026-11-02
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "015_spend_limits"
down_revision = "014_handoff_notify_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "spend_budgets",
        sa.Column("scope", sa.String(64), primary_key=True),
        sa.Column("day", sa.String(10), primary_key=True),
        sa.Column("calls", sa.Integer(), server_default="0", nullable=False),
        sa.Column("reserved", sa.Numeric(14, 6), server_default="0", nullable=False),
        sa.Column("spent", sa.Numeric(14, 6), server_default="0", nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_table(
        "spend_reservations",
        sa.Column(
            "inbound_event_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("inbound_events.id", ondelete="CASCADE"), primary_key=True,
        ),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("day", sa.String(10), nullable=False),
        sa.Column("amount", sa.Numeric(14, 6), nullable=False),
        sa.Column("actual", sa.Numeric(14, 6), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("cost_version", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_spend_reservations_business_id", "spend_reservations", ["business_id"])


def downgrade() -> None:
    op.drop_table("spend_reservations")
    op.drop_table("spend_budgets")
