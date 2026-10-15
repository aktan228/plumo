"""Instagram API with Instagram Login: Direct messages of one professional account.

Checked against Meta docs on 2026-10-14 (developers.facebook.com/docs/instagram-platform):
host graph.instagram.com, version pinned in INSTAGRAM_API_VERSION (docs show v25.0),
GET /me?fields=user_id,username,name,account_type, POST /me/subscribed_apps?subscribed_fields=messages,
POST /me/messages {"recipient": {"id": IGSID}, "message": {"text": ...}} with a Bearer
Instagram User token, text up to 1000 bytes, a reply only within 24 hours of the
customer's last message. Webhooks: GET verification with hub.verify_token, POST
signed with X-Hub-Signature-256 = "sha256=" + HMAC-SHA256(app secret, raw body).

Error codes below follow the Graph API conventions (190 token, 10/200-299
permissions, 4/17/32/613 throttling, 551 user unavailable); confirm them on the
live app, Meta changes subcodes without notice.
"""

import hashlib
import hmac
import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from app.infrastructure.channels.base import AccountInfo, ChannelError, ChannelEvent, clip_inbound

logger = logging.getLogger("plumo.channels.instagram")

API = "https://graph.instagram.com"
# Subcodes Meta uses for "sent outside of the allowed window".
_WINDOW_SUBCODES = {2534022, 2018278}


class InstagramClient:
    def __init__(
        self,
        access_token: str,
        *,
        api_version: str = "v25.0",
        timeout_s: float = 15.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._token = access_token
        self._base = f"{API}/{api_version.strip() or 'v25.0'}"
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(timeout_s, connect=5.0), transport=transport)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get_me(self) -> AccountInfo:
        data = await self._call("GET", "/me", params={"fields": "user_id,username,name,account_type"})
        account_id = str(data.get("user_id") or "")
        if not account_id:
            raise ChannelError("bad_request", "unexpected_response", "Instagram returned no user_id")
        username = data.get("username")
        return AccountInfo(
            external_account_id=account_id,
            display_name=str(data.get("name") or username or "Instagram"),
            username=username,
            details={"account_type": data.get("account_type")},
        )

    async def subscribe_messages(self) -> None:
        data = await self._call("POST", "/me/subscribed_apps", params={"subscribed_fields": "messages"})
        if not data.get("success"):
            raise ChannelError("permission", "subscription_failed", "Instagram did not confirm the messages subscription")

    async def unsubscribe(self) -> None:
        await self._call("DELETE", "/me/subscribed_apps")

    async def send_message(self, recipient_id: str, text: str) -> str:
        data = await self._call(
            "POST",
            "/me/messages",
            json={"recipient": {"id": recipient_id}, "message": {"text": text}},
            sends=True,
        )
        message_id = data.get("message_id")
        if not message_id:
            raise ChannelError("ambiguous", "no_message_id", "Instagram answered without message_id")
        return str(message_id)

    async def _call(self, method: str, path: str, *, params=None, json=None, sends: bool = False) -> dict:
        headers = {"Authorization": f"Bearer {self._token}"}
        try:
            response = await self._client.request(method, self._base + path, params=params, json=json, headers=headers)
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout):
            raise ChannelError("transient", "instagram_unreachable", "Instagram is unreachable") from None
        except httpx.TimeoutException:
            kind = "ambiguous" if sends else "transient"
            raise ChannelError(kind, "instagram_timeout", "Instagram did not answer in time") from None
        except httpx.HTTPError:
            kind = "ambiguous" if sends else "transient"
            raise ChannelError(kind, "instagram_network_error", "network error talking to Instagram") from None
        return _result(response, sends)


def _result(response: httpx.Response, sends: bool) -> dict:
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    if response.status_code < 300 and isinstance(payload, dict) and "error" not in payload:
        return payload
    error = payload.get("error") if isinstance(payload, dict) else None
    error = error if isinstance(error, dict) else {}
    status = response.status_code
    code = _int(error.get("code"))
    subcode = _int(error.get("error_subcode"))
    message = str(error.get("message") or f"HTTP {status}")[:200]
    if code == 190 or status == 401:
        raise ChannelError("auth", "token_invalid", message, status=status)
    if subcode in _WINDOW_SUBCODES:
        raise ChannelError("window", "window_closed", message, status=status)
    if code in (4, 17, 32, 613) or status == 429:
        raise ChannelError("rate_limited", "instagram_rate_limited", message, retry_after=60.0, status=status)
    if code == 10 or (code is not None and 200 <= code <= 299) or status == 403:
        raise ChannelError("permission", "missing_permission", message, status=status)
    if code == 551:
        raise ChannelError("recipient", "recipient_unavailable", message, status=status)
    if status >= 500 or code in (1, 2):
        kind = "ambiguous" if sends else "transient"
        raise ChannelError(kind, "instagram_server_error", message, status=status)
    raise ChannelError("bad_request", "instagram_bad_request", message, status=status)


def _int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def valid_signature(app_secret: str, raw_body: bytes, header: str | None) -> bool:
    """X-Hub-Signature-256 check on the exact bytes Meta sent, before JSON parsing."""

    if not app_secret or not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.removeprefix("sha256="))


def parse_entry(entry: dict[str, Any]) -> list[ChannelEvent]:
    """Messaging events of one webhook entry. `entry.id` is the business's account (IG_ID).

    Customer text → text; attachments and unsupported content → unsupported.
    Echoes of our own messages, read receipts, reactions, edits, deletions and
    postbacks are ignored: no model run, no reply, nothing stored about them.
    """

    account_id = str(entry.get("id") or "")
    events: list[ChannelEvent] = []
    for item in entry.get("messaging") or []:
        if not isinstance(item, dict):
            continue
        message = item.get("message")
        if not isinstance(message, dict):
            continue
        mid = str(message.get("mid") or "")
        sender = str((item.get("sender") or {}).get("id") or "")
        recipient = str((item.get("recipient") or {}).get("id") or "")
        if not mid or not sender:
            continue
        if message.get("is_echo") or sender == account_id or (account_id and recipient and recipient != account_id):
            continue
        if message.get("is_deleted"):
            continue
        when = _time(item.get("timestamp"))
        data: dict[str, Any] = {"chat_id": sender}
        text = message.get("text")
        if isinstance(text, str) and text.strip() and not message.get("attachments"):
            clipped, cut = clip_inbound(text)
            if cut:
                data["truncated"] = True
            events.append(ChannelEvent(mid, "text", sender, sender, mid, clipped, when, data))
            continue
        attachments = message.get("attachments") or []
        kinds = [str(part.get("type") or "file") for part in attachments if isinstance(part, dict)]
        media = kinds[0] if kinds else "unsupported"
        data["unsupported"] = media
        events.append(ChannelEvent(mid, "unsupported", sender, sender, mid, f"[{media}]", when, data))
    return events


def _time(value) -> datetime | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    # Meta sends milliseconds in `timestamp`.
    if number > 10**11:
        number /= 1000
    try:
        return datetime.fromtimestamp(number, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None
