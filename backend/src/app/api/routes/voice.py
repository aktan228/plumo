"""Mock voice entry points."""

from fastapi import APIRouter, Depends

from app.api.deps import Services, get_services
from app.api.mappers import agent_out
from app.api.schemas import TranscriptOut, TranscribeIn, VoiceRespondIn, VoiceRespondOut
from app.correlation import get_correlation_id, get_request_id

router = APIRouter(prefix="/voice", tags=["voice"])


@router.post("/transcribe", response_model=TranscriptOut, summary="Распознать аудио (mock STT)")
async def transcribe(body: TranscribeIn, services: Services = Depends(get_services)) -> TranscriptOut:
    transcript = await services.voice.transcribe(body.audio_id)
    return TranscriptOut(text=transcript.text, language=transcript.language, audio_id=transcript.audio_id)


@router.post(
    "/respond",
    response_model=VoiceRespondOut,
    summary="Аудио → текст → агент → аудио (mock)",
)
async def respond(body: VoiceRespondIn, services: Services = Depends(get_services)) -> VoiceRespondOut:
    transcript, response, audio = await services.voice.respond(
        audio_id=body.audio_id,
        external_user_id=body.external_user_id,
        channel=body.channel,
        language_hint=body.language_hint,
        business_id=body.business_id,
        correlation_id=get_correlation_id() or None,
        request_id=get_request_id() or None,
    )
    return VoiceRespondOut(
        transcript=TranscriptOut(text=transcript.text, language=transcript.language, audio_id=transcript.audio_id),
        audio=TranscriptOut(text=audio.text, language=transcript.language, audio_id=audio.audio_id),
        response=agent_out(response),
    )
