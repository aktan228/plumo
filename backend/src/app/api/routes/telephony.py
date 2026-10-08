"""Phone calls through ElevenLabs Agents.

Setup in the ElevenLabs dashboard (see README, section "Телефония"):

- Agent → LLM → Custom LLM, server URL `https://<host>/api/v1/telephony/elevenlabs/v1`,
  API key = ELEVENLABS_LLM_TOKEN.
- Agent system prompt: `plumo_caller={{system__caller_id}} plumo_call={{system__conversation_id}}`.
- Conversation initiation webhook → `/api/v1/telephony/elevenlabs/initiation`
  with header `Authorization: Bearer <ELEVENLABS_LLM_TOKEN>`.
- Post-call webhook → `/api/v1/telephony/elevenlabs/post-call`, HMAC secret = ELEVENLABS_WEBHOOK_SECRET.
"""

import hmac
import json
import logging
import os

from fastapi import APIRouter, Body, Depends, Request
from fastapi.responses import StreamingResponse

from app.api.deps import Services, get_services
from app.domain.errors import AppError, ProviderUnavailable, Unauthorized
from app.domain.phrases import voice_failure_phrase
from app.infrastructure.telephony.elevenlabs import (
    for_speech,
    initiation_response,
    parse_initiation,
    parse_llm_request,
    parse_post_call,
    sse_stream,
    verify_signature,
)

logger = logging.getLogger("plumo.telephony")

router = APIRouter(prefix="/telephony/elevenlabs", tags=["telephony"])


@router.post("/v1/chat/completions", summary="Custom LLM для ElevenLabs: реплика звонящего → ответ агента (SSE)")
@router.post("/chat/completions", include_in_schema=False)
async def chat_completions(
    request: Request,
    body: dict = Body(...),
    services: Services = Depends(get_services),
) -> StreamingResponse:
    _require_token(request)
    turn = parse_llm_request(body)
    try:
        # A failed turn must not leave half a pipeline in the transaction,
        # and must not leave the caller in silence either.
        async with services.session.begin_nested():
            reply = await services.calls.answer(turn)
        text = for_speech(reply.text)
    except AppError as exc:
        logger.warning("call_turn_failed", extra={"error": exc.code, "call_id": turn.call_id})
        text = voice_failure_phrase("ru")
    return StreamingResponse(sse_stream(text), media_type="text/event-stream")


@router.post("/initiation", summary="Webhook начала входящего звонка: приветствие и память")
async def initiation(
    request: Request,
    body: dict = Body(...),
    services: Services = Depends(get_services),
) -> dict:
    _require_token(request)
    greeting = await services.calls.start(parse_initiation(body))
    return initiation_response(greeting.text, greeting.language, greeting.variables)


@router.post("/post-call", summary="Webhook после звонка: длительность, стоимость, расшифровка")
async def post_call(request: Request, services: Services = Depends(get_services)) -> dict:
    raw = await request.body()
    secret = os.getenv("ELEVENLABS_WEBHOOK_SECRET", "").strip()
    if not secret:
        raise ProviderUnavailable("ELEVENLABS_WEBHOOK_SECRET is not set")
    if not verify_signature(request.headers.get("elevenlabs-signature"), raw, secret):
        raise Unauthorized("bad webhook signature")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise Unauthorized("webhook body is not JSON") from exc
    report = parse_post_call(payload if isinstance(payload, dict) else {})
    if report is None:
        return {"status": "ignored"}
    call = await services.calls.finish(report)
    return {"status": "ok", "call_id": str(call.id)}


def _require_token(request: Request) -> None:
    expected = os.getenv("ELEVENLABS_LLM_TOKEN", "").strip()
    if not expected:
        raise ProviderUnavailable("ELEVENLABS_LLM_TOKEN is not set")
    header = request.headers.get("authorization", "")
    given = header[7:].strip() if header.lower().startswith("bearer ") else request.headers.get("x-plumo-token", "")
    if not hmac.compare_digest(given.encode(), expected.encode()):
        raise Unauthorized("bad voice platform token")
