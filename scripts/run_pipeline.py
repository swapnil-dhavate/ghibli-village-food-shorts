"""Orchestrates one full daily run: pick topic -> research+write narrated script -> synthesize
narration (Piper TTS) -> generate images -> assemble video (motion+voice+music+captions) ->
upload to YouTube (unlisted by default -- see config.json's youtube_privacy_status -- so a
human reviews and approves before it goes public). Called by .github/workflows/daily_video.yml,
or manually for testing.
"""

import json
import os
import sys
import time
from pathlib import Path

from pick_topic import pick_next_topic
from generate_script import generate_script
from generate_voice import generate_all_voice
from generate_images import generate_all_images
from assemble_video import assemble

ROOT = Path(__file__).resolve().parent.parent


def main():
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))

    run_id = time.strftime("%Y-%m-%d")
    work_dir = ROOT / "work" / run_id
    work_dir.mkdir(parents=True, exist_ok=True)

    print(f"[run_pipeline] picking today's topic...", file=sys.stderr)
    topic = pick_next_topic()
    print(f"[run_pipeline] topic: {topic['title']} ({topic['category']})", file=sys.stderr)

    print(f"[run_pipeline] researching and writing script via Gemini...", file=sys.stderr)
    story = generate_script(topic, config["scene_count"])
    (work_dir / "story.json").write_text(json.dumps(story, indent=2), encoding="utf-8")

    print(f"[run_pipeline] synthesizing narration via Piper TTS...", file=sys.stderr)
    story = generate_all_voice(story, work_dir / "voice")
    (work_dir / "story.json").write_text(json.dumps(story, indent=2), encoding="utf-8")

    print(f"[run_pipeline] generating {len(story['scenes'])} scene images via Pollinations...", file=sys.stderr)
    base_seed = int(time.time()) % 100000
    story = generate_all_images(
        story, work_dir / "images", config["resolution"]["width"], config["resolution"]["height"],
        config["image_model"], base_seed,
    )
    (work_dir / "story.json").write_text(json.dumps(story, indent=2), encoding="utf-8")

    print(f"[run_pipeline] assembling video...", file=sys.stderr)
    video_path = work_dir / f"{topic['id']}_{run_id}.mp4"
    assemble(
        story, work_dir, ROOT / "assets" / "sfx", ROOT / "assets" / "music",
        config["resolution"]["width"], config["resolution"]["height"], video_path,
    )
    print(f"[run_pipeline] video ready: {video_path}", file=sys.stderr)

    if os.environ.get("SKIP_YOUTUBE_UPLOAD") == "1":
        print(f"[run_pipeline] SKIP_YOUTUBE_UPLOAD=1 set, not uploading. Done: {video_path}")
        return str(video_path)

    from upload_youtube import upload_video

    # Lets a manual workflow_dispatch run override config.json's default for this run only.
    privacy_status = os.environ.get("YOUTUBE_PRIVACY_OVERRIDE") or config["youtube_privacy_status"]
    print(f"[run_pipeline] uploading to YouTube (privacy={privacy_status})...", file=sys.stderr)
    result = upload_video(str(video_path), story, privacy_status, config["youtube_category_id"])
    url = f"https://youtube.com/shorts/{result['id']}"
    print(f"[run_pipeline] done: {url}")
    return url


if __name__ == "__main__":
    main()
