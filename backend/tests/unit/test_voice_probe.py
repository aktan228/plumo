"""Scoring and audio helpers of the ElevenLabs probe. No network."""

import io
import wave

from app.voice_probe import confidence, entity_hits, ulaw_to_pcm16, wav_bytes, wer


def test_ulaw_decodes_silence_and_extremes() -> None:
    pcm = ulaw_to_pcm16(bytes([0xFF, 0x7F, 0x00, 0x80]))
    samples = [int.from_bytes(pcm[i : i + 2], "little", signed=True) for i in range(0, len(pcm), 2)]
    assert samples[0] == 0 and samples[1] == 0
    assert samples[2] == -32124 and samples[3] == 32124


def test_wav_is_8khz_mono_16bit() -> None:
    with wave.open(io.BytesIO(wav_bytes(b"\x00\x00" * 800))) as wav:
        assert (wav.getframerate(), wav.getnchannels(), wav.getsampwidth(), wav.getnframes()) == (8000, 1, 2, 800)


def test_wer_ignores_case_punctuation_and_digit_grouping() -> None:
    assert wer("Цена 85 000 долларов.", "цена 85000 долларов") == 0.0
    assert wer("эки бөлмөлүү батир", "эки бөлмө батир") == round(1 / 3, 3)
    assert wer("Ещё есть?", "еще есть") == 0.0


def test_entities_survive_or_not() -> None:
    found, missed = entity_hits(("85000", "чүй"), "Чүй проспектинде баасы восемьдесят пять тысяч")
    assert found == ["чүй"] and missed == ["85000"]


def test_confidence_is_geometric_mean_of_word_probabilities() -> None:
    words = [
        {"type": "word", "logprob": 0.0},
        {"type": "spacing", "logprob": -9.0},
        {"type": "word", "logprob": -0.6931471805599453},
    ]
    assert confidence(words) == round(0.5**0.5, 3)
    assert confidence([]) is None
