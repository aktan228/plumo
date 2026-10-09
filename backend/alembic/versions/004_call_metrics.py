"""Per-business call metrics and per-step timings in the interaction log.

voice_calls and interaction_logs get business_id, filled from the customer.
interaction_logs also keeps step timings and speech-recognition confidence.

Revision ID: 004_call_metrics
Revises: 003_business_isolation
Create Date: 2026-10-09
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "004_call_metrics"
down_revision = "003_business_isolation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("voice_calls", sa.Column("business_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.execute(
        "UPDATE voice_calls vc SET business_id = c.business_id FROM customers c WHERE c.id = vc.customer_id"
    )
    op.create_foreign_key("voice_calls_business_id_fkey", "voice_calls", "businesses", ["business_id"], ["id"])
    op.create_index("ix_voice_calls_business_id", "voice_calls", ["business_id"])

    op.add_column("interaction_logs", sa.Column("business_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.execute(
        "UPDATE interaction_logs il SET business_id = c.business_id FROM customers c WHERE c.id = il.customer_id"
    )
    op.create_foreign_key(
        "interaction_logs_business_id_fkey", "interaction_logs", "businesses", ["business_id"], ["id"]
    )
    op.create_index("ix_interaction_logs_business_id", "interaction_logs", ["business_id"])
    op.add_column(
        "interaction_logs",
        sa.Column("timings", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.add_column("interaction_logs", sa.Column("stt_confidence", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("interaction_logs", "stt_confidence")
    op.drop_column("interaction_logs", "timings")
    op.drop_index("ix_interaction_logs_business_id", table_name="interaction_logs")
    op.drop_constraint("interaction_logs_business_id_fkey", "interaction_logs", type_="foreignkey")
    op.drop_column("interaction_logs", "business_id")
    op.drop_index("ix_voice_calls_business_id", table_name="voice_calls")
    op.drop_constraint("voice_calls_business_id_fkey", "voice_calls", type_="foreignkey")
    op.drop_column("voice_calls", "business_id")
