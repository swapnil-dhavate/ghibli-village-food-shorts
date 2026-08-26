"""Call the Gemini free-tier API to research and write today's narrated script + scene
breakdown for any general-interest topic (history/science/nature/mystery). Narration/title/
description are written in Hindi (see build_prompt's LANGUAGE section) -- image_prompt and
visual_description stay in English since the free image generator only understands English.

Requires env var GEMINI_API_KEY (from https://aistudio.google.com/apikey).
Model name is overridable via GEMINI_MODEL since Google renames/retires free-tier
models over time -- check https://ai.google.dev/gemini-api/docs/models if this 404s.

Replaces generate_story.py: the old version wrote a wordless ASMR script for a fixed food/
character-bible format. This version writes an actually-narrated script (narration_text per
scene, spoken via Piper TTS in generate_voice.py) for whatever topic pick_topic.py picks --
"research" here means relying on Gemini's own training-time knowledge of the topic, there is
no external search tool wired up.
"""

import json
import os
import time
from pathlib import Path

import requests

from constants import ART_STYLE, KNOWN_AUDIO_TAGS, MUSIC_MOODS, NEGATIVE_PROMPT

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
        "music_mood": {"type": "STRING", "enum": MUSIC_MOODS},
        "scenes": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "scene_number": {"type": "INTEGER"},
                    "title": {"type": "STRING"},
                    "narration_text": {"type": "STRING"},
                    "visual_description": {"type": "STRING"},
                    "image_prompt": {"type": "STRING"},
                    "camera_motion": {
                        "type": "STRING",
                        "enum": ["static", "push_in", "pull_out", "pan_left", "pan_right", "tilt_up", "tilt_down"],
                    },
                    "audio_tags": {"type": "ARRAY", "items": {"type": "STRING", "enum": KNOWN_AUDIO_TAGS}},
                },
                "required": [
                    "scene_number", "title", "narration_text", "visual_description",
                    "image_prompt", "camera_motion", "audio_tags",
                ],
            },
        },
    },
    "required": ["video_title", "video_description", "tags", "music_mood", "scenes"],
}


