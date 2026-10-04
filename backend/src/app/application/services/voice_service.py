"""Voice pipeline. Audio never reaches AgentService; text does."""

from app.domain.models import AgentResponse, AudioInput, AudioOutput, InboundMessage, Transcript
from app.domain.ports import STTProvider, TTSProvider
from app.application.services.agent_service import AgentService


class VoiceService:
    """STT, then the same agent as chat, then TTS.

    Mock providers exchange audio ids. A real provider can return bytes
    behind the same methods without changing this class.
    """

    def __init__(self, stt: STTProvider, tts: TTSProvider, agent: AgentService) -> None:
        self.stt = stt
        self.tts = tts
        self.agent = agent

    async def transcribe(self, audio_id: str) -> Transcript:
        return await self.stt.transcribe(AudioInput(audio_id=audio_id))

    async def respond(
        self,
        *,
        audio_id: str,
        external_user_id: str,
        channel: str = "voice",
        language_hint: str | None = None,
        business_id=None,
        correlation_id: str | None = None,
        request_id: str | None = None,
    ) -> tuple[Transcript, AgentResponse, AudioOutput]:
        transcript = await self.transcribe(audio_id)
        message = InboundMessage(
            channel=channel,
            external_user_id=external_user_id,
            text=transcript.text,
            language_hint=language_hint or transcript.language,
            business_id=business_id,
            correlation_id=correlation_id,
            request_id=request_id,
            metadata={"audio_id": audio_id},
        )
        response = await self.agent.process_message(message)
        audio = await self.tts.synthesize(response.response_text)
        return transcript, response, audio
