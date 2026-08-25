"""Generate one still image per scene via Pollinations.ai's image API.

Primary path: the free, keyless `flux` model, text-prompt-only. No character-consistency
guarantee here -- same wording every scene (plus a shared seed, see generate_all_images) is
the only lever available without a reference image.

Optional upgrade path: if POLLINATIONS_API_KEY is set (a free account at
enter.pollinations.ai, no card needed), try the `kontext` image-to-image model first,
conditioned on that scene's primary_character's committed reference portrait (see
constants.CHARACTER_REFERENCE_IMAGES) -- this carries real identity/style consistency across
scenes AND across every future video, not just a shared seed's rough family resemblance.
Falls back to the plain flux path automatically (no error) whenever kontext is unavailable,
unauthenticated, or out of free daily credit -- this can never cost anything unless the
account has a card on file, which it should not for this project's $0 constraint.
"""

import base64
import json
import os
import sys
import time
import urllib.parse
from pathlib import Path

import requests

from constants import CHARACTER_REFERENCE_IMAGES, REPO_RAW_BASE_URL

POLLINATIONS_BASE = "https://image.pollinations.ai/prompt"
POLLINATIONS_API_KEY = os.environ.get("POLLINATIONS_API_KEY")
# Deliberately a DIFFERENT model from generate_story.py's GEMINI_MODEL -- each Gemini free-tier
# model has its own separate daily request quota (discovered empirically: gemini-3.6-flash caps
# at just 20 requests/day on the free tier). Routing the many small QC checks to a lighter model
# keeps them off the story-generation model's quota entirely.
GEMINI_VISION_MODEL = os.environ.get("GEMINI_QC_MODEL", "gemini-3.5-flash-lite")
QC_MAX_ATTEMPTS = 3


def build_full_prompt(scene):
    # Pollinations' flux backend only reliably attends to roughly the first ~300 characters
    # of a prompt -- appending the long negative-prompt text pushes real subject content out
    # of that window and the model falls back to a generic background. Rely on the (short,
    # front-loaded) positive image_prompt alone; negative_prompt is kept on the scene for
    # documentation / other tools but intentionally not sent here.
    return scene["image_prompt"]


