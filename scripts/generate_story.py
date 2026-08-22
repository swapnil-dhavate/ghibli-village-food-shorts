"""Call the Gemini free-tier API to write today's scene-by-scene story + prompts.

Requires env var GEMINI_API_KEY (from https://aistudio.google.com/apikey).
Model name is overridable via GEMINI_MODEL since Google renames/retires free-tier
models over time -- check https://ai.google.dev/gemini-api/docs/models if this 404s.
"""

import json
import os
import time
from pathlib import Path

import requests

from constants import ART_STYLE, CHARACTER_BIBLE, ENVIRONMENT_RULES, KNOWN_AUDIO_TAGS, NEGATIVE_PROMPT

ROOT = Path(__file__).resolve().parent.parent
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
)

RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "video_title": {"type": "STRING"},
        "video_description": {"type": "STRING"},
        "tags": {"type": "ARRAY", "items": {"type": "STRING"}},
        "scenes": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "scene_number": {"type": "INTEGER"},
                    "act": {"type": "STRING"},
                    "title": {"type": "STRING"},
                    "character_actions": {"type": "STRING"},
                    "image_prompt": {"type": "STRING"},
                    "camera_motion": {
                        "type": "STRING",
                        "enum": ["static", "push_in", "pull_out", "pan_left", "pan_right", "tilt_up", "tilt_down"],
                    },
                    "audio_tags": {"type": "ARRAY", "items": {"type": "STRING", "enum": KNOWN_AUDIO_TAGS}},
                },
                "required": ["scene_number", "act", "title", "character_actions", "image_prompt", "camera_motion", "audio_tags"],
            },
        },
    },
    "required": ["video_title", "video_description", "tags", "scenes"],
}


def build_prompt(dish, scene_count):
    return f"""You are a cinematic director writing a wordless, ASMR-style Studio Ghibli \
animated YouTube Short about traditional Indian village food, vertical 9:16, no dialogue, \
no narration, no on-screen text.

DISH: {dish['name']} ({dish['region']})
WEATHER (keep identical across all scenes): {dish['weather']}

CHARACTER BIBLE (use this exact family in every image_prompt, described in full each time):
{CHARACTER_BIBLE}

ART STYLE (include in every image_prompt): {ART_STYLE}

ENVIRONMENT RULES (must hold in every scene): {ENVIRONMENT_RULES}

Write exactly {scene_count} scenes covering, in order: harvesting/gathering the ingredients,
traditional cooking over a clay stove, and the family serving and eating together with warm
emotional expressions. Each image_prompt must be a fully independent, self-contained prompt
(never say "same as previous scene") that restates the relevant characters, the weather, the
art style, and the food/cooking details for that moment, plus a camera angle. character_actions
must describe only visual actions (no dialogue). audio_tags must be chosen from the allowed
enum and should match what's happening in that scene (e.g. chopping while cutting vegetables,
oil_sizzling while frying). camera_motion should vary across scenes rather than repeating the
same one every time.

Also write a YouTube Shorts video_title (include the dish name and the word Shorts or #Shorts),
a short video_description (1-3 sentences, no dialogue quoted, mention it's a wordless ASMR
animated short), and 8-12 relevant tags.
"""


def generate_story(dish, scene_count, max_retries=3):
    api_key = os.environ["GEMINI_API_KEY"]
    payload = {
        "contents": [{"parts": [{"text": build_prompt(dish, scene_count)}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": RESPONSE_SCHEMA,
            "temperature": 1.0,
        },
    }

    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(
                GEMINI_URL,
                params={"key": api_key},
                json=payload,
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            story = json.loads(text)
            for scene in story["scenes"]:
                scene["negative_prompt"] = NEGATIVE_PROMPT
            return story
        except Exception as exc:  # noqa: BLE001 - broad on purpose, we retry then re-raise
            last_error = exc
            time.sleep(5 * attempt)

    raise RuntimeError(f"Gemini story generation failed after {max_retries} attempts: {last_error}")


if __name__ == "__main__":
    import sys

    dish = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")) if len(sys.argv) > 1 else json.loads(sys.stdin.read())
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    story = generate_story(dish, config["scene_count"])
    json.dump(story, sys.stdout, indent=2)