def build_prompt(topic, scene_count):
    return f"""You are a scriptwriter and visual director for a narrated, fact-based YouTube \
Shorts video, vertical 9:16, aimed at a broad Hindi-speaking general audience.

TOPIC: {topic['title']} (category: {topic['category']})

LANGUAGE: narration_text, video_title, and video_description MUST be written in natural,
fluent, conversational HINDI using Devanagari script -- the way a real Hindi speaker would
actually talk, NOT a stiff word-for-word translation from English. This text is spoken aloud
by a Hindi text-to-speech voice and shown as on-screen Hindi captions, so it must read
naturally out loud. tags should mix Hindi and English terms (English tags help search reach
even on a Hindi video). image_prompt and visual_description MUST stay in ENGLISH regardless
-- the free image generator only reliably understands English prompts, switching those to
Hindi would hurt image quality.

Research this topic using your own knowledge and write an accurate, engaging, hook-first
narrated script. Do not fabricate specific statistics/dates you are not confident about --
prefer well-established facts over invented precision.

ART STYLE (for your own reference, not restated in narration): {ART_STYLE}

Write exactly {scene_count} scenes forming a complete narrated mini-story about this topic:
- Scene 1's NARRATION must open with a surprising fact or a hook question in its first
  sentence -- no slow build-up, the viewer decides whether to keep watching in the first two
  seconds. The hook lives in the words, NOT in the image: scene 1's image_prompt/
  visual_description must still be just as simple and concrete as every other scene (a
  specific person/animal/place doing one simple thing) -- do not reach for a more abstract or
  symbolic visual just because it's the opening scene (e.g. don't try to depict "a prism
  splitting light into a rainbow" or "a question mark over a landscape" -- ground scene 1 in
  a concrete moment from the topic instead, the same way you would any other scene).
- Middle scenes each cover one distinct, accurate fact or step about the topic, in a logical
  order.
- The final scene lands on a satisfying closing thought or the most striking fact, saved
  for last.

For each scene write:
- narration_text: what's actually SPOKEN aloud for this scene, IN HINDI (Devanagari script)
  -- 1-2 complete sentences, roughly 12-25 words, conversational and engaging (not dry/
  academic, not a literal translation). This becomes both the TTS narration audio and the
  on-screen subtitle text, so it must stand alone as natural spoken Hindi prose.
- visual_description: a short plain-prose description of what the image should show for this
  scene, used later to automatically verify the generated image actually matches (can differ
  from narration_text -- narration can reference things the image doesn't literally show).
- image_prompt: the actual image-generation prompt (see CRITICAL rules below).
- camera_motion: one of static/push_in/pull_out/pan_left/pan_right/tilt_up/tilt_down, should
  vary across scenes rather than repeating.
- audio_tags: 1-3 tags from the allowed enum, matching this scene's setting/mood.

CRITICAL image_prompt RULES -- the image generator only reliably renders roughly the first
250-300 characters of a prompt, so every image_prompt MUST:
1. Be a single flowing sentence of AT MOST 320 characters total.
2. Start with the style anchor "Flat 2D children's book illustration style, warm colors,"
   followed IMMEDIATELY by the subject and action -- never open with atmosphere/lighting.
   (Testing showed this anchor renders far more reliably than photorealistic/anime style
   anchors on the free image backend, which tend to drift into garbled looks instead --
   do not change this anchor without re-testing.)
3. Depict ONLY 1-2 concrete visual subjects (a person, an animal, a place, an object) actually
   doing or showing something -- never try to depict an abstract concept directly (e.g. don't
   draw "the passage of time"; draw a specific clock, hourglass, or aging tree instead).
4. Prefer simple, common, single-step scenes the image generator has actually seen a lot of
   over rare or compound scenes (e.g. avoid "a king signing a treaty while soldiers march
   past in the background" -- pick one simple visual moment instead, like "a king signing a
   scroll at a wooden table"). Simpler single-subject prompts render far more reliably than
   busy multi-element ones on this free image backend. In particular, AVOID scenes of someone
   pulling/dragging/hauling a heavy object (a sledge, cart, boat, or block under tension) --
   verified directly that this specific action has a very low render-match rate on this free
   backend, however central it is to the topic. Use a static alternative instead: the object
   already in place being worked on (e.g. "workers lowering a stone block into position with
   ropes" or "a stone block resting on a wooden sledge beside a river"), not the pulling
   motion itself.
5. End with at most one short clause for setting/atmosphere (e.g. "at sunset over stone
   ruins") -- do not list camera angle, negative prompts, or long style adjective lists.
Every image_prompt must still be fully independent (never say "same as previous scene").

Also pick ONE music_mood for the WHOLE video from calm/cozy/upbeat/curious/emotional that best
fits this topic's overall tone (e.g. a mystery topic might suit "curious", a joyful nature
fact might suit "upbeat"), and write a YouTube Shorts video_title IN HINDI (concise, curiosity-
driven; the "#Shorts" hashtag itself can stay in English/Latin script since hashtags aren't
translated), a short video_description IN HINDI (1-3 sentences), and 8-12 tags (mix of Hindi
and English terms).
"""


def generate_script(topic, scene_count, max_retries=3):
    api_key = os.environ["GEMINI_API_KEY"]
    payload = {
        "contents": [{"parts": [{"text": build_prompt(topic, scene_count)}]}],
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
            script = json.loads(text)
            for scene in script["scenes"]:
                scene["negative_prompt"] = NEGATIVE_PROMPT
            return script
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(5 * attempt)

    raise RuntimeError(f"Gemini script generation failed after {max_retries} attempts: {last_error}")


if __name__ == "__main__":
    import sys

    topic = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")) if len(sys.argv) > 1 else json.loads(sys.stdin.read())
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    script = generate_script(topic, config["scene_count"])
    json.dump(script, sys.stdout, indent=2)
