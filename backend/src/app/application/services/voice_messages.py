"""Telegram voice messages in the worker: download, transcribe once, decide what the agent gets.

The audio lives only in memory for one transcription; it is never written to disk or the
database. What a paid transcription produced is saved on the inbound event in its own
committed transaction, so a job retried after a crash reuses it instead of downloading
and paying again. Logs carry the event id, duration, provider and a safe error code only:
no transcript, no file_id, no token.
"""

import logging
import re
from dataclasses import dataclass

from app.domain.enums import VoiceNotice
from app.domain.errors import ProviderTransientError, ProviderUnavailable
from app.domain.models import AudioInput, InboundEvent
from app.infrastructure.channels.base import ChannelError, clip_inbound
from app.infrastructure.channels.telegram import DOWNLOAD_LIMIT_BYTES
from app.infrastructure.database.channel_repositories import InboundEventRepository

logger = logging.getLogger("plumo.voice_messages")

# Sounds without content. "да", "ага", "нет" are answers and stay.
_FILLERS = frozenset({"э", "ээ", "эээ", "эм", "эмм", "мм", "ммм", "м", "хм", "хмм", "а", "аа", "ааа", "ну", "ой", "ох", "ах", "уф", "ух"})
_TAGS = re.compile(r"[\(\[][^\)\]]{0,40}[\)\]]")
_WORD = re.compile(r"[^\W\d_]+|\d+", re.UNICODE)


@dataclass
class VoiceOutcome:
    """What the agent gets for one voice message."""

    # text: a transcript for the usual turn; otherwise a VoiceNotice for a fixed line.
    kind: str
    text: str | None = None
    language: str | None = None
    confidence: float | None = None
    cost_usd: float = 0.0
    error_code: str | None = None


def too_long(event: InboundEvent, max_seconds: int) -> bool:
    """Refused before download: over our duration limit or over what a bot may download."""

    duration = event.data.get("duration")
    size = event.data.get("file_size")
    return (isinstance(duration, int) and duration > max_seconds) or (
        isinstance(size, int) and size > DOWNLOAD_LIMIT_BYTES
    )


def stt_estimate_usd(event: InboundEvent, settings) -> float:
    """Reserve for transcription: the stated duration (the limit when unknown) at the configured price."""

    duration = event.data.get("duration")
    seconds = duration if isinstance(duration, int) and duration > 0 else settings.voice_max_duration_s
    return round(seconds / 60 * settings.stt_usd_per_minute, 6)


def is_unclear(text: str, confidence: float | None, min_confidence: float) -> bool:
    """Silence, noise, sound tags or only fillers; or confidence under the threshold when set."""

    words = [word.lower() for word in _WORD.findall(_TAGS.sub(" ", text or ""))]
    if not words or all(word in _FILLERS for word in words):
        return True
    return min_confidence > 0 and confidence is not None and confidence < min_confidence


class VoiceTranscriber:
    def __init__(self, session_factory, gateway, settings) -> None:
        self.session_factory = session_factory
        self.gateway = gateway
        self.settings = settings

    async def transcribe(self, event: InboundEvent, connection, provider_name: str, provider, last_attempt: bool) -> VoiceOutcome:
        """Transcript or a notice. Raises ProviderTransientError when a later attempt may work."""

        data = dict(event.data)
        if data.get("transcribed"):
            # The job ran before and crashed after paying for this: use what was saved.
            return self._outcome(event.text or "", data.get("stt_language"), data.get("stt_confidence"), float(data.get("stt_cost_usd") or 0))
        if data.get("stt_error"):
            return VoiceOutcome(VoiceNotice.failed, error_code=str(data["stt_error"]))
        content: bytes | None = None
        try:
            content = await self.gateway.download_file(connection, str(data.get("file_id") or ""), DOWNLOAD_LIMIT_BYTES)
            transcript = await provider.transcribe(
                AudioInput(audio_id=str(event.id), content=content, mime_type=str(data.get("mime_type") or "audio/ogg"))
            )
        except ChannelError as exc:
            if exc.retryable and not last_attempt:
                raise ProviderTransientError(f"voice_download_{exc.code}") from None
            return await self._failed(event, data, f"download_{exc.code}"[:48])
        except ProviderTransientError as exc:
            if not last_attempt:
                raise
            return await self._failed(event, data, _code(exc))
        except ProviderUnavailable as exc:
            return await self._failed(event, data, _code(exc))
        finally:
            content = None
        seconds = transcript.duration_s if transcript.duration_s is not None else float(data.get("duration") or 0)
        cost = round(seconds / 60 * self.settings.stt_usd_per_minute, 6)
        text, _ = clip_inbound(transcript.text)
        data.update(
            transcribed=True,
            stt_provider=provider_name,
            stt_language=transcript.language,
            stt_confidence=transcript.confidence,
            stt_seconds=round(seconds, 2),
            stt_cost_usd=cost,
            stt_cost_version=self.settings.stt_cost_version,
        )
        await self._save(event, text, data)
        logger.info(
            "voice_transcribed",
            extra={"inbound_event_id": str(event.id), "duration_s": round(seconds, 2), "stt_provider": provider_name},
        )
        event.text, event.data = text, data
        return self._outcome(text, transcript.language, transcript.confidence, cost)

    def _outcome(self, text: str, language, confidence, cost: float) -> VoiceOutcome:
        confidence = float(confidence) if isinstance(confidence, (int, float)) else None
        if is_unclear(text, confidence, self.settings.stt_min_confidence):
            return VoiceOutcome(VoiceNotice.unclear, language=language, confidence=confidence, cost_usd=cost)
        return VoiceOutcome("text", text=text, language=language, confidence=confidence, cost_usd=cost)

    async def _failed(self, event: InboundEvent, data: dict, code: str) -> VoiceOutcome:
        data["stt_error"] = code
        await self._save(event, None, data)
        logger.warning("voice_not_transcribed", extra={"inbound_event_id": str(event.id), "error_code": code})
        event.data = data
        return VoiceOutcome(VoiceNotice.failed, error_code=code)

    async def _save(self, event: InboundEvent, text: str | None, data: dict) -> None:
        async with self.session_factory() as own:
            await InboundEventRepository(own).save_voice_result(event.id, text, data)
            await own.commit()


def _code(exc: Exception) -> str:
    """A short code from our own exception text ("stt_http_401"), never a provider message."""

    raw = str(exc).strip().split(" ")[0] if str(exc).strip() else type(exc).__name__
    return re.sub(r"[^a-z0-9_]", "", raw.lower())[:48] or type(exc).__name__.lower()
