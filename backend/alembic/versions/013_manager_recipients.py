"""Manager notification recipient per business.

Handoff notifications used to go to one chat from TELEGRAM_MANAGER_CHAT_ID for every
business. Now each business binds its own private chat with the service bot: a one-time
code (only its hash is stored), the chat that sent it waits as a candidate, an operator
of the business confirms it.

Revision ID: 013_manager_recipients
Revises: 012_handoff_notify_job
Create Date: 2026-10-29
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "013_manager_recipients"
down_revision = "012_handoff_notify_job"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "manager_recipients",
        sa.Column(
            "business_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("businesses.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("code_hash", sa.String(64), nullable=True, unique=True),
        sa.Column("code_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("candidate_chat_id", sa.String(32), nullable=True),
        sa.Column("candidate_label", sa.String(200), nullable=True),
        sa.Column("candidate_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("chat_id", sa.String(32), nullable=True),
        sa.Column("chat_label", sa.String(200), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "confirmed_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("operators.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("attention", sa.String(64), nullable=True),
        sa.Column("attention_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("manager_recipients")
