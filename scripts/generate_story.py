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
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")
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

FULL CHARACTER BIBLE (for your own reference -- do NOT restate all of this in every
image_prompt, see rules below):
{CHARACTER_BIBLE}

ART STYLE (for your own reference): {ART_STYLE}

ENVIRONMENT RULES (must hold in every scene): {ENVIRONMENT_RULES}

Write exactly {scene_count} scenes covering, in order: harvesting/gathering the ingredients,
traditional cooking over a clay stove, and the family serving and eating together with warm
emotional expressions. character_actions must describe only visual actions (no dialogue).
audio_tags must be chosen from the allowed enum and should match what's happening in that
scene (e.g. chopping while cutting vegetables, oil_sizzling while frying). camera_motion
should vary across scenes rather than repeating the same one every time.

CRITICAL image_prompt RULES -- the image generator only reliably renders roughly the first
250-300 characters of a prompt, so every image_prompt MUST:
1. Be a single flowing sentence of AT MOST 320 characters total.
2. Start with the style anchor "Flat 2D children's book illustration style, warm colors,"
   followed IMMEDIATELY by the subject and action (who is doing what) -- never open with
   atmosphere/lighting/scenery. (Testing showed this anchor renders far more reliably than
   "Studio Ghibli anime style" on the free image backend, which tends to drift into
   photorealistic/3D-render looks instead -- do not change this anchor without re-testing.)
3. Mention ONLY 1-2 characters actually doing something in that specific scene, INCLUDING
   the final scene -- never describe the whole 5-person family in one image_prompt, even
   though the scene conceptually is a family meal. Pick the 2 most relevant family members
   for the final image_prompt (e.g. "a father and his young daughter sharing food together");
   character_actions can still describe the full family in prose for flavor/audio purposes,
   that's fine, just not in image_prompt. Describe each character in no more than 6-8 words
   (e.g. "a 35-year-old Indian father in a cotton dhoti" not the full character bible entry).
4. Prefer simple, common, single-step actions the image generator has actually seen a lot of
   (kneading dough, stirring a pot, pouring water, serving food, eating, smiling at each
   other) over rare/specific compound actions (e.g. avoid "rotating a stone mill while
   someone else pours grain into it" -- pick one simple visual moment from that instead, like
   "grinding grain with a stone mill"). Simpler single-action prompts render far more reliably
   than multi-step or unusual-tool ones on this free image backend.
5. End with at most one short clause for weather/setting (e.g. "in a rainy mud-house
   courtyard") -- do not list camera angle, negative prompts, or long style adjective lists.
Every image_prompt must still be fully independent (never say "same as previous scene").

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
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(5 * attempt)

    raise RuntimeError(f"Gemini story generation failed after {max_retries} attempts: {last_error}")


if __name__ == "__main__":
    import sys

    dish = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")) if len(sys.argv) > 1 else json.loads(sys.stdin.read())
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    story = generate_story(dish, config["scene_count"])
    json.dump(story, sys.stdout, indent=2)
