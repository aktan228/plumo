"""Email verification and single-use password recovery tokens.

Revision ID: 008_account_email
Revises: 007_self_service_registration
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "008_account_email"
down_revision = "007_self_service_registration"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("operators", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))
    # Existing pilot/admin accounts keep access. New public accounts start unverified.
    op.execute("UPDATE operators SET email_verified_at = now()")
    op.create_table(
        "auth_email_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "operator_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("operators.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("purpose", sa.String(16), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("purpose IN ('verify', 'reset')", name="ck_auth_email_purpose"),
    )
    op.create_index("ix_auth_email_operator_created", "auth_email_tokens", ["operator_id", "created_at"])


def downgrade():
    op.drop_table("auth_email_tokens")
    op.drop_column("operators", "email_verified_at")
