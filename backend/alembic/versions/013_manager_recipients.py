"""Tenant-specific confirmed manager recipients and durable delivery attempts."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "013_manager_recipients"
down_revision = "012_handoff_notify_job"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "manager_recipients",
        sa.Column("business_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("chat_id", sa.String(32)), sa.Column("display_name", sa.String(200)),
        sa.Column("pending_hash", sa.String(64), unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("candidate_chat_id", sa.String(32)), sa.Column("candidate_name", sa.String(200)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_table(
        "manager_notifications",
        sa.Column("handoff_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("handoff_requests.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("recipient_version", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_manager_notifications_business_id", "manager_notifications", ["business_id"])


def downgrade():
    op.drop_table("manager_notifications")
    op.drop_table("manager_recipients")
