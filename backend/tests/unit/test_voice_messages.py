"""Telegram voice messages without a database: parsing, the STT adapter, the mock guard, ops status, prompt."""

import json
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest

from app.application.services.voice_messages import is_unclear, stt_estimate_usd, too_long
from app.config import Settings
from app.domain.errors import ProviderTransientError, ProviderUnavailable
from app.domain.models import AudioInput, Business, Customer, InboundEvent
from app.infrastructure.ai.elevenlabs_stt import ElevenLabsSTTProvider
from app.infrastructure.ai.factory import AIProviderFactory
from app.infrastructure.ai.openrouter_llm import system_parts
from app.infrastructure.channels.base import ChannelError
from app.infrastructure.channels.telegram import TelegramClient, parse_update
from app.release import config_status

TOKEN = "123456789:AAH-secret_part_of_the_token_xyz"


def _update(**message) -> dict:
    return {
        "update_id": 7001,
        "message": {
            "message_id": 3,
            "date": 1760000000,
            "chat": {"id": 555, "type": "private"},
            "from": {"id": 555, "is_bot": False, "first_name": "Айгуль"},
            **message,
        },
    }


def test_voice_and_audio_files_become_voice_events_with_references_only() -> None:
    voice = {"file_id": "AwACAg", "file_unique_id": "AgAD", "duration": 7, "mime_type": "audio/ogg", "file_size": 12345}
    event = parse_update(_update(voice=voice, caption="подпись"))
    assert event.kind == "voice" and event.text == "[voice]" and event.chat_id == "555"
    assert event.data == {**voice, "chat_id": "555", "contact_name": "Айгуль"}

    audio = parse_update(_update(audio={"file_id": "CQAC", "duration": 30, "mime_type": "audio/mpeg", "title": "x"}))
    assert audio.kind == "voice" and audio.data["file_id"] == "CQAC" and "title" not in audio.data
    # An audio attachment that is not audio by its MIME type stays unsupported.
    odd = parse_update(_update(audio={"file_id": "CQAD", "duration": 3, "mime_type": "application/octet-stream"}))
    assert odd.kind == "unsupported"


@pytest.mark.parametrize("media", ["photo", "video", "video_note", "sticker", "document", "animation"])
def test_other_media_stay_unsupported(media) -> None:
    event = parse_update(_update(**{media: {"file_id": "x"} if media != "photo" else [{"file_id": "x"}]}))
    assert event.kind == "unsupported" and event.data["unsupported"] == media and "file_id" not in event.data


