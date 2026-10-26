"""Self-service setup drafts; workspace names are display names, not tenant identifiers.

Revision ID: 007_self_service_registration
Revises: 006_channels_dashboard
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "007_self_service_registration"
down_revision = "006_channels_dashboard"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("businesses_name_key", "businesses", type_="unique")
    op.create_table(
        "onboarding_drafts",
        sa.Column(
            "business_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("businesses.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("step", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("data", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("step >= 0 AND step <= 5", name="ck_onboarding_step"),
    )


def downgrade() -> None:
    duplicate = (
        op.get_bind().execute(sa.text("SELECT 1 FROM businesses GROUP BY name HAVING count(*) > 1 LIMIT 1")).first()
    )
    if duplicate:
        raise RuntimeError("Rename duplicate workspace names before downgrading to 006_channels_dashboard.")
    op.drop_table("onboarding_drafts")
    op.create_unique_constraint("businesses_name_key", "businesses", ["name"])
