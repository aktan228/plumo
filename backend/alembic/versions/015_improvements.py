"""Evidence-backed answer improvements; no automatic knowledge writes."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "015_improvements"
down_revision = "014_pipeline_stage"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("improvements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category", sa.String(32), nullable=False), sa.Column("note", sa.Text(), nullable=False),
        sa.Column("source_key", sa.String(100), nullable=False), sa.Column("snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="new"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fixed_publication_version", sa.Integer()), sa.Column("fixed_at", sa.DateTime(timezone=True)),
        sa.Column("correction_note", sa.Text()), sa.Column("verification", postgresql.JSONB()),
        sa.Column("history", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("operators.id"), nullable=False),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("operators.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status IN ('new','in_progress','fixed','verified')", name="ck_improvement_status"),
        sa.CheckConstraint("category IN ('incorrect_fact','missing_answer','handoff','language_tone')", name="ck_improvement_category"),
        sa.CheckConstraint("version >= 0", name="ck_improvement_version"))
    op.create_index("ix_improvements_business_created", "improvements", ["business_id", "created_at", "id"])


def downgrade():
    op.drop_table("improvements")