def check_image_matches(image_bytes, description):
    """Ask Gemini (already-free-tier, multimodal) whether the generated image actually
    shows what the scene called for. Free image generation is seed-dependent and sometimes
    drifts completely off-prompt (verified during testing) -- this catches that so a bad
    render doesn't ship. Returns True on any inconclusive/error case so a QC hiccup never
    blocks the pipeline; it can only trigger a retry, never a hard failure.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return True
    try:
        payload = {
            "contents": [{"parts": [
                {"text": f"Does this image clearly show: {description}? Reply with only one word: MATCH or NO_MATCH."},
                {"inline_data": {"mime_type": "image/png", "data": base64.b64encode(image_bytes).decode("ascii")}},
            ]}]
        }
        resp = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_VISION_MODEL}:generateContent",
            params={"key": api_key}, json=payload, timeout=60,
        )
        resp.raise_for_status()
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip().upper()
        return "NO_MATCH" not in text
    except Exception as exc:  # noqa: BLE001
        print(f"[generate_images] QC check failed, skipping: {exc}", file=sys.stderr)
        return True


def fetch_image_bytes(scene, width, height, seed, model, max_retries=4):
    prompt = build_full_prompt(scene)
    encoded = urllib.parse.quote(prompt, safe="")
    url = f"{POLLINATIONS_BASE}/{encoded}"
    params = {
        "width": width,
        "height": height,
        "seed": seed,
        "model": model,
        "nologo": "true",
    }

    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(url, params=params, timeout=180)
            resp.raise_for_status()
            return resp.content
        except Exception as exc:  # noqa: BLE001 - retry then re-raise
            last_error = exc
            time.sleep(8 * attempt)

    raise RuntimeError(f"Image generation failed for scene {scene['scene_number']} after {max_retries} attempts: {last_error}")


def fetch_kontext_image_bytes(scene, width, height, timeout=180):
    """Try the reference-conditioned `kontext` model for this scene. Returns None (never
    raises) whenever it's unavailable for any reason -- no API key configured, no reference
    image for this scene's primary_character, out of free daily credit, or any request error
    -- so the caller can transparently fall back to the always-free flux path.
    """
    if not POLLINATIONS_API_KEY:
        return None
    reference_rel_path = CHARACTER_REFERENCE_IMAGES.get(scene.get("primary_character"))
    if not reference_rel_path:
        return None

    reference_url = f"{REPO_RAW_BASE_URL}/{reference_rel_path}"
    prompt = build_full_prompt(scene)
    encoded_prompt = urllib.parse.quote(prompt, safe="")
    url = f"{POLLINATIONS_BASE}/{encoded_prompt}"
    params = {
        "width": width,
        "height": height,
        "model": "kontext",
        "image": reference_url,
        "nologo": "true",
    }
    headers = {"Authorization": f"Bearer {POLLINATIONS_API_KEY}"}

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=timeout)
        if resp.status_code != 200 or "image" not in resp.headers.get("content-type", ""):
            print(f"[generate_images] kontext unavailable for scene {scene['scene_number']} ({resp.status_code}), falling back to flux", file=sys.stderr)
            return None
        return resp.content
    except Exception as exc:  # noqa: BLE001 - any failure just falls back to flux
        print(f"[generate_images] kontext request failed for scene {scene['scene_number']}, falling back to flux: {exc}", file=sys.stderr)
        return None


def generate_image(scene, width, height, seed, model, out_path):
    """Generate an image for this scene, re-rolling the seed up to QC_MAX_ATTEMPTS times if
    Gemini's vision QC says the render doesn't match the scene's intended action. Free-tier
    image generation is seed-dependent and can drift completely off-prompt on a given seed
    (verified during testing) -- a different seed on the same prompt often fixes it. Each
    attempt tries the reference-conditioned kontext model first (see fetch_kontext_image_bytes),
    falling back to plain flux whenever kontext isn't available.

    Raises if every attempt still fails QC: shipping a confirmed-mismatched image (verified
    during testing to sometimes be completely unrelated to the prompt, e.g. a random forest
    scene for a cooking video) is worse than failing the run for a day -- the workflow can
    always be re-triggered manually.
    """
    image_bytes = None
    for attempt in range(QC_MAX_ATTEMPTS):
        image_bytes = fetch_kontext_image_bytes(scene, width, height)
        if image_bytes is None:
            image_bytes = fetch_image_bytes(scene, width, height, seed + attempt * 1000, model)
        if check_image_matches(image_bytes, scene["character_actions"]):
            out_path.write_bytes(image_bytes)
            return
        print(f"[generate_images] scene {scene['scene_number']} QC mismatch on attempt {attempt + 1}, retrying with new seed", file=sys.stderr)

    raise RuntimeError(
        f"scene {scene['scene_number']} failed vision QC on all {QC_MAX_ATTEMPTS} attempts "
        f"(action: {scene['character_actions']!r}) -- refusing to publish a confirmed-mismatched image"
    )


def generate_all_images(story, output_dir, width, height, model, base_seed):
    """Every scene uses the SAME base_seed (only the prompt differs) -- verified during testing
    that this makes rendering style/color-grading far more consistent scene-to-scene than
    incrementing the seed per scene, since the free backend's style drift is seed-driven, not
    prompt-driven. Retries (see generate_image) still vary the seed, just from this shared base.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    for scene in story["scenes"]:
        out_path = output_dir / f"scene_{scene['scene_number']:02d}.png"
        generate_image(scene, width, height, base_seed, model, out_path)
        scene["image_path"] = str(out_path)
    return story


if __name__ == "__main__":
    story_path, output_dir_arg = sys.argv[1], sys.argv[2]
    story = json.loads(Path(story_path).read_text(encoding="utf-8"))

    root = Path(__file__).resolve().parent.parent
    config = json.loads((root / "config.json").read_text(encoding="utf-8"))
    resolution = config["resolution"]

    output_dir = Path(output_dir_arg)
    base_seed = int(time.time()) % 100000

    story = generate_all_images(
        story, output_dir, resolution["width"], resolution["height"], config["image_model"], base_seed
    )

    (output_dir / "story_with_images.json").write_text(json.dumps(story, indent=2), encoding="utf-8")
    json.dump(story, sys.stdout, indent=2)
