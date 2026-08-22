"""Assemble the final vertical video from scene stills using ffmpeg only (no GPU, no paid API).

Per scene: apply a Ken Burns pan/zoom (ffmpeg zoompan) to the still image, and build an SFX
bed from assets/sfx/<tag>.mp3 files matching the scene's audio_tags (silence if none are
present on disk yet -- see assets/sfx/README.md).

Scenes are chained together with real crossfade transitions (video: xfade, audio: acrossfade),
not hard cuts, so the short still feels like one continuous piece rather than a slideshow.
"""

import json
import subprocess
import sys
from pathlib import Path

TRANSITION_SECONDS = 0.8
FPS = 25

ZOOMPAN_EXPR = {
    # z: zoom expression, x/y: pan expressions. `on`=output frame index, `d`=total frames.
    "static": {
        "z": "1.08",
        "x": "iw/2-(iw/zoom/2)",
        "y": "ih/2-(ih/zoom/2)",
    },
    "push_in": {
        "z": "min(zoom+0.0015,1.25)",
        "x": "iw/2-(iw/zoom/2)",
        "y": "ih/2-(ih/zoom/2)",
    },
    "pull_out": {
        "z": "if(eq(on,0),1.25,max(zoom-0.0015,1.0))",
        "x": "iw/2-(iw/zoom/2)",
        "y": "ih/2-(ih/zoom/2)",
    },
    "pan_left": {
        "z": "1.15",
        "x": "(iw-iw/zoom)*(1-on/{d})",
        "y": "ih/2-(ih/zoom/2)",
    },
    "pan_right": {
        "z": "1.15",
        "x": "(iw-iw/zoom)*(on/{d})",
        "y": "ih/2-(ih/zoom/2)",
    },
    "tilt_up": {
        "z": "1.15",
        "x": "iw/2-(iw/zoom/2)",
        "y": "(ih-ih/zoom)*(1-on/{d})",
    },
    "tilt_down": {
        "z": "1.15",
        "x": "iw/2-(iw/zoom/2)",
        "y": "(ih-ih/zoom)*(on/{d})",
    },
}


def run(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{result.stderr[-4000:]}")
    return result


def make_scene_clip(image_path, camera_motion, duration, width, height, out_path):
    d_frames = int(duration * FPS)
    expr = ZOOMPAN_EXPR.get(camera_motion, ZOOMPAN_EXPR["static"])
    x_expr = expr["x"].format(d=d_frames)
    y_expr = expr["y"].format(d=d_frames)
    vf = (
        f"scale={width * 3}:{height * 3},"
        f"zoompan=z='{expr['z']}':d={d_frames}:x='{x_expr}':y='{y_expr}':s={width}x{height}:fps={FPS},"
        "format=yuv420p"
    )
    run([
        "ffmpeg", "-y", "-loop", "1", "-i", str(image_path),
        "-vf", vf, "-t", str(duration), "-r", str(FPS),
        str(out_path),
    ])


def make_scene_audio(audio_tags, sfx_dir, duration, out_path):
    available = [sfx_dir / f"{tag}.mp3" for tag in audio_tags if (sfx_dir / f"{tag}.mp3").exists()]
    missing = [tag for tag in audio_tags if not (sfx_dir / f"{tag}.mp3").exists()]
    for tag in missing:
        print(f"[assemble_video] no sfx file for tag '{tag}' (expected assets/sfx/{tag}.mp3) - skipping", file=sys.stderr)

    if not available:
        run([
            "ffmpeg", "-y", "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo",
            "-t", str(duration), str(out_path),
        ])
        return

    cmd = ["ffmpeg", "-y"]
    for track in available:
        cmd += ["-stream_loop", "-1", "-t", str(duration), "-i", str(track)]
    n = len(available)
    filter_complex = "".join(f"[{i}:a]" for i in range(n)) + f"amix=inputs={n}:duration=first:dropout_transition=2[aout]"
    cmd += ["-filter_complex", filter_complex, "-map", "[aout]", str(out_path)]
    run(cmd)


def chain_xfade(clip_paths, clip_duration, out_path):
    n = len(clip_paths)
    if n == 1:
        run(["ffmpeg", "-y", "-i", str(clip_paths[0]), "-c", "copy", str(out_path)])
        return

    cmd = ["ffmpeg", "-y"]
    for p in clip_paths:
        cmd += ["-i", str(p)]

    filter_parts = []
    cumulative = clip_duration
    last_label = "0:v"
    for i in range(1, n):
        offset = cumulative - TRANSITION_SECONDS
        out_label = f"v{i}" if i < n - 1 else "vout"
        filter_parts.append(
            f"[{last_label}][{i}:v]xfade=transition=fade:duration={TRANSITION_SECONDS}:offset={offset:.3f}[{out_label}]"
        )
        last_label = out_label
        cumulative = cumulative + clip_duration - TRANSITION_SECONDS

    cmd += ["-filter_complex", ";".join(filter_parts), "-map", "[vout]", str(out_path)]
    run(cmd)


def chain_acrossfade(audio_paths, out_path):
    n = len(audio_paths)
    if n == 1:
        run(["ffmpeg", "-y", "-i", str(audio_paths[0]), "-c", "copy", str(out_path)])
        return

    cmd = ["ffmpeg", "-y"]
    for p in audio_paths:
        cmd += ["-i", str(p)]

    filter_parts = []
    last_label = "0:a"
    for i in range(1, n):
        out_label = f"a{i}" if i < n - 1 else "aout"
        filter_parts.append(
            f"[{last_label}][{i}:a]acrossfade=d={TRANSITION_SECONDS}[{out_label}]"
        )
        last_label = out_label

    cmd += ["-filter_complex", ";".join(filter_parts), "-map", "[aout]", str(out_path)]
    run(cmd)


def assemble(story, work_dir, sfx_dir, width, height, out_path):
    work_dir = Path(work_dir)
    scenes = story["scenes"]
    total_duration = story.get("_video_duration_seconds", 28)
    clip_duration = total_duration / len(scenes)

    video_clips, audio_clips = [], []
    for scene in scenes:
        n = scene["scene_number"]
        v_path = work_dir / f"scene_{n:02d}_v.mp4"
        a_path = work_dir / f"scene_{n:02d}_a.m4a"
        make_scene_clip(scene["image_path"], scene["camera_motion"], clip_duration, width, height, v_path)
        make_scene_audio(scene["audio_tags"], Path(sfx_dir), clip_duration, a_path)
        video_clips.append(v_path)
        audio_clips.append(a_path)

    video_out = work_dir / "video_only.mp4"
    audio_out = work_dir / "audio_only.m4a"
    chain_xfade(video_clips, clip_duration, video_out)
    chain_acrossfade(audio_clips, audio_out)

    run([
        "ffmpeg", "-y", "-i", str(video_out), "-i", str(audio_out),
        "-c:v", "libx264", "-c:a", "aac", "-shortest", str(out_path),
    ])


if __name__ == "__main__":
    story_path, work_dir_arg, out_path_arg = sys.argv[1], sys.argv[2], sys.argv[3]
    story = json.loads(Path(story_path).read_text(encoding="utf-8"))

    root = Path(__file__).resolve().parent.parent
    config = json.loads((root / "config.json").read_text(encoding="utf-8"))
    story["_video_duration_seconds"] = config["video_duration_seconds"]

    assemble(
        story,
        work_dir_arg,
        root / "assets" / "sfx",
        config["resolution"]["width"],
        config["resolution"]["height"],
        out_path_arg,
    )
    print(out_path_arg)