async def test_download_keeps_the_token_out_of_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/getFile"):
            return httpx.Response(200, json={"ok": True, "result": {"file_id": "f", "file_unique_id": "u", "file_size": 4, "file_path": "voice/f.oga"}})
        assert request.url.path == f"/file/bot{TOKEN}/voice/f.oga"
        return httpx.Response(200, content=b"OggS")

    client = TelegramClient(TOKEN, transport=httpx.MockTransport(handler))
    assert await client.download_file("f") == b"OggS"
    with pytest.raises(ChannelError) as too_big:
        await client.download_file("f", max_bytes=2)
    assert too_big.value.code == "file_too_big" and TOKEN not in str(too_big.value)

    def broken(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/getFile"):
            return httpx.Response(200, json={"ok": True, "result": {"file_path": "voice/f.oga"}})
        raise httpx.ConnectError(f"cannot reach {request.url}")

    failing = TelegramClient(TOKEN, transport=httpx.MockTransport(broken))
    with pytest.raises(ChannelError) as network:
        await failing.download_file("f")
    assert network.value.retryable and TOKEN not in str(network.value) and "secret_part" not in repr(network.value)
    await client.aclose()
    await failing.aclose()


async def test_elevenlabs_request_and_transcript() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"], seen["headers"], seen["body"] = str(request.url), request.headers, request.read()
        return httpx.Response(200, json={
            "language_code": "kir", "language_probability": 0.9, "text": "  Саламатсызбы,   баасы канча? ",
            "words": [{"text": "Саламатсызбы", "type": "word", "logprob": -0.1}, {"text": " ", "type": "spacing", "logprob": -9},
                      {"text": "баасы", "type": "word", "logprob": -0.3}],
            "audio_duration_secs": 3.5,
        })

    provider = ElevenLabsSTTProvider(api_key="el-key", transport=httpx.MockTransport(handler))
    result = await provider.transcribe(AudioInput("e1", content=b"OggS-bytes", mime_type="audio/ogg"))
    assert result.text == "Саламатсызбы, баасы канча?" and result.language == "ky" and result.duration_s == 3.5
    assert 0.8 < result.confidence < 0.85  # mean of e^-0.1 and e^-0.3; spacing is not a word
    assert seen["url"] == "https://api.elevenlabs.io/v1/speech-to-text"
    assert seen["headers"]["xi-api-key"] == "el-key"
    assert b'name="model_id"\r\n\r\nscribe_v2' in seen["body"] and b"OggS-bytes" in seen["body"]
    assert b'filename="voice.ogg"' in seen["body"] and b"enable_logging" not in seen["body"]
    await provider.aclose()

    private = ElevenLabsSTTProvider(api_key="el-key", zero_retention=True, transport=httpx.MockTransport(handler))
    await private.transcribe(AudioInput("e2", content=b"x"))
    assert seen["url"].endswith("?enable_logging=false")
    await private.aclose()


@pytest.mark.parametrize(("status", "error"), [(429, ProviderTransientError), (503, ProviderTransientError), (401, ProviderUnavailable), (422, ProviderUnavailable)])
async def test_elevenlabs_errors_are_transient_or_permanent(status, error) -> None:
    provider = ElevenLabsSTTProvider(api_key="el-key", transport=httpx.MockTransport(lambda request: httpx.Response(status, json={"detail": "x"})))
    with pytest.raises(error) as raised:
        await provider.transcribe(AudioInput("e", content=b"x"))
    assert type(raised.value) is error and str(raised.value) == f"stt_http_{status}"
    await provider.aclose()
    with pytest.raises(ProviderUnavailable):
        await ElevenLabsSTTProvider(api_key="").transcribe(AudioInput("e", content=b"x"))


def test_the_mock_never_transcribes_a_chat_voice_message() -> None:
    def factory(**values) -> AIProviderFactory:
        return AIProviderFactory(Settings(**{"ai_mode": "production", "voice_messages_enabled": True, "stt_provider": "real", **values}))

    real = object()
    on = factory()
    on.register_stt("real", real)
    assert on.voice_message_stt() == ("real", real)
    assert factory(voice_messages_enabled=False).voice_message_stt() is None
    assert factory(stt_provider="mock").voice_message_stt() is None
    assert factory().voice_message_stt() is None  # named but not registered
    mock_mode = factory(ai_mode="mock")
    mock_mode.register_stt("real", real)
    assert mock_mode.voice_message_stt() is None
    renamed = factory()
    renamed.register_stt("real", renamed._stt["mock"])  # the mock under another name
    assert renamed.voice_message_stt() is None


def test_ops_status_names_a_mock_stt_only_when_voice_is_on(monkeypatch) -> None:
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    base = dict(app_env="stand", ai_mode="production", big_model_provider="openrouter", handoff_provider="telegram")
    assert "stt_mock" not in config_status(Settings(**base))["problems"]
    assert "stt_mock" in config_status(Settings(**base, voice_messages_enabled=True))["problems"]
    live = config_status(Settings(**base, voice_messages_enabled=True, stt_provider="elevenlabs"))
    assert "stt_mock" not in live["problems"] and "missing:ELEVENLABS_API_KEY" in live["problems"]
    assert live["stt_provider"] == "elevenlabs"


def test_unclear_transcripts_and_limits() -> None:
    assert is_unclear("", None, 0) and is_unclear("(шум) ...", None, 0) and is_unclear("Э-э, ммм", 0.9, 0)
    assert not is_unclear("да", None, 0) and not is_unclear("Ага, 85000", None, 0)
    assert is_unclear("Квартира есть?", 0.2, 0.5) and not is_unclear("Квартира есть?", 0.2, 0)

    def event(**data) -> InboundEvent:
        return InboundEvent(uuid4(), uuid4(), uuid4(), "telegram", "1", "voice", "queued", datetime.now(UTC), data=data)

    assert too_long(event(duration=121), 120) and not too_long(event(duration=120), 120)
    assert too_long(event(duration=5, file_size=21 * 1024 * 1024), 120)
    settings = Settings(stt_usd_per_minute=0.006, voice_max_duration_s=120)
    assert stt_estimate_usd(event(duration=30), settings) == 0.003
    assert stt_estimate_usd(event(), settings) == 0.012  # unknown duration: the limit


def test_the_model_is_told_the_message_was_a_voice_transcript() -> None:
    from app.application.services.context_builder import ContextBuilder

    now = datetime.now(UTC)
    business = Business(uuid4(), "Demo Realty", "", "", {}, "", now, now)
    customer = Customer(uuid4(), None, "ru", "new", None, None, None, now, now, business_id=business.id)
    context = ContextBuilder().build(business=business, knowledge=[], customer=customer, summary=None,
                                     recent_messages=[], current_message="85000", language="ru", channel="telegram")
    assert "Голосовое сообщение" not in json.dumps(system_parts(context), ensure_ascii=False)
    context.voice_message = True
    stable, turn = system_parts(context)
    assert "Голосовое сообщение" in turn and "повтори" in turn and "Голосовое" not in stable
