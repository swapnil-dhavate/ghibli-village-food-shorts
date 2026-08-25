"""Synthesize per-scene narration audio via Piper TTS.

Piper is free, open-source, and runs entirely offline/on-CPU inside the pipeline itself --
no API key, no account, no per-request cost, no rate limit (verified directly: ~11s wall
time for a 7s clip on ordinary CPU, most of which is one-time model load). This is what
makes "FREE TTS" in the new architecture actually free rather than gated like every hosted
TTS API turned out to be (see generate_images.py's kontext notes for that same pattern).

The voice model (assets/voices/en_US-lessac-medium.onnx + .json) is committed to the repo
so runs don't depend on Hugging Face being reachable every single day.
"""

import json
import sys
import wave
from pathlib import Path

from piper import PiperVoice

ROOT = Path(__file__).resolve().parent.parent
VOICE_MODEL = ROOT / "assets" / "voices" / "en_US-lessac-medium.onnx"
VOICE_CONFIG = ROOT / "assets" / "voices" / "en_US-lessac-medium.onnx.json"

_voice = None


def _get_voice():
    # Loaded once and reused across scenes -- model load dominates wall time, per-call
    # synthesis is fast once it's warm.
    global _voice
    if _voice is None:
        _voice = PiperVoice.load(str(VOICE_MODEL), str(VOICE_CONFIG))
    return _voice


def synthesize_scene_audio(text, out_path):
    voice = _get_voice()
    with wave.open(str(out_path), "wb") as wav_file:
        voice.synthesize_wav(text, wav_file)
    with wave.open(str(out_path), "rb") as wav_file:
        duration = wav_file.getnframes() / wav_file.getframerate()
    return duration


def generate_all_voice(story, output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    for scene in story["scenes"]:
        n = scene["scene_number"]
        out_path = output_dir / f"scene_{n:02d}_narration.wav"
        duration = synthesize_scene_audio(scene["narration_text"], out_path)
        scene["voice_path"] = str(out_path)
        scene["voice_duration"] = duration
    return story


if __name__ == "__main__":
    story_path, output_dir_arg = sys.argv[1], sys.argv[2]
    story = json.loads(Path(story_path).read_text(encoding="utf-8"))
    output_dir = Path(output_dir_arg)
    story = generate_all_voice(story, output_dir)
    json.dump(story, sys.stdout, indent=2)
