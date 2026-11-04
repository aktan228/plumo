"""Immutable scenario snapshots at the existing shared publication boundary."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "021_scenario_revisions"
down_revision = "020_improvements"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("scenario_revisions",
        sa.Column("business_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("publication_version", sa.Integer(), primary_key=True),
        sa.Column("settings", postgresql.JSONB(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False))


def downgrade():
    op.drop_table("scenario_revisions")
