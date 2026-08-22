"""Orchestrates one full daily run: pick dish -> write story -> generate images -> assemble
video -> upload to YouTube. Called by .github/workflows/daily_video.yml, or manually for testing.
"""

import json
import sys
import time
from pathlib import Path

from pick_dish import pick_next_dish
from generate_story import generate_story
from generate_images import generate_all_images
from assemble_video import assemble
from upload_youtube import upload_video

ROOT = Path(__file__).resolve().parent.parent


def main():
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))

    run_id = time.strftime("%Y-%m-%d")
    work_dir = ROOT / "work" / run_id
    work_dir.mkdir(parents=True, exist_ok=True)

    print(f"[run_pipeline] picking today's dish...", file=sys.stderr)
    dish = pick_next_dish()
    print(f"[run_pipeline] dish: {dish['name']} ({dish['region']})", file=sys.stderr)

    print(f"[run_pipeline] writing story via Gemini...", file=sys.stderr)
    story = generate_story(dish, config["scene_count"])
    story["_video_duration_seconds"] = config["video_duration_seconds"]
    (work_dir / "story.json").write_text(json.dumps(story, indent=2), encoding="utf-8")

    print(f"[run_pipeline] generating {len(story['scenes'])} scene images via Pollinations...", file=sys.stderr)
    base_seed = int(time.time()) % 100000
    story = generate_all_images(
        story, work_dir / "images", config["resolution"]["width"], config["resolution"]["height"],
        config["image_model"], base_seed,
    )
    (work_dir / "story.json").write_text(json.dumps(story, indent=2), encoding="utf-8")

    print(f"[run_pipeline] assembling video...", file=sys.stderr)
    video_path = work_dir / f"{dish['id']}_{run_id}.mp4"
    assemble(
        story, work_dir, ROOT / "assets" / "sfx",
        config["resolution"]["width"], config["resolution"]["height"], video_path,
    )
    print(f"[run_pipeline] video ready: {video_path}", file=sys.stderr)

    print(f"[run_pipeline] uploading to YouTube (privacy={config['youtube_privacy_status']})...", file=sys.stderr)
    result = upload_video(str(video_path), story, config["youtube_privacy_status"], config["youtube_category_id"])
    url = f"https://youtube.com/shorts/{result['id']}"
    print(f"[run_pipeline] done: {url}")
    return url


if __name__ == "__main__":
    main()
