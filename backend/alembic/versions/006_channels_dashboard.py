"""Real Telegram/Instagram channels and the team dashboard.

- operators and their sessions: the dashboard is closed, each operator sees one business;
- channel_connections: a bot or Instagram account linked to a business, secrets stay on the server;
- inbound_events, jobs, outbound_messages: a webhook is stored before 2xx, a worker answers,
  every reply has one delivery record;
- conversations get business_id, the connection, the reply target and the dialog mode;
- messages get `seq`, a stable insertion order and the operator's read cursor.

Existing dialogs: business_id comes from the customer; dialogs with an ACCEPTED handoff
start in `human` mode, the rest in `ai`. Old dialogs have no connection: they stay
readable, a manager cannot send into them from the dashboard.

Revision ID: 006_channels_dashboard
Revises: 005_business_profile
Create Date: 2026-10-14
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "006_channels_dashboard"
down_revision = "005_business_profile"
branch_labels = None
depends_on = None

_UUID = postgresql.UUID(as_uuid=True)
_TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "operators",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("business_id", _UUID, sa.ForeignKey("businesses.id"), nullable=False),
        sa.Column("email", sa.String(254), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(100), nullable=False, server_default=""),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", _TS, nullable=False),
        sa.Column("updated_at", _TS, nullable=False),
    )
    op.create_index("ix_operators_business_id", "operators", ["business_id"])

    op.create_table(
        "operator_sessions",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("operator_id", _UUID, sa.ForeignKey("operators.id"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", _TS, nullable=False),
        sa.Column("expires_at", _TS, nullable=False),
        sa.Column("last_seen_at", _TS, nullable=False),
        sa.Column("revoked_at", _TS, nullable=True),
    )
    op.create_index("ix_operator_sessions_operator_id", "operator_sessions", ["operator_id"])

    op.create_table(
        "channel_connections",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("business_id", _UUID, sa.ForeignKey("businesses.id"), nullable=False),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("credential_ref", sa.String(64), nullable=False),
        sa.Column("auth_method", sa.String(32), nullable=False, server_default="server_credential"),
        sa.Column("external_account_id", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False, server_default=""),
        sa.Column("username", sa.String(100), nullable=True),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("agent_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("webhook_nonce", sa.String(64), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("last_check_at", _TS, nullable=True),
        sa.Column("last_check_ok", sa.Boolean(), nullable=True),
        sa.Column("last_event_at", _TS, nullable=True),
        sa.Column("last_error_code", sa.String(64), nullable=True),
        sa.Column("last_error_message", sa.String(300), nullable=True),
        sa.Column("last_error_at", _TS, nullable=True),
        sa.Column("details", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", _TS, nullable=False),
        sa.Column("updated_at", _TS, nullable=False),
        sa.Column("disconnected_at", _TS, nullable=True),
        sa.UniqueConstraint("business_id", "channel", "external_account_id", name="uq_connection_business_account"),
    )
    op.create_index("ix_channel_connections_business_id", "channel_connections", ["business_id"])
    op.create_index(
        "uq_connection_active_business_channel",
        "channel_connections",
        ["business_id", "channel"],
        unique=True,
        postgresql_where=sa.text("status <> 'disconnected'"),
    )
    op.create_index(
        "uq_connection_active_account",
        "channel_connections",
        ["channel", "external_account_id"],
        unique=True,
        postgresql_where=sa.text("status <> 'disconnected'"),
    )

    op.create_table(
        "inbound_events",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("business_id", _UUID, sa.ForeignKey("businesses.id"), nullable=False),
        sa.Column("connection_id", _UUID, sa.ForeignKey("channel_connections.id"), nullable=False),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("external_event_id", sa.String(128), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("sender_id", sa.String(128), nullable=True),
        sa.Column("provider_message_id", sa.String(128), nullable=True),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("data", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("provider_time", _TS, nullable=True),
        sa.Column("received_at", _TS, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("processed_at", _TS, nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.UniqueConstraint("connection_id", "external_event_id", name="uq_inbound_connection_event"),
    )
    op.create_index("ix_inbound_events_business_id", "inbound_events", ["business_id"])
    op.create_index("ix_inbound_events_status", "inbound_events", ["status"])

    # Conversations: business, connection, reply target and mode.
    op.add_column("conversations", sa.Column("business_id", _UUID, nullable=True))
    op.execute("UPDATE conversations c SET business_id = cu.business_id FROM customers cu WHERE cu.id = c.customer_id")
    op.alter_column("conversations", "business_id", nullable=False)
    op.create_foreign_key(
        "conversations_business_id_fkey", "conversations", "businesses", ["business_id"], ["id"]
    )
    op.create_index("ix_conversations_business_id", "conversations", ["business_id"])
    op.add_column("conversations", sa.Column("connection_id", _UUID, nullable=True))
    op.create_foreign_key(
        "conversations_connection_id_fkey", "conversations", "channel_connections", ["connection_id"], ["id"]
    )
    op.create_index("ix_conversations_connection_id", "conversations", ["connection_id"])
    op.add_column("conversations", sa.Column("mode", sa.String(16), nullable=False, server_default="ai"))
    op.add_column("conversations", sa.Column("mode_version", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("conversations", sa.Column("mode_changed_at", _TS, nullable=True))
    op.add_column("conversations", sa.Column("external_chat_id", sa.String(128), nullable=True))
    op.add_column("conversations", sa.Column("contact_name", sa.String(200), nullable=True))
    op.add_column("conversations", sa.Column("contact_handle", sa.String(100), nullable=True))
    op.execute(
        """
        UPDATE conversations c SET mode = 'human', mode_version = 1, mode_changed_at = h.updated_at
        FROM (
            SELECT conversation_id, max(updated_at) AS updated_at
            FROM handoff_requests WHERE status = 'ACCEPTED' GROUP BY conversation_id
        ) AS h
        WHERE h.conversation_id = c.id
        """
    )

    # Messages: insertion order. Existing rows are numbered by time.
    op.add_column("messages", sa.Column("seq", sa.BigInteger(), nullable=True))
    op.execute(
        """
        UPDATE messages m SET seq = numbered.n
        FROM (SELECT id, row_number() OVER (ORDER BY timestamp, created_at, id) AS n FROM messages) AS numbered
        WHERE numbered.id = m.id
        """
    )
    op.execute("ALTER TABLE messages ALTER COLUMN seq SET NOT NULL")
    op.execute("ALTER TABLE messages ALTER COLUMN seq ADD GENERATED BY DEFAULT AS IDENTITY")
    op.execute("SELECT setval(pg_get_serial_sequence('messages', 'seq'), COALESCE((SELECT max(seq) FROM messages), 0) + 1, false)")
    op.create_unique_constraint("messages_seq_key", "messages", ["seq"])
    op.create_index("ix_messages_conversation_timestamp", "messages", ["conversation_id", "timestamp", "seq"])

    op.create_table(
        "outbound_messages",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("business_id", _UUID, sa.ForeignKey("businesses.id"), nullable=False),
        sa.Column("conversation_id", _UUID, sa.ForeignKey("conversations.id"), nullable=False),
        sa.Column("connection_id", _UUID, sa.ForeignKey("channel_connections.id"), nullable=True),
        sa.Column("message_id", _UUID, sa.ForeignKey("messages.id"), nullable=True, unique=True),
        sa.Column("author_role", sa.String(16), nullable=False),
        sa.Column("operator_id", _UUID, sa.ForeignKey("operators.id"), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("mode_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("parts_sent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("provider_message_ids", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("error_message", sa.String(300), nullable=True),
        sa.Column("created_at", _TS, nullable=False),
        sa.Column("updated_at", _TS, nullable=False),
        sa.Column("sent_at", _TS, nullable=True),
        sa.UniqueConstraint("business_id", "idempotency_key", name="uq_outbound_business_idempotency"),
    )
    op.create_index("ix_outbound_messages_business_id", "outbound_messages", ["business_id"])
    op.create_index("ix_outbound_messages_conversation_id", "outbound_messages", ["conversation_id"])
    op.create_index("ix_outbound_messages_status", "outbound_messages", ["status"])

    op.create_table(
        "jobs",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("business_id", _UUID, sa.ForeignKey("businesses.id"), nullable=False),
        sa.Column("ordering_key", sa.String(200), nullable=False),
        sa.Column("inbound_event_id", _UUID, sa.ForeignKey("inbound_events.id"), nullable=True),
        sa.Column("outbound_message_id", _UUID, sa.ForeignKey("outbound_messages.id"), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("run_at", _TS, nullable=False),
        sa.Column("locked_until", _TS, nullable=True),
        sa.Column("locked_by", sa.String(64), nullable=True),
        sa.Column("last_error", sa.String(300), nullable=True),
        sa.Column("created_at", _TS, nullable=False),
        sa.Column("updated_at", _TS, nullable=False),
        sa.Column("finished_at", _TS, nullable=True),
    )
    op.create_index("ix_jobs_status_run_at", "jobs", ["status", "run_at"])
    op.create_index("ix_jobs_ordering_key_id", "jobs", ["ordering_key", "id"])

    op.create_table(
        "conversation_reads",
        sa.Column("operator_id", _UUID, sa.ForeignKey("operators.id"), primary_key=True),
        sa.Column("conversation_id", _UUID, sa.ForeignKey("conversations.id"), primary_key=True),
        sa.Column("last_read_seq", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("updated_at", _TS, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("conversation_reads")
    op.drop_index("ix_jobs_ordering_key_id", "jobs")
    op.drop_index("ix_jobs_status_run_at", "jobs")
    op.drop_table("jobs")
    op.drop_table("outbound_messages")

    op.drop_index("ix_messages_conversation_timestamp", "messages")
    op.drop_constraint("messages_seq_key", "messages", type_="unique")
    op.drop_column("messages", "seq")

    for column in ("contact_handle", "contact_name", "external_chat_id", "mode_changed_at", "mode_version", "mode"):
        op.drop_column("conversations", column)
    op.drop_index("ix_conversations_connection_id", "conversations")
    op.drop_constraint("conversations_connection_id_fkey", "conversations", type_="foreignkey")
    op.drop_column("conversations", "connection_id")
    op.drop_index("ix_conversations_business_id", "conversations")
    op.drop_constraint("conversations_business_id_fkey", "conversations", type_="foreignkey")
    op.drop_column("conversations", "business_id")

    op.drop_table("inbound_events")
    op.drop_index("uq_connection_active_account", "channel_connections")
    op.drop_index("uq_connection_active_business_channel", "channel_connections")
    op.drop_table("channel_connections")
    op.drop_table("operator_sessions")
    op.drop_table("operators")
