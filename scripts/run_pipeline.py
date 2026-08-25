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
MAX_ATTEMPTS = 3


def generate_video(topic, config, work_dir, run_id):
    """Script -> voice -> images -> assembly, retried as a unit up to MAX_ATTEMPTS times for
    the SAME topic (not a new topic per retry -- that would burn through the rotation catalog
    faster than one topic/day). A scene failing vision QC (generate_images.py fails loudly by
    design rather than shipping a mismatched image) is the most common reason to retry, but
    this catches any exception in the chain. Each retry is a fresh Gemini call (temperature=1.0)
    and a fresh image seed, so it's a genuinely different attempt, not a repeat of the same
    failure. Without this, a single bad scene would cost the whole day's video, since the daily
    cron only fires once.
    """
    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            print(f"[run_pipeline] attempt {attempt}/{MAX_ATTEMPTS}: researching and writing script via Gemini...", file=sys.stderr)
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
            return story, video_path
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            print(f"[run_pipeline] attempt {attempt}/{MAX_ATTEMPTS} failed: {exc}", file=sys.stderr)

    raise RuntimeError(
        f"All {MAX_ATTEMPTS} attempts failed for topic {topic['title']!r} -- giving up for today: {last_error}"
    )


def main():
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))

    run_id = time.strftime("%Y-%m-%d")
    work_dir = ROOT / "work" / run_id
    work_dir.mkdir(parents=True, exist_ok=True)

    print(f"[run_pipeline] picking today's topic...", file=sys.stderr)
    topic = pick_next_topic()
    print(f"[run_pipeline] topic: {topic['title']} ({topic['category']})", file=sys.stderr)

    story, video_path = generate_video(topic, config, work_dir, run_id)
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
