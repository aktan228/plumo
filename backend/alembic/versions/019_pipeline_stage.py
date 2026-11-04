"""Manual pipeline stages, independent from conversation ownership and delivery."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "019_pipeline_stage"
down_revision = "018_dashboard_manager_compat"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("conversations", sa.Column("pipeline_stage", sa.String(32), nullable=False, server_default="unassigned"))
    op.add_column("conversations", sa.Column("stage_version", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("conversations", sa.Column("stage_updated_at", sa.DateTime(timezone=True)))
    op.add_column("conversations", sa.Column("stage_updated_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("operators.id")))
    op.create_check_constraint("ck_conversation_stage", "conversations", "pipeline_stage IN ('unassigned','new','discovery','qualified','meeting_requested','meeting_confirmed')")
    op.create_check_constraint("ck_conversation_stage_version", "conversations", "stage_version >= 0")
    op.create_index("ix_conversations_business_stage", "conversations", ["business_id", "pipeline_stage"])


def downgrade():
    op.drop_index("ix_conversations_business_stage", table_name="conversations")
    op.drop_constraint("ck_conversation_stage_version", "conversations", type_="check")
    op.drop_constraint("ck_conversation_stage", "conversations", type_="check")
    for column in ["stage_updated_by", "stage_updated_at", "stage_version", "pipeline_stage"]:
        op.drop_column("conversations", column)
