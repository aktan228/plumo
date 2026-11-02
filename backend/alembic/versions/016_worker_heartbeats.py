"""Worker heartbeats for monitoring (J-05).

Revision ID: 016_worker_heartbeats
Revises: 015_spend_limits
Create Date: 2026-11-02
"""

from alembic import op
import sqlalchemy as sa

revision = "016_worker_heartbeats"
down_revision = "015_spend_limits"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "worker_heartbeats",
        sa.Column("worker_id", sa.String(64), primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_worker_heartbeats_seen_at", "worker_heartbeats", ["seen_at"])


def downgrade() -> None:
    op.drop_table("worker_heartbeats")
