"""ElevenLabs Speech-to-Text (Scribe) for chat voice messages.

Checked 2026-11-06 against elevenlabs.io/docs/api-reference/speech-to-text/convert and
elevenlabs.io/docs/capabilities/speech-to-text:
- POST https://api.elevenlabs.io/v1/speech-to-text, multipart/form-data, header xi-api-key;
  model_id "scribe_v2"; file; optional language_code (ISO-639-1 or -3); tag_audio_events.
- Response: text, language_code, language_probability, words[] with type and logprob
  (<= 0, higher is more confident), optional audio_duration_secs.
- OGG and Opus are accepted, no conversion. Kyrgyz (kir) is in the "Good" tier
  (>10% to <=20% WER), Russian in "Excellent" (<=5%).
- Query enable_logging=false is zero retention mode, "may only be used by enterprise
  customers". By default ElevenLabs keeps logs and transcripts.

The key is read from ELEVENLABS_API_KEY and never logged. The audio stays in memory.
"""

import logging
import math
import os

import httpx

from app.domain.errors import ProviderTransientError, ProviderUnavailable
from app.domain.models import AudioInput, Transcript
from app.domain.text_signals import detect_language

logger = logging.getLogger("plumo.stt.elevenlabs")

URL = "https://api.elevenlabs.io/v1/speech-to-text"
_LANGUAGES = {"ru": "ru", "rus": "ru", "ky": "ky", "kir": "ky"}
_EXTENSIONS = {"audio/ogg": "ogg", "audio/opus": "ogg", "audio/mpeg": "mp3", "audio/mp3": "mp3", "audio/mp4": "m4a", "audio/m4a": "m4a", "audio/x-m4a": "m4a", "audio/wav": "wav", "audio/x-wav": "wav", "audio/webm": "webm", "audio/flac": "flac"}


class ElevenLabsSTTProvider:
    name = "elevenlabs"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = "scribe_v2",
        zero_retention: bool = False,
        timeout_s: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._key = (api_key if api_key is not None else os.getenv("ELEVENLABS_API_KEY", "")).strip()
        self.model = model
        self.zero_retention = zero_retention
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(timeout_s, connect=5.0), transport=transport)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def transcribe(self, audio: AudioInput) -> Transcript:
        if not self._key:
            raise ProviderUnavailable("ELEVENLABS_API_KEY is not set")
        if not audio.content:
            raise ProviderUnavailable("no audio bytes to transcribe")
        mime = (audio.mime_type or "audio/ogg").split(";")[0].strip().lower()
        form = {"model_id": self.model, "tag_audio_events": "false", "timestamps_granularity": "word"}
        if audio.language_hint in ("ru", "ky"):
            form["language_code"] = audio.language_hint
        params = {"enable_logging": "false"} if self.zero_retention else None
        try:
            response = await self._client.post(
                URL,
                headers={"xi-api-key": self._key},
                params=params,
                data=form,
                files={"file": (f"voice.{_EXTENSIONS.get(mime, 'ogg')}", audio.content, mime)},
            )
        except httpx.TimeoutException:
            raise ProviderTransientError("stt_timeout") from None
        except httpx.HTTPError:
            raise ProviderTransientError("stt_network_error") from None
        status = response.status_code
        if status == 429 or status >= 500:
            raise ProviderTransientError(f"stt_http_{status}")
        if status >= 300:
            # 401 key, 402 balance, 400/422 audio or parameters: a retry gives the same answer.
            raise ProviderUnavailable(f"stt_http_{status}")
        try:
            payload = response.json()
        except ValueError:
            raise ProviderTransientError("stt_bad_json") from None
        text = " ".join(str(payload.get("text") or "").split())
        code = str(payload.get("language_code") or "").lower()
        language = _LANGUAGES.get(code) or detect_language(text)
        duration = payload.get("audio_duration_secs")
        return Transcript(
            text=text,
            language=language if language != "unknown" else "ru",
            audio_id=audio.audio_id,
            confidence=_confidence(payload.get("words")),
            duration_s=float(duration) if isinstance(duration, (int, float)) else None,
        )


def _confidence(words) -> float | None:
    """Mean word probability from logprobs, 0..1; None when the response has none."""

    if not isinstance(words, list):
        return None
    values = [
        math.exp(min(0.0, float(item["logprob"])))
        for item in words
        if isinstance(item, dict) and item.get("type", "word") == "word" and isinstance(item.get("logprob"), (int, float))
    ]
    return sum(values) / len(values) if values else None
