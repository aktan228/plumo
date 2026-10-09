"""Sales profile per business: what it sells, the next step, qualifying questions.

The agent is not tied to one industry. Prompt wording that used to be about
apartments comes from businesses.profile now.

Revision ID: 005_business_profile
Revises: 004_call_metrics
Create Date: 2026-10-09
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "005_business_profile"
down_revision = "004_call_metrics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "businesses",
        sa.Column("profile", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )


def downgrade() -> None:
    op.drop_column("businesses", "profile")
