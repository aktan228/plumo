"""Versioned resumable onboarding snapshots.

Revision ID: 009_onboarding_persistence
Revises: 008_account_email
"""

from alembic import op
import sqlalchemy as sa

revision = "009_onboarding_persistence"
down_revision = "008_account_email"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("onboarding_drafts", sa.Column("version", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("onboarding_drafts", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column("onboarding_drafts", "completed_at")
    op.drop_column("onboarding_drafts", "version")
