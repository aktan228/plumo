"""Dashboard recipient versions and durable legacy notification ledger."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "018_dashboard_manager_compat"
down_revision = "017_leads"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("handoff_requests", sa.Column("notify_generation", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("manager_recipients", sa.Column("version", sa.Integer(), nullable=False, server_default="0"))
    op.create_table("manager_notifications",
        sa.Column("handoff_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("handoff_requests.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("recipient_version", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")))
    op.create_index("ix_manager_notifications_business_id", "manager_notifications", ["business_id"])


def downgrade():
    op.drop_table("manager_notifications")
    op.drop_column("manager_recipients", "version")
    op.drop_column("handoff_requests", "notify_generation")
