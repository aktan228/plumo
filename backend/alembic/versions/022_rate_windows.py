"""Short-window rate limits for paid customer turns (PJ-01).

rate_windows: turns started per scope (`business:<id>`, `service`) in one fixed window.
Shared by every API and worker process and kept across restarts.

Revision ID: 022_rate_windows
Revises: 021_scenario_revisions
Create Date: 2026-11-04
"""

from alembic import op
import sqlalchemy as sa

revision = "022_rate_windows"
down_revision = "021_scenario_revisions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rate_windows",
        sa.Column("scope", sa.String(64), primary_key=True),
        sa.Column("window_start", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("count", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_table("rate_windows")
