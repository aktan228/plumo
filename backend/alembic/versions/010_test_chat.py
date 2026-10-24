"""Isolated test chat sessions, idempotent turns and shared daily allowances."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "010_test_chat"
down_revision = "009_onboarding_persistence"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "test_chat_budgets",
        sa.Column(
            "business_id", pg.UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("day", sa.String(10), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("sessions", sa.Integer(), nullable=False),
        sa.Column("charged", sa.Numeric(14, 6), nullable=False),
    )
    op.create_table(
        "test_chat_sessions",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "business_id", pg.UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("publication_version", sa.Integer(), nullable=False),
        sa.Column("state", pg.JSONB(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("paused", sa.Boolean(), nullable=False),
        sa.Column("pending_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_test_chat_sessions_business_id", "test_chat_sessions", ["business_id"])
    op.create_table(
        "test_chat_turns",
        sa.Column(
            "session_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("test_chat_sessions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("request_id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error", sa.String(64), nullable=True),
        sa.Column("result", pg.JSONB(), nullable=False),
        sa.Column("day", sa.String(10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("test_chat_turns")
    op.drop_index("ix_test_chat_sessions_business_id", table_name="test_chat_sessions")
    op.drop_table("test_chat_sessions")
    op.drop_table("test_chat_budgets")
