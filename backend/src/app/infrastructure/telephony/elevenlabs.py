"""ElevenLabs Agents wire format. Pure functions, no I/O.

ElevenLabs owns the phone leg: SIP trunk, speech recognition, turn-taking,
barge-in and speech synthesis. Plumo is plugged in as its "Custom LLM", so
every spoken turn still goes through AgentService: memory, knowledge,
router, validator and handoff. Voice and chat share one brain.

Three callbacks:

- custom LLM: OpenAI-compatible `chat/completions`, answered as SSE
- conversation initiation: caller id in, greeting and variables out
- post-call: transcript, duration and cost, signed with HMAC
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.domain.models import CallReport, CallTurn

PROVIDER = "elevenlabs"

# The agent's system prompt in the ElevenLabs dashboard must carry these
# markers so each LLM request says who is calling:
#   plumo_caller={{system__caller_id}} plumo_call={{system__conversation_id}} plumo_called={{system__called_number}}
_MARKER = re.compile(r"plumo_(caller|call|called|business)=([^\s{}]+)")
_MARKDOWN = re.compile(r"[*_`#>|]+")
_SPACES = re.compile(r"[ \t]+")
# Symbols a TTS voice spells out letter by letter. Numbers stay digits:
# the ElevenLabs normalizer reads them, and the validator needs digits.
_SPOKEN_UNITS = (
    (re.compile(r"\s*USD(?![A-Za-z])"), " долларов"),
    (re.compile(r"\s*(?:KGS|сом\b)"), " сомов"),
    (re.compile(r"\s*(?:м²|м2|кв\.\s?м\.?)"), " квадратных метров"),
    (re.compile(r"\s+—\s+"), ", "),
)


def parse_llm_request(body: dict[str, Any]) -> CallTurn:
    """Take the last user message and the call identity from a chat/completions body.

    History in `messages` is ignored on purpose: Plumo keeps its own memory,
    shared with chats, and builds the model context itself.
    """

    messages = body.get("messages") or []
    text = ""
    user_turns = 0
    markers: dict[str, str] = {}
    for item in messages:
        if not isinstance(item, dict):
            continue
        content = _content_text(item.get("content"))
        if item.get("role") == "system":
            markers.update(_markers(content))
        elif item.get("role") == "user" and content.strip():
            text = content.strip()
            user_turns += 1

    extra = body.get("elevenlabs_extra_body") or {}
    if not isinstance(extra, dict):
        extra = {}
    caller = _first(extra.get("caller_id"), markers.get("caller"), body.get("user_id"))
    call_id = _first(extra.get("conversation_id"), markers.get("call"))
    # The platform resends a turn after a network hiccup with the same history.
    # A turn the caller kept talking into comes back with longer text: a new id.
    message_id = None
    if call_id and text:
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
        message_id = f"{call_id[:96]}:{user_turns}:{digest}"
    return CallTurn(
        text=text,
        caller=caller,
        message_id=message_id,
        call_id=call_id,
        called=_first(extra.get("called_number"), markers.get("called")),
        business_id=_first(extra.get("business_id"), markers.get("business")),
    )


def for_speech(text: str) -> str:
    """Strip chat formatting that a TTS voice would read out loud."""

    for pattern, spoken in _SPOKEN_UNITS:
        text = pattern.sub(spoken, text)
    lines = [_SPACES.sub(" ", _MARKDOWN.sub("", line)).strip(" -•") for line in text.splitlines()]
    lines = [line for line in lines if line]
    joined = ""
    for line in lines:
        if joined and joined[-1] not in ".!?:;":
            joined += "."
        joined = f"{joined} {line}" if joined else line
    return joined.strip()


def sse_stream(text: str, model: str = "plumo") -> Iterator[str]:
    """Answer in OpenAI chat.completion.chunk SSE, which ElevenLabs requires.

    The reply is validated as a whole before it is spoken, so it goes out as
    one content chunk. Streaming tokens would let an unvalidated price reach
    the caller's ear before the validator sees it.
    """

    chunk_id = f"chatcmpl-{uuid4().hex}"
    created = int(time.time())

    def chunk(delta: dict[str, Any], finish: str | None = None) -> str:
        payload = {
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
        }
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    yield chunk({"role": "assistant", "content": ""})
    if text:
        yield chunk({"content": text})
    yield chunk({}, "stop")
    yield "data: [DONE]\n\n"


def parse_initiation(body: dict[str, Any]) -> CallTurn:
    """Inbound-call webhook body: caller_id, called_number, call_sid, agent_id."""

    return CallTurn(
        text="",
        caller=_first(body.get("caller_id")),
        call_id=_first(body.get("call_sid"), body.get("conversation_id")),
        called=_first(body.get("called_number")),
    )


def initiation_response(first_message: str, language: str, variables: dict[str, str]) -> dict[str, Any]:
    """Greeting override. "Overrides → first message, language" must be allowed on the agent."""

    return {
        "type": "conversation_initiation_client_data",
        "dynamic_variables": variables,
        "conversation_config_override": {
            "agent": {
                "first_message": first_message,
                "language": "ky" if language == "ky" else "ru",
            }
        },
    }


def verify_signature(header: str | None, body: bytes, secret: str, *, tolerance_s: int = 1800, now: float | None = None) -> bool:
    """Check `ElevenLabs-Signature: t=<unix>,v0=<hex hmac_sha256(secret, "t.body")>`."""

    if not header or not secret:
        return False
    parts = dict(item.split("=", 1) for item in header.split(",") if "=" in item)
    stamp = parts.get("t", "")
    given = parts.get("v0", "")
    if not stamp.isdigit() or not given:
        return False
    current = time.time() if now is None else now
    if abs(current - int(stamp)) > tolerance_s:
        return False
    expected = hmac.new(secret.encode(), f"{stamp}.".encode() + body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, given)


def parse_post_call(payload: dict[str, Any]) -> CallReport | None:
    """Return a report for `post_call_transcription`; other event types are ignored."""

    if payload.get("type") != "post_call_transcription":
        return None
    data = payload.get("data") or {}
    meta = data.get("metadata") or {}
    phone = meta.get("phone_call") or {}
    client = data.get("conversation_initiation_client_data") or {}
    variables = client.get("dynamic_variables") or {}
    call_id = _first(data.get("conversation_id"))
    if call_id is None:
        return None
    started = meta.get("start_time_unix_secs")
    started_at = datetime.fromtimestamp(int(started), UTC) if isinstance(started, (int, float)) else datetime.now(UTC)
    cost = meta.get("cost")
    transcript = [_turn(item) for item in data.get("transcript") or [] if isinstance(item, dict)]
    return CallReport(
        call_id=call_id,
        caller=_first(phone.get("external_number"), variables.get("system__caller_id")),
        called=_first(phone.get("agent_number"), variables.get("system__called_number")),
        status="completed" if data.get("status") in ("done", None) else "failed",
        started_at=started_at,
        duration_s=int(meta.get("call_duration_secs") or 0),
        provider_cost=float(cost) if isinstance(cost, (int, float)) else None,
        transcript=transcript,
        raw_metadata={
            "agent_id": data.get("agent_id"),
            "termination_reason": meta.get("termination_reason"),
            "provider_cost_credits": cost,
            "latency": _latency_summary(transcript),
        },
    )


def _turn(item: dict[str, Any]) -> dict[str, Any]:
    entry = {"role": item.get("role"), "message": item.get("message"), "t": item.get("time_in_call_secs")}
    metrics = _turn_metrics(item.get("conversation_turn_metrics"))
    if metrics:
        entry["metrics"] = metrics
    if item.get("interrupted") is not None:
        entry["interrupted"] = bool(item.get("interrupted"))
    return entry


def _turn_metrics(raw: Any) -> dict[str, float]:
    """`{"convai_llm_service_ttfb": {"elapsed_time": 0.37}, ...}` → `{"llm_service_ttfb": 0.37}` in seconds.

    The platform measures our Custom LLM endpoint here: time to the first
    token and to the first sentence, as the caller experiences it.
    """

    if isinstance(raw, dict) and isinstance(raw.get("metrics"), dict):
        raw = raw["metrics"]
    if not isinstance(raw, dict):
        return {}
    metrics: dict[str, float] = {}
    for key, value in raw.items():
        elapsed = value.get("elapsed_time") if isinstance(value, dict) else value
        if isinstance(elapsed, (int, float)):
            metrics[str(key).removeprefix("convai_")] = round(float(elapsed), 3)
    return metrics


def _latency_summary(transcript: list[dict[str, Any]]) -> dict[str, float]:
    """p50 and max per metric over the agent's turns, for the call row."""

    values: dict[str, list[float]] = {}
    for item in transcript:
        for key, value in (item.get("metrics") or {}).items():
            values.setdefault(key, []).append(value)
    summary: dict[str, float] = {}
    for key, series in values.items():
        ordered = sorted(series)
        summary[f"{key}_p50"] = ordered[len(ordered) // 2]
        summary[f"{key}_max"] = ordered[-1]
    return summary


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(str(part.get("text") or "") for part in content if isinstance(part, dict))
    return ""


def _markers(text: str) -> dict[str, str]:
    return {key: value for key, value in _MARKER.findall(text)}


def _first(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text and not text.startswith("{{"):
            return text
    return None
