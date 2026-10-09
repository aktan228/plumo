"""Mock speech providers. They exchange ids, not audio bytes."""

import hashlib

from app.domain.models import AudioInput, AudioOutput, Transcript
from app.domain.text_signals import detect_language

_TRANSCRIPTS = {
    "mock_audio_apt": "Еще продается квартира за 85000?",
    "mock_audio_installment": "А рассрочка есть?",
    "mock_audio_hello": "Здравствуйте",
    "mock_audio_meeting": "Хочу записаться на встречу завтра в 15:00",
    "mock_audio_manager": "Позовите менеджера",
}
_DEFAULT = "Здравствуйте, хочу узнать про квартиру"


class MockSTTProvider:
    """Map a known audio id to a fixed transcript. Unknown ids use a greeting."""

    async def transcribe(self, audio: AudioInput) -> Transcript:
        text = _TRANSCRIPTS.get(audio.audio_id, _DEFAULT)
        language = detect_language(text)
        return Transcript(text=text, language=language if language != "unknown" else "ru", audio_id=audio.audio_id)


class MockTTSProvider:
    """Return a stable fake audio id for a text. No waveform is produced."""

    async def synthesize(self, text: str) -> AudioOutput:
        digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]
        return AudioOutput(audio_id=f"mock_audio_{digest}", text=text)
