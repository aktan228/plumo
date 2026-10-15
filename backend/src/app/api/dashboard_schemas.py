"""HTTP schemas of the team dashboard: sign-in, integrations, dialogs, deliveries.

No secret ever appears here: tokens, webhook secrets and service keys stay on the server.
"""

from datetime import datetime as DateTime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.api.schemas import CustomerOut, HandoffOut, SummaryOut


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=200)


class BusinessBriefOut(BaseModel):
    id: UUID
    name: str


class OperatorOut(BaseModel):
    id: UUID
    email: str
    display_name: str
    business: BusinessBriefOut


class SessionOut(BaseModel):
    operator: OperatorOut
    expires_at: DateTime
    ai_mode: str = Field(description="mock — ответы ядра без живой модели; production — подключённая LLM.")


class LoginOut(SessionOut):
    token: str = Field(description="Значение HttpOnly cookie. Только для сервера Next.js, не для браузерного кода.")


# ---- integrations ---------------------------------------------------------------------


class AccountOut(BaseModel):
    external_id: str
    display_name: str
    username: str | None = None
    link: str | None = None


class ErrorStateOut(BaseModel):
    code: str
    message: str
    at: DateTime | None = None


class ConnectionOut(BaseModel):
    id: UUID
    channel: str
    status: Literal["not_connected", "connecting", "connected", "action_required", "error", "disconnected"]
    auth_method: str
    credential_ref: str
    account: AccountOut
    agent_enabled: bool
    version: int
    last_check_at: DateTime | None = None
    last_check_ok: bool | None = None
    last_event_at: DateTime | None = None
    last_error: ErrorStateOut | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: DateTime
    updated_at: DateTime
    disconnected_at: DateTime | None = None


class CredentialOut(BaseModel):
    ref: str
    label: str


class ChannelIntegrationOut(BaseModel):
    channel: Literal["telegram", "instagram"]
    status: str
    connection: ConnectionOut | None = None
    credentials: list[CredentialOut]
    requirements: dict[str, bool]
    webhook_url: str | None = Field(default=None, description="Callback для Meta App Dashboard (Instagram).")


class IntegrationsOut(BaseModel):
    channels: list[ChannelIntegrationOut]
    ai_mode: str


class ConnectIn(BaseModel):
    credential_ref: str = Field(min_length=1, max_length=64)
    replace_webhook: bool = Field(
        default=False, description="Telegram: заменить webhook, который сейчас указывает на другой адрес."
    )


class IntegrationPatchIn(BaseModel):
    agent_enabled: bool
    version: int | None = Field(default=None, description="Версия из GET; при расхождении 409 version_conflict.")


# ---- dialogs --------------------------------------------------------------------------


class DialogCustomerOut(BaseModel):
    id: UUID
    name: str | None = None
    handle: str | None = None
    phone: str | None = None
    language: str


class LastMessageOut(BaseModel):
    text: str
    role: str
    at: DateTime


class DialogItemOut(BaseModel):
    id: UUID
    channel: str
    mode: Literal["ai", "waiting", "human"]
    mode_version: int
    customer: DialogCustomerOut
    connection_id: UUID | None = None
    last_message: LastMessageOut | None = None
    activity_at: DateTime
    unread: int
    last_seq: int | None = None


class DialogListOut(BaseModel):
    items: list[DialogItemOut]
    next_cursor: str | None = None


class DeliveryOut(BaseModel):
    id: UUID
    status: Literal["queued", "sending", "sent", "failed", "unknown", "cancelled"]
    attempts: int
    error_code: str | None = None
    sent_at: DateTime | None = None
    updated_at: DateTime


class DialogMessageOut(BaseModel):
    id: UUID
    seq: int | None = None
    role: Literal["user", "assistant", "manager", "system"]
    text: str
    timestamp: DateTime
    author: str | None = None
    event: str | None = Field(default=None, description="takeover / resume для системных событий.")
    unsupported: str | None = Field(default=None, description="Тип вложения, которое канал прислал вместо текста.")
    delivery: DeliveryOut | None = None


class ReplyStateOut(BaseModel):
    allowed: bool
    reason: str | None = None
    max_chars: int | None = None
    max_bytes: int | None = None
    window_expires_at: DateTime | None = None


class ConnectionBriefOut(BaseModel):
    id: UUID
    channel: str
    status: str
    agent_enabled: bool
    account: AccountOut


class DialogDetailOut(BaseModel):
    dialog: DialogItemOut
    messages: list[DialogMessageOut]
    older_cursor: str | None = None
    customer: CustomerOut
    summary: SummaryOut | None = None
    handoff: HandoffOut | None = None
    connection: ConnectionBriefOut | None = None
    reply: ReplyStateOut


class DialogMessagesOut(BaseModel):
    messages: list[DialogMessageOut]
    older_cursor: str | None = None


class DialogStateOut(BaseModel):
    id: UUID
    mode: Literal["ai", "waiting", "human"]
    mode_version: int


class ManagerSendIn(BaseModel):
    text: str = Field(min_length=1, max_length=4096)
    idempotency_key: str = Field(
        min_length=8,
        max_length=100,
        description="Один ключ на одно нажатие «Отправить»; повтор с тем же ключом вернёт ту же операцию.",
    )


class ManagerSendOut(BaseModel):
    message: DialogMessageOut
    delivery: DeliveryOut
    created: bool


class ReadIn(BaseModel):
    seq: int = Field(ge=0, description="seq последнего показанного сообщения.")


class ReadOut(BaseModel):
    last_read_seq: int
    unread: int


class ResolveDeliveryIn(BaseModel):
    action: Literal["retry", "mark_sent", "mark_failed"]
