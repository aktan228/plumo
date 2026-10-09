"""Customers belong to one business; typed phones do not merge cards; message dedup in the DB.

Existing customers are attached to the oldest business: before this revision
every deployment served one business.

Revision ID: 003_business_isolation
Revises: 002_voice_calls
Create Date: 2026-10-08
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "003_business_isolation"
down_revision = "002_voice_calls"
branch_labels = None
depends_on = None

_FIRST_BUSINESS = "(SELECT id FROM businesses ORDER BY created_at ASC, id ASC LIMIT 1)"


def upgrade() -> None:
    op.add_column("customers", sa.Column("business_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("customers", sa.Column("contact_phone", sa.String(32), nullable=True))
    op.execute(f"UPDATE customers SET business_id = {_FIRST_BUSINESS}")
    op.alter_column("customers", "business_id", nullable=False)
    op.create_foreign_key("customers_business_id_fkey", "customers", "businesses", ["business_id"], ["id"])
    op.create_index("ix_customers_business_id", "customers", ["business_id"])
    op.drop_constraint("customers_phone_key", "customers", type_="unique")
    op.create_unique_constraint("uq_customers_business_phone", "customers", ["business_id", "phone"])

    op.add_column("customer_channels", sa.Column("business_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.execute(
        "UPDATE customer_channels cc SET business_id = c.business_id FROM customers c WHERE c.id = cc.customer_id"
    )
    op.alter_column("customer_channels", "business_id", nullable=False)
    op.create_foreign_key(
        "customer_channels_business_id_fkey", "customer_channels", "businesses", ["business_id"], ["id"]
    )
    op.drop_constraint("uq_channel_external", "customer_channels", type_="unique")
    op.create_unique_constraint(
        "uq_channel_business_external", "customer_channels", ["business_id", "channel", "external_id"]
    )

    op.add_column("messages", sa.Column("external_id", sa.String(128), nullable=True))
    # The old check lived in JSON metadata; keep the first copy of any duplicate.
    op.execute(
        """
        UPDATE messages SET external_id = first.ext
        FROM (
            SELECT DISTINCT ON (conversation_id, metadata->>'external_message_id')
                   id, metadata->>'external_message_id' AS ext
            FROM messages
            WHERE role = 'user' AND metadata ? 'external_message_id'
            ORDER BY conversation_id, metadata->>'external_message_id', created_at ASC
        ) AS first
        WHERE messages.id = first.id
        """
    )
    op.create_unique_constraint(
        "uq_messages_conversation_external", "messages", ["conversation_id", "external_id"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_messages_conversation_external", "messages", type_="unique")
    op.drop_column("messages", "external_id")

    op.drop_constraint("uq_channel_business_external", "customer_channels", type_="unique")
    op.create_unique_constraint("uq_channel_external", "customer_channels", ["channel", "external_id"])
    op.drop_constraint("customer_channels_business_id_fkey", "customer_channels", type_="foreignkey")
    op.drop_column("customer_channels", "business_id")

    op.drop_constraint("uq_customers_business_phone", "customers", type_="unique")
    op.create_unique_constraint("customers_phone_key", "customers", ["phone"])
    op.drop_index("ix_customers_business_id", "customers")
    op.drop_constraint("customers_business_id_fkey", "customers", type_="foreignkey")
    op.drop_column("customers", "contact_phone")
    op.drop_column("customers", "business_id")
