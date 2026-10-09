"""Live check of ElevenLabs speech for phone calls: TTS → phone line → Scribe STT.

    python -m app.voice_probe                      # built-in ru / ky / mixed phrases
    python -m app.voice_probe --tts eleven_v4_turbo --stt scribe_v2
    python -m app.voice_probe --audio-dir recordings/   # your own calls, with <name>.txt references

What it measures, per phrase and TTS model:

- TTS time to first audio byte and total, synthesized straight into the phone
  format (G.711 μ-law 8 kHz), so STT hears what a SIP line carries;
- STT latency, detected language and its probability, confidence
  (geometric mean of word probabilities from Scribe `logprob`);
- WER against the reference text and whether key entities (prices, streets,
  days) survived — WER alone hides a misheard price.

Synthetic speech is clean and well articulated: its WER is a lower bound. The
product decision on Kyrgyz voice needs real recordings (`--audio-dir`) checked
by a native speaker. Listen to the saved WAVs before trusting Kyrgyz TTS.

Uses ELEVENLABS_API_KEY from backend/.env. Spends credits: the character count
is printed before anything is sent. Runs outside the core, like elevenlabs_setup.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import math
import os
import re
import sys
import time
import wave
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

import httpx
from dotenv import load_dotenv

API = "https://api.elevenlabs.io"
DEFAULT_VOICE = "EXAVITQu4vr4xnSDxMaL"  # premade "Sarah"; set ELEVENLABS_VOICE_ID for the agent's voice
DEFAULT_TTS = ("eleven_flash_v2_5", "eleven_v3_conversational", "eleven_v4_turbo")
DEFAULT_STT = "scribe_v2"


@dataclass(slots=True)
class Phrase:
    key: str
    language: str  # ru | ky | mixed
    text: str
    entities: tuple[str, ...]


# Fictional demo data. Kyrgyz lines need a native speaker's check.
PHRASES = (
    Phrase(
        "ru_agent",
        "ru",
        "Да, квартира на Чуй ещё продаётся: две комнаты, 58 квадратных метров, 85 000 долларов. Когда вам удобно посмотреть?",
        ("чуй", "58", "85000"),
    ),
    Phrase(
        "ru_caller",
        "ru",
        "Здравствуйте, а на Киевской трёхкомнатная ещё есть? Можно в субботу в 11 посмотреть?",
        ("киевской", "субботу", "11"),
    ),
    Phrase(
        "ky_agent",
        "ky",
        "Ооба, Чүй проспектиндеги эки бөлмөлүү батир дагы эле сатылууда, баасы 85 000 доллар. Качан көрүүгө ыңгайлуу?",
        ("чүй", "85000"),
    ),
    Phrase(
        "ky_caller",
        "ky",
        "Эртең саат үчтө Филармониянын жанындагы батирди көрсөм болобу?",
        ("эртең", "филармония"),
    ),
    Phrase(
        "mixed_caller",
        "mixed",
        "Саламатсызбы, мага эки комнатный квартира керек, бюджет 90 000 долларга чейин, рассрочка барбы?",
        ("90000", "рассрочка"),
    ),
)


@dataclass(slots=True)
class Result:
    phrase: str
    language: str
    source: str  # TTS model id or "file"
    stt_model: str
    stt_language_hint: str | None
    reference: str
    transcript: str = ""
    wer: float | None = None
    entities_found: list[str] = field(default_factory=list)
    entities_missed: list[str] = field(default_factory=list)
    detected_language: str | None = None
    language_probability: float | None = None
    confidence: float | None = None
    tts_first_byte_ms: int | None = None
    tts_total_ms: int | None = None
    stt_ms: int | None = None
    audio_s: float | None = None
    wav: str | None = None
    error: str | None = None


# --- audio ----------------------------------------------------------------


def ulaw_to_pcm16(data: bytes) -> bytes:
    """G.711 μ-law → 16-bit little-endian PCM. `audioop` is gone since Python 3.13."""

    out = bytearray()
    for byte in data:
        value = ~byte & 0xFF
        sign = value & 0x80
        exponent = (value >> 4) & 0x07
        mantissa = value & 0x0F
        sample = (((mantissa << 3) + 0x84) << exponent) - 0x84
        out += (-sample if sign else sample).to_bytes(2, "little", signed=True)
    return bytes(out)


def wav_bytes(pcm16: bytes, rate: int = 8000) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(pcm16)
    return buffer.getvalue()


# --- scoring --------------------------------------------------------------

_DIGIT_GROUPS = re.compile(r"(?<=\d)[\s  ,.](?=\d{3}\b)")
_NON_WORD = re.compile(r"[^\w\s]+")


def normalize(text: str) -> list[str]:
    """Lowercase, ё→е, "85 000" → "85000", no punctuation. Same rules for reference and hypothesis."""

    text = text.lower().replace("ё", "е")
    text = _DIGIT_GROUPS.sub("", text)
    text = _NON_WORD.sub(" ", text)
    return text.split()


def wer(reference: str, hypothesis: str) -> float:
    ref, hyp = normalize(reference), normalize(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0
    previous = list(range(len(hyp) + 1))
    for i, word in enumerate(ref, start=1):
        current = [i] + [0] * len(hyp)
        for j, other in enumerate(hyp, start=1):
            current[j] = min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (word != other))
        previous = current
    return round(previous[-1] / len(ref), 3)


def entity_hits(entities: tuple[str, ...], hypothesis: str) -> tuple[list[str], list[str]]:
    joined = " ".join(normalize(hypothesis))
    found = [item for item in entities if " ".join(normalize(item)) in joined]
    return found, [item for item in entities if item not in found]


def confidence(words: list[dict]) -> float | None:
    """Geometric mean of word probabilities from Scribe `logprob` (≤ 0)."""

    logprobs = [float(item["logprob"]) for item in words if item.get("type") == "word" and isinstance(item.get("logprob"), (int, float))]
    if not logprobs:
        return None
    return round(math.exp(sum(logprobs) / len(logprobs)), 3)


# --- ElevenLabs -----------------------------------------------------------


class ElevenLabs:
    def __init__(self, key: str) -> None:
        self.client = httpx.AsyncClient(base_url=API, headers={"xi-api-key": key}, timeout=60.0)

    async def models(self) -> list[dict]:
        response = await self.client.get("/v1/models")
        response.raise_for_status()
        return response.json()

    async def tts_phone(self, text: str, model: str, voice: str, language: str | None) -> tuple[bytes, int, int]:
        """μ-law 8 kHz audio, time to first byte and total, ms."""

        body: dict = {"text": text, "model_id": model}
        if language in ("ru", "ky"):
            body["language_code"] = language
        for attempt in (0, 1):
            started = time.perf_counter()
            first: int | None = None
            chunks = bytearray()
            async with self.client.stream(
                "POST", f"/v1/text-to-speech/{voice}/stream", params={"output_format": "ulaw_8000"}, json=body
            ) as response:
                if response.status_code == 400 and attempt == 0 and "language_code" in body:
                    await response.aread()
                    body.pop("language_code")  # some models pick the language from the text only
                    continue
                if response.status_code != 200:
                    raise RuntimeError(f"TTS {model}: HTTP {response.status_code} {(await response.aread())[:200]!r}")
                async for chunk in response.aiter_bytes():
                    if first is None and chunk:
                        first = int((time.perf_counter() - started) * 1000)
                    chunks += chunk
            return bytes(chunks), first or 0, int((time.perf_counter() - started) * 1000)
        raise RuntimeError(f"TTS {model}: rejected")

    async def stt(self, audio: bytes, filename: str, model: str, language: str | None) -> tuple[dict, int]:
        data = {"model_id": model, "timestamps_granularity": "word", "tag_audio_events": "false"}
        if language:
            data["language_code"] = language
        started = time.perf_counter()
        response = await self.client.post("/v1/speech-to-text", data=data, files={"file": (filename, audio, "audio/wav")})
        elapsed = int((time.perf_counter() - started) * 1000)
        if response.status_code != 200:
            raise RuntimeError(f"STT {model}: HTTP {response.status_code} {response.text[:200]}")
        return response.json(), elapsed

    async def aclose(self) -> None:
        await self.client.aclose()


async def _transcribe(api: ElevenLabs, result: Result, audio: bytes, filename: str, entities: tuple[str, ...]) -> None:
    body, elapsed = await api.stt(audio, filename, result.stt_model, result.stt_language_hint)
    result.stt_ms = elapsed
    result.transcript = str(body.get("text") or "").strip()
    result.detected_language = body.get("language_code")
    probability = body.get("language_probability")
    result.language_probability = round(float(probability), 3) if isinstance(probability, (int, float)) else None
    result.confidence = confidence(body.get("words") or [])
    if result.reference:
        result.wer = wer(result.reference, result.transcript)
        result.entities_found, result.entities_missed = entity_hits(entities, result.transcript)


def _hints(language: str, both: bool) -> list[str | None]:
    """Auto-detect always; also the forced code, as an agent with a fixed language would run."""

    forced = language if language in ("ru", "ky") else None
    return [None, forced] if both and forced else [None]


async def probe_tts(api: ElevenLabs, args, out: Path) -> list[Result]:
    catalog = {item["model_id"]: {lang["language_id"] for lang in item.get("languages") or []} for item in await api.models()}
    results: list[Result] = []
    plan = []
    for model in args.tts:
        if model not in catalog:
            print(f"! {model}: нет в /v1/models этого ключа, пропускаю")
            continue
        for phrase in PHRASES:
            needs = {"ru"} if phrase.language == "ru" else {"ky"}
            if needs - catalog[model]:
                continue
            plan.append((model, phrase))
    chars = sum(len(phrase.text) for _, phrase in plan)
    print(f"TTS: {len(plan)} синтезов, {chars} символов (с учётом множителя модели — меньше). STT: {len(plan)} файлов.")
    if not args.yes and chars > 3000:
        print("Больше 3000 символов: добавьте --yes, если это ожидаемо.")
        return []
    for model, phrase in plan:
        try:
            ulaw, first, total = await api.tts_phone(phrase.text, model, args.voice, phrase.language)
        except (RuntimeError, httpx.HTTPError) as exc:
            results.append(Result(phrase.key, phrase.language, model, args.stt, None, phrase.text, error=str(exc)))
            continue
        audio = wav_bytes(ulaw_to_pcm16(ulaw))
        path = out / f"{model}__{phrase.key}.wav"
        path.write_bytes(audio)
        for hint in _hints(phrase.language, args.forced_language):
            result = Result(
                phrase.key, phrase.language, model, args.stt, hint, phrase.text,
                tts_first_byte_ms=first, tts_total_ms=total, audio_s=round(len(ulaw) / 8000, 2), wav=str(path),
            )
            try:
                await _transcribe(api, result, audio, path.name, phrase.entities)
            except (RuntimeError, httpx.HTTPError) as exc:
                result.error = str(exc)
            results.append(result)
    return results


async def probe_files(api: ElevenLabs, args) -> list[Result]:
    """Own recordings: <name>.wav/.mp3/.ogg/.m4a with an optional <name>.txt reference and <name>.lang (ru/ky/mixed)."""

    folder = Path(args.audio_dir)
    files = sorted(item for item in folder.iterdir() if item.suffix.lower() in (".wav", ".mp3", ".ogg", ".m4a", ".flac"))
    print(f"STT: {len(files)} файлов из {folder}")
    results = []
    for path in files:
        reference_path, lang_path = path.with_suffix(".txt"), path.with_suffix(".lang")
        reference = reference_path.read_text(encoding="utf-8").strip() if reference_path.exists() else ""
        language = lang_path.read_text(encoding="utf-8").strip() if lang_path.exists() else "unknown"
        for hint in _hints(language, args.forced_language):
            result = Result(path.stem, language, "file", args.stt, hint, reference, wav=str(path))
            try:
                await _transcribe(api, result, path.read_bytes(), path.name, ())
            except (RuntimeError, httpx.HTTPError) as exc:
                result.error = str(exc)
            results.append(result)
    return results


def summarize(results: list[Result]) -> list[dict]:
    """Mean WER, entity recall and latency per source × language × hint."""

    groups: dict[tuple, list[Result]] = {}
    for item in results:
        if item.error is None:
            groups.setdefault((item.source, item.language, item.stt_language_hint or "auto"), []).append(item)
    rows = []
    for (source, language, hint), items in sorted(groups.items()):
        scored = [item for item in items if item.wer is not None]
        found = sum(len(item.entities_found) for item in items)
        total = found + sum(len(item.entities_missed) for item in items)
        rows.append(
            {
                "source": source,
                "language": language,
                "stt_hint": hint,
                "n": len(items),
                "wer": round(sum(item.wer for item in scored) / len(scored), 3) if scored else None,
                "entities": f"{found}/{total}" if total else "-",
                "confidence": _mean([item.confidence for item in items]),
                "tts_first_byte_ms": _mean([item.tts_first_byte_ms for item in items]),
                "stt_ms": _mean([item.stt_ms for item in items]),
            }
        )
    return rows


def _mean(values: list) -> float | None:
    numbers = [value for value in values if isinstance(value, (int, float))]
    return round(sum(numbers) / len(numbers), 3) if numbers else None


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Проверка ElevenLabs TTS/STT в телефонном качестве")
    parser.add_argument("--tts", nargs="+", default=list(DEFAULT_TTS), help="модели TTS")
    parser.add_argument("--stt", default=DEFAULT_STT, help="модель Scribe")
    parser.add_argument("--voice", default=os.getenv("ELEVENLABS_VOICE_ID") or DEFAULT_VOICE)
    parser.add_argument("--audio-dir", help="папка со своими записями вместо синтеза")
    parser.add_argument("--forced-language", action="store_true", help="дополнительно распознать с заданным языком")
    parser.add_argument("--out", default="work/voice_probe", help="куда сохранить WAV и отчёт (work/ в .gitignore)")
    parser.add_argument("--yes", action="store_true", help="разрешить больше 3000 символов TTS")
    args = parser.parse_args(argv)

    load_dotenv()
    key = os.getenv("ELEVENLABS_API_KEY", "").strip()
    if not key:
        print("ELEVENLABS_API_KEY пуст: положите ключ в backend/.env", file=sys.stderr)
        return 1
    out = Path(args.out) / datetime.now().strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    api = ElevenLabs(key)
    try:
        results = await (probe_files(api, args) if args.audio_dir else probe_tts(api, args, out))
    finally:
        await api.aclose()
    if not results:
        return 1

    for item in results:
        if item.error:
            print(f"✗ {item.source:26} {item.phrase:13} {item.error}")
            continue
        missed = f" пропущено: {', '.join(item.entities_missed)}" if item.entities_missed else ""
        print(
            f"• {item.source:26} {item.phrase:13} hint={item.stt_language_hint or 'auto':4} "
            f"WER={item.wer} lang={item.detected_language}({item.language_probability}) conf={item.confidence} "
            f"tts_ttfb={item.tts_first_byte_ms}ms stt={item.stt_ms}ms{missed}\n    «{item.transcript}»"
        )
    summary = summarize(results)
    print("\nСводка:")
    for row in summary:
        print("  " + "  ".join(f"{key}={value}" for key, value in row.items()))
    report = out / "report.json"
    report.write_text(
        json.dumps({"summary": summary, "results": [asdict(item) for item in results]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nОтчёт и WAV: {out}")
    return 0 if all(item.error is None for item in results) else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
