"""Manager notification as a queued job.

The notification used to be sent by a task started before the transaction committed:
a rollback left the manager with a handoff that does not exist, a retried job sent it
twice, a stopped process lost it. Now the handoff and its job are one transaction and
the worker sends it.

- jobs.handoff_id: which handoff a notify_handoff job is about;
- one notify_handoff job per handoff (partial unique index);
- handoff_requests.notified_at: set after Telegram accepted it, so a redelivered job sends nothing.

Handoffs created before this revision were notified by the old path: they are marked as notified.

Revision ID: 007_handoff_notify_job
Revises: 006_channels_dashboard
Create Date: 2026-10-25
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "007_handoff_notify_job"
down_revision = "006_channels_dashboard"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("handoff_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_jobs_handoff_id", "jobs", "handoff_requests", ["handoff_id"], ["id"])
    op.create_index(
        "uq_jobs_notify_handoff",
        "jobs",
        ["handoff_id"],
        unique=True,
        postgresql_where=sa.text("kind = 'notify_handoff'"),
    )
    op.add_column("handoff_requests", sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE handoff_requests SET notified_at = created_at WHERE notified_at IS NULL")


def downgrade() -> None:
    op.drop_column("handoff_requests", "notified_at")
    op.drop_index("uq_jobs_notify_handoff", "jobs")
    op.drop_constraint("fk_jobs_handoff_id", "jobs", type_="foreignkey")
    op.drop_column("jobs", "handoff_id")
