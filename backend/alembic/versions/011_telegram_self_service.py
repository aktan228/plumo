"""Encrypted self-service Telegram credentials."""

from alembic import op
import sqlalchemy as sa

revision = "011_telegram_self_service"
down_revision = "010_test_chat"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("channel_connections", sa.Column("encrypted_token", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("channel_connections", "encrypted_token")
