"""State of the manager notification on the handoff itself.

Until now only `notified_at` existed: the dashboard could not tell "being sent" from
"failed" or "may have been sent, nobody knows". The notification now has the same
states as a delivery (queued/sending/sent/failed/unknown/cancelled), its last error and
the time of the last attempt. `sending` is written before the call to Telegram, so a
worker that died mid-send leaves `unknown` for a person to decide, not a blind resend.

Existing handoffs: notified -> sent; with a pending job -> queued; with a failed job ->
failed and the job's error; without a job (old rows) -> stays NULL.

Revision ID: 014_handoff_notify_status
Revises: 013_manager_recipients
Create Date: 2026-10-29
"""

from alembic import op
import sqlalchemy as sa

revision = "014_handoff_notify_status"
down_revision = "013_manager_recipients"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("handoff_requests", sa.Column("notify_status", sa.String(16), nullable=True))
    op.add_column("handoff_requests", sa.Column("notify_error", sa.String(64), nullable=True))
    op.add_column("handoff_requests", sa.Column("notify_attempted_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE handoff_requests SET notify_status = 'sent' WHERE notified_at IS NOT NULL")
    op.execute(
        """
        UPDATE handoff_requests h SET notify_status = CASE WHEN j.status = 'failed' THEN 'failed' ELSE 'queued' END,
               notify_error = CASE WHEN j.status = 'failed' THEN left(j.last_error, 64) END
        FROM jobs j
        WHERE j.handoff_id = h.id AND j.kind = 'notify_handoff' AND h.notified_at IS NULL
        """
    )


def downgrade() -> None:
    op.drop_column("handoff_requests", "notify_attempted_at")
    op.drop_column("handoff_requests", "notify_error")
    op.drop_column("handoff_requests", "notify_status")
