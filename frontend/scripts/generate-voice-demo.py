"""Build fictional call samples; run with Piper installed and FFmpeg on PATH.

Russian: CC0 Denis Piper voice in work/voice-demo.
English WAV utterances: Windows SAPI David/Zira, generated beforehand.
Only MP3 files and timestamped transcripts ship to the browser.
"""
import json
from pathlib import Path
import subprocess
import wave

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "work/voice-demo"
OUTPUT = ROOT / "frontend/public/audio/voice-demo"
SCRIPT = json.loads((Path(__file__).parent / "voice-demo.json").read_text(encoding="utf-8"))


def build():
    from piper import PiperVoice, SynthesisConfig
    voice = PiperVoice.load(str(WORK / "ru_RU-denis-medium.onnx"))
    OUTPUT.mkdir(parents=True, exist_ok=True)
    result = {}
    for locale, lines in SCRIPT.items():
        clips = []
        cues = []
        cursor = 0.0
        for index, line in enumerate(lines):
            raw = WORK / f"{locale}-{index}.wav"
            if locale == "ru":
                with wave.open(str(raw), "wb") as stream:
                    voice.synthesize_wav(line["text"], stream, syn_config=SynthesisConfig(length_scale=1.03 if line["speaker"] == "plumo" else 0.96))
            clip = WORK / f"{locale}-{index}-ready.wav"
            # Normalize formats and leave a short conversational pause.
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(raw), "-af", "loudnorm=I=-18:TP=-2:LRA=7,apad=pad_dur=0.55", "-ar", "24000", "-ac", "1", str(clip)], check=True)
            with wave.open(str(clip), "rb") as stream:
                duration = stream.getnframes() / stream.getframerate()
            cues.append({**line, "start": round(cursor, 3), "end": round(cursor + duration, 3)})
            cursor += duration
            clips.append(clip)
        manifest = WORK / f"{locale}-concat.txt"
        manifest.write_text("\n".join(f"file '{clip.as_posix()}'" for clip in clips), encoding="utf-8")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(manifest), "-codec:a", "libmp3lame", "-b:a", "96k", str(OUTPUT / f"{locale}.mp3")], check=True)
        result[locale] = {"duration": round(cursor, 3), "cues": cues}
    (ROOT / "frontend/src/components/landing/voice-demo-data.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print({locale: sample["duration"] for locale, sample in result.items()})


if __name__ == "__main__":
    build()
