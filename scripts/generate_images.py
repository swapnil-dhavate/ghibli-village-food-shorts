"""Generate one still image per scene via Pollinations.ai's free, keyless image API.

Pollinations doesn't support a real negative-prompt parameter for every backing model,
so the negative prompt is folded into the text prompt as an "Avoid:" clause instead.
No character-consistency guarantee here -- same wording every scene is the only lever
we have without a trained LoRA (see README's known-limitations section).
"""

import json
import sys
import time
import urllib.parse
from pathlib import Path

import requests

POLLINATIONS_BASE = "https://image.pollinations.ai/prompt"


def build_full_prompt(scene):
    # Pollinations' flux backend only reliably attends to roughly the first ~300 characters
    # of a prompt -- appending the long negative-prompt text pushes real subject content out
    # of that window and the model falls back to a generic background. Rely on the (short,
    # front-loaded) positive image_prompt alone; negative_prompt is kept on the scene for
    # documentation / other tools but intentionally not sent here.
    return scene["image_prompt"]


def generate_image(scene, width, height, seed, model, out_path, max_retries=4):
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
            out_path.write_bytes(resp.content)
            return
        except Exception as exc:  # noqa: BLE001 - retry then re-raise
            last_error = exc
            time.sleep(8 * attempt)

    raise RuntimeError(f"Image generation failed for scene {scene['scene_number']} after {max_retries} attempts: {last_error}")


def generate_all_images(story, output_dir, width, height, model, base_seed):
    output_dir.mkdir(parents=True, exist_ok=True)
    for scene in story["scenes"]:
        seed = base_seed + scene["scene_number"]
        out_path = output_dir / f"scene_{scene['scene_number']:02d}.png"
        generate_image(scene, width, height, seed, model, out_path)
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
