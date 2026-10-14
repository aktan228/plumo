"""Map dashboard records to API schemas. Only safe fields leave the server."""

from app.api.dashboard_schemas import (
    AccountOut,
    ConnectionBriefOut,
    ConnectionOut,
    DeliveryOut,
    DialogCustomerOut,
    DialogItemOut,
    DialogMessageOut,
    ErrorStateOut,
    LastMessageOut,
)
from app.domain.models import ChannelConnection, Message, OutboundMessage
from app.infrastructure.database.dialog_queries import DialogRow

# Connection details that may be shown. Anything else stays server-side.
_SAFE_DETAILS = {
    "webhook_host",
    "pending_update_count",
    "telegram_last_error",
    "conflict_host",
    "account_type",
    "api_version",
    "disconnect_warning",
}


def account_out(connection: ChannelConnection) -> AccountOut:
    link = None
    if connection.username:
        if connection.channel == "telegram":
            link = f"https://t.me/{connection.username}"
        elif connection.channel == "instagram":
            link = f"https://instagram.com/{connection.username}"
    return AccountOut(
        external_id=connection.external_account_id,
        display_name=connection.display_name,
        username=connection.username,
        link=link,
    )


def connection_out(connection: ChannelConnection) -> ConnectionOut:
    error = None
    if connection.last_error_code:
        error = ErrorStateOut(
            code=connection.last_error_code,
            message=connection.last_error_message or "",
            at=connection.last_error_at,
        )
    return ConnectionOut(
        id=connection.id,
        channel=connection.channel,
        status=connection.status,
        auth_method=connection.auth_method,
        credential_ref=connection.credential_ref,
        account=account_out(connection),
        agent_enabled=connection.agent_enabled,
        version=connection.version,
        last_check_at=connection.last_check_at,
        last_check_ok=connection.last_check_ok,
        last_event_at=connection.last_event_at,
        last_error=error,
        details={key: value for key, value in connection.details.items() if key in _SAFE_DETAILS and value is not None},
        created_at=connection.created_at,
        updated_at=connection.updated_at,
        disconnected_at=connection.disconnected_at,
    )


def connection_brief_out(connection: ChannelConnection) -> ConnectionBriefOut:
    return ConnectionBriefOut(
        id=connection.id,
        channel=connection.channel,
        status=connection.status,
        agent_enabled=connection.agent_enabled,
        account=account_out(connection),
    )


def dialog_mode(mode: str, waiting: bool) -> str:
    if mode == "human":
        return "human"
    return "waiting" if waiting else "ai"


def dialog_item_out(row: DialogRow) -> DialogItemOut:
    last = None
    if row.last_text is not None and row.last_at is not None:
        last = LastMessageOut(text=row.last_text[:300], role=row.last_role or "user", at=row.last_at)
    return DialogItemOut(
        id=row.id,
        channel=row.channel,
        mode=dialog_mode(row.mode, row.waiting),
        mode_version=row.mode_version,
        customer=DialogCustomerOut(
            id=row.customer_id,
            name=row.contact_name,
            handle=row.contact_handle,
            phone=row.phone or row.contact_phone,
            language=row.language,
        ),
        connection_id=row.connection_id,
        last_message=last,
        activity_at=row.activity_at,
        unread=int(row.unread or 0),
        last_seq=row.last_seq,
    )


def delivery_out(outbound: OutboundMessage) -> DeliveryOut:
    return DeliveryOut(
        id=outbound.id,
        status=outbound.status,
        attempts=outbound.attempts,
        error_code=outbound.error_code,
        sent_at=outbound.sent_at,
        updated_at=outbound.updated_at,
    )


def dialog_message_out(message: Message, delivery: OutboundMessage | None = None) -> DialogMessageOut:
    meta = message.metadata or {}
    unsupported = meta.get("unsupported")
    return DialogMessageOut(
        id=message.id,
        seq=message.seq,
        role=message.role if message.role in ("user", "assistant", "manager", "system") else "system",
        text=message.text,
        timestamp=message.timestamp,
        author=str(meta["author"])[:100] if meta.get("author") else None,
        event=str(meta["event"]) if meta.get("event") else None,
        unsupported=str(unsupported) if unsupported else None,
        delivery=delivery_out(delivery) if delivery else None,
    )
