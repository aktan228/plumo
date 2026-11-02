"""Pilot requests from the website (J-07): stored first, the team is told by the worker.

Revision ID: 017_leads
Revises: 016_worker_heartbeats
Create Date: 2026-11-02
"""

from alembic import op
import sqlalchemy as sa

revision = "017_leads"
down_revision = "016_worker_heartbeats"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "leads",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("idempotency_key", sa.String(64), nullable=False, unique=True),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("company", sa.String(200), nullable=False, server_default=""),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("message", sa.Text(), nullable=False, server_default=""),
        sa.Column("plan", sa.String(200), nullable=False, server_default=""),
        sa.Column("locale", sa.String(8), nullable=False, server_default="ru"),
        sa.Column("notify_status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("notify_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("notify_error", sa.String(64), nullable=True),
        sa.Column("notify_after", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_leads_notify_queue", "leads", ["notify_after"], postgresql_where=sa.text("notify_status = 'queued'"))


def downgrade() -> None:
    op.drop_table("leads")
