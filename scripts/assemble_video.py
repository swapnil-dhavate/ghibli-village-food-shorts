"""Assemble the final vertical video from scene stills using ffmpeg only (no GPU, no paid API).

Per scene: apply a Ken Burns pan/zoom (ffmpeg zoompan) to the still image, sized to that
scene's actual narration length (not a fixed even split -- see PADDING_SECONDS/MIN_SCENE_SECONDS),
and build an audio bed mixing that scene's Piper narration with a low-volume SFX texture from
assets/sfx/<tag>.mp3. Scenes are chained together with real crossfade transitions (video: xfade,
audio: acrossfade), not hard cuts. A single looped background-music bed (assets/music/<mood>.mp3,
picked once per video by generate_script.py) is mixed under everything at the end, and the
narration text is burned in as on-screen captions synced to when each scene's narration plays.
"""

import json
import subprocess
import sys
from pathlib import Path

TRANSITION_SECONDS = 0.8
FPS = 25
LEAD_IN = 0.3  # seconds of near-silence before narration starts in each scene, for breathing room
PADDING_SECONDS = 1.2  # added to each scene's own narration length to get its clip duration
MIN_SCENE_SECONDS = 3.0  # floor, in case a scene's narration is unusually short
SFX_VOLUME = 0.22
MUSIC_VOLUME = 0.14
# DejaVu Sans has NO Devanagari glyphs at all (verified directly -- renders as empty tofu
# boxes), so it can't be used now that narration/captions/title are Hindi. Noto Sans
# Devanagari covers Devanagari plus basic Latin/numbers/punctuation (verified: "आकाश 100%
# नीला #Shorts (2026)" renders correctly, mixed script and all).
HOOK_FONT_FILE = "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf"
HOOK_SECONDS = 2.2
CAPTION_FONT_SIZE = 40


def _ease(frame_expr, d_expr):
    # Cosine ease-in-out over [0,1] instead of a linear ramp -- a constant-velocity pan/zoom
    # reads as an obvious mechanical "ffmpeg slideshow" tell; slow-in/slow-out reads as an
    # intentional camera move. `min(on,d)` guards the very last frame from overshooting.
    return f"(1-cos(PI*min({frame_expr},{d_expr})/{d_expr}))/2"


ZOOMPAN_EXPR = {
    # z/x/y are all direct functions of `on` (output frame index) and `d` (total frames),
    # not frame-to-frame recursive increments, so the eased curve above can drive them.
    # `on`=output frame index, `d`=total frames.
    #
    # Ranges bumped up (0.22->0.40 zoom, 1.18->1.32 pan/tilt headroom) after user feedback that
    # motion over a 5-8s narration-driven clip read as barely-there/static at the old range --
    # same eased curve, just a bigger sweep so it's actually perceptible as movement.
    "static": {
        "z": "1.10",
        "x": "iw/2-(iw/zoom/2)",
        "y": "ih/2-(ih/zoom/2)",
    },
    "push_in": {
        "z": f"1.0+0.40*{_ease('on', '{d}')}",
        "x": "iw/2-(iw/zoom/2)",
        "y": "ih/2-(ih/zoom/2)",
    },
    "pull_out": {
        "z": f"1.40-0.40*{_ease('on', '{d}')}",
        "x": "iw/2-(iw/zoom/2)",
        "y": "ih/2-(ih/zoom/2)",
    },
    "pan_left": {
        "z": "1.32",
        "x": f"(iw-iw/zoom)*(1-{_ease('on', '{d}')})",
        "y": "ih/2-(ih/zoom/2)",
    },
    "pan_right": {
        "z": "1.32",
        "x": f"(iw-iw/zoom)*{_ease('on', '{d}')}",
        "y": "ih/2-(ih/zoom/2)",
    },
    "tilt_up": {
        "z": "1.32",
        "x": "iw/2-(iw/zoom/2)",
        "y": f"(ih-ih/zoom)*(1-{_ease('on', '{d}')})",
    },
    "tilt_down": {
        "z": "1.32",
        "x": "iw/2-(iw/zoom/2)",
        "y": f"(ih-ih/zoom)*{_ease('on', '{d}')}",
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
    z_expr = expr["z"].format(d=d_frames)
    x_expr = expr["x"].format(d=d_frames)
    y_expr = expr["y"].format(d=d_frames)
    vf = (
        f"scale={width * 3}:{height * 3},"
        f"zoompan=z='{z_expr}':d={d_frames}:x='{x_expr}':y='{y_expr}':s={width}x{height}:fps={FPS},"
        "format=yuv420p"
    )
    run([
        "ffmpeg", "-y", "-loop", "1", "-i", str(image_path),
        "-vf", vf, "-t", str(duration), "-r", str(FPS),
        str(out_path),
    ])


def make_sfx_bed(audio_tags, sfx_dir, duration, out_path):
    available = [sfx_dir / f"{tag}.mp3" for tag in audio_tags if (sfx_dir / f"{tag}.mp3").exists()]
    missing = [tag for tag in audio_tags if not (sfx_dir / f"{tag}.mp3").exists()]
    for tag in missing:
        print(f"[assemble_video] no sfx file for tag '{tag}' (expected assets/sfx/{tag}.mp3) - skipping", file=sys.stderr)

    if not available:
        run([
            "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
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


def make_scene_audio_bed(scene, sfx_dir, clip_duration, out_path):
    """Mix this scene's Piper narration (delayed by LEAD_IN, padded to clip_duration) with a
    low-volume SFX texture bed. Narration is the foreground element -- SFX is deliberately
    quiet support, unlike the old wordless-ASMR pipeline where SFX alone carried the scene.
    """
    sfx_path = out_path.with_name(out_path.stem + "_sfx.wav")
    make_sfx_bed(scene["audio_tags"], Path(sfx_dir), clip_duration, sfx_path)

    lead_in_ms = int(LEAD_IN * 1000)
    filter_complex = (
        f"[0:a]loudnorm=I=-16:TP=-1.5:LRA=11,adelay=delays={lead_in_ms}:all=1,"
        f"apad=whole_dur={clip_duration}[voice];"
        f"[1:a]volume={SFX_VOLUME}[sfx];"
        f"[voice][sfx]amix=inputs=2:duration=first:dropout_transition=0[aout]"
    )
    run([
        "ffmpeg", "-y",
        "-i", str(scene["voice_path"]),
        "-i", str(sfx_path),
        "-filter_complex", filter_complex,
        "-map", "[aout]", str(out_path),
    ])


def chain_xfade(clip_infos, out_path):
    """clip_infos: list of (path, duration) in scene order -- durations vary per scene now
    (narration-driven), so offsets are computed from each clip's own duration instead of a
    single shared value.
    """
    n = len(clip_infos)
    if n == 1:
        run(["ffmpeg", "-y", "-i", str(clip_infos[0][0]), "-c", "copy", str(out_path)])
        return

    cmd = ["ffmpeg", "-y"]
    for p, _ in clip_infos:
        cmd += ["-i", str(p)]

    filter_parts = []
    cumulative = clip_infos[0][1]
    last_label = "0:v"
    for i in range(1, n):
        offset = cumulative - TRANSITION_SECONDS
        out_label = f"v{i}" if i < n - 1 else "vout"
        filter_parts.append(
            f"[{last_label}][{i}:v]xfade=transition=fade:duration={TRANSITION_SECONDS}:offset={offset:.3f}[{out_label}]"
        )
        last_label = out_label
        cumulative = cumulative + clip_infos[i][1] - TRANSITION_SECONDS

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


def mix_background_music(narration_sfx_path, music_mood, music_dir, total_duration, out_path):
    music_path = Path(music_dir) / f"{music_mood}.mp3" if music_mood else None
    if not music_path or not music_path.exists():
        print(f"[assemble_video] no music file for mood '{music_mood}' (expected assets/music/{music_mood}.mp3) - skipping music", file=sys.stderr)
        run(["ffmpeg", "-y", "-i", str(narration_sfx_path), "-c", "copy", str(out_path)])
        return
    run([
        "ffmpeg", "-y",
        "-i", str(narration_sfx_path),
        "-stream_loop", "-1", "-t", str(total_duration), "-i", str(music_path),
        "-filter_complex",
        f"[1:a]volume={MUSIC_VOLUME}[music];[0:a][music]amix=inputs=2:duration=first:dropout_transition=0[aout]",
        "-map", "[aout]", str(out_path),
    ])


def compute_scene_starts(clip_durations):
    """Mirrors chain_xfade's internal offset math so captions/timing line up with where each
    scene actually starts in the crossfaded output."""
    starts = [0.0]
    cumulative = clip_durations[0]
    for d in clip_durations[1:]:
        offset = cumulative - TRANSITION_SECONDS
        starts.append(offset)
        cumulative = cumulative + d - TRANSITION_SECONDS
    return starts


def _escape_drawtext(text):
    # ffmpeg drawtext's text= value (wrapped in single quotes at the call site) still needs
    # colons backslash-escaped even inside the quotes. A literal single quote is the one
    # character with NO working escape inside a quoted value -- verified directly that every
    # backslash-escape variant either broke the whole filtergraph or silently swallowed
    # everything after it into the text value (production crash: real narration containing
    # "Earth's" broke parsing). Fix: swap it for the Unicode right single quote (U+2019),
    # which isn't a quote delimiter to ffmpeg's parser at all -- also reads as more
    # typographically correct in a rendered caption. % needs no escaping as long as the
    # call site also sets expansion=none (disables drawtext's own %{...} text-expansion
    # syntax, which a backslash-escaped % does NOT survive -- verified separately).
    return text.replace("'", "’").replace("\\", "\\\\").replace(":", "\\:")


def _fit_font_size(text, max_width_px, font_path, max_size=58, min_size=28, step=2):
    """Measure actual rendered text width (via the real font file) and shrink until it fits,
    instead of guessing a fixed size -- verified directly that a fixed size overflowed the
    frame on a longer title ("Refreshing Pakhala Bhata of Odisha" got clipped on both edges).
    Falls back to min_size (never crashes) if Pillow or the font file isn't available, e.g. in
    a local dev environment without fonts-dejavu-core installed.
    """
    try:
        from PIL import ImageFont
    except ImportError:
        return min_size
    size = max_size
    while size > min_size:
        try:
            font = ImageFont.truetype(font_path, size)
        except OSError:
            return min_size
        if font.getlength(text) <= max_width_px:
            return size
        size -= step
    return min_size


def _wrap_text(text, max_width_px, font_path, fontsize, max_lines=4):
    """Break narration text into lines that actually fit the frame width -- drawtext has no
    built-in auto-wrap, and captions (full 12-25 word sentences) are far too long for one line.
    """
    words = text.split()
    try:
        from PIL import ImageFont
        font = ImageFont.truetype(font_path, fontsize)
        measure = font.getlength
    except (ImportError, OSError):
        # Font unavailable (e.g. local dev without fonts-dejavu-core) -- fall back to a rough
        # fixed word-count wrap so this never crashes, just less precisely fitted.
        approx_per_line = 6
        return [" ".join(words[i:i + approx_per_line]) for i in range(0, len(words), approx_per_line)][:max_lines]

    lines = []
    current = []
    for word in words:
        trial = " ".join(current + [word])
        if not current or measure(trial) <= max_width_px:
            current.append(word)
        else:
            lines.append(" ".join(current))
            current = [word]
    if current:
        lines.append(" ".join(current))
    return lines[:max_lines]


def add_title_hook(video_in, video_title, width, out_path):
    """Overlay the topic title for the first ~2s as a fading title card. A silent slideshow
    with zero on-screen text has nothing to stop the scroll or orient a muted viewer in the
    first second -- this is a cheap, free fix for that, independent of image/motion quality.
    """
    hook_text = video_title.split("|")[0].replace("#Shorts", "").strip()
    if not hook_text:
        run(["ffmpeg", "-y", "-i", str(video_in), "-c", "copy", str(out_path)])
        return

    escaped = _escape_drawtext(hook_text)
    fontsize = _fit_font_size(hook_text, width * 0.88, HOOK_FONT_FILE)
    fade_expr = (
        f"if(lt(t,0.3),t/0.3,if(gt(t,{HOOK_SECONDS - 0.3}),max(0,({HOOK_SECONDS}-t)/0.3),1))"
    )
    vf = (
        f"drawtext=fontfile={HOOK_FONT_FILE}:text='{escaped}':fontsize={fontsize}:fontcolor=white:"
        f"box=1:boxcolor=black@0.45:boxborderw=24:x=(w-text_w)/2:y=140:expansion=none:"
        f"enable='lte(t,{HOOK_SECONDS})':alpha='{fade_expr}'"
    )
    run(["ffmpeg", "-y", "-i", str(video_in), "-vf", vf, str(out_path)])


def burn_captions(video_in, scenes, scene_starts, clip_durations, width, out_path):
    """Burn each scene's narration_text as an on-screen caption, visible while that scene's
    narration audio actually plays -- a silent/uncaptioned video loses most muted-viewing
    retention, which is most Shorts traffic.
    """
    parts = []
    for scene, start, duration in zip(scenes, scene_starts, clip_durations):
        lines = _wrap_text(scene["narration_text"], width * 0.86, HOOK_FONT_FILE, CAPTION_FONT_SIZE)
        escaped = _escape_drawtext("\n".join(lines))
        cap_start = start + LEAD_IN
        cap_end = min(start + LEAD_IN + scene["voice_duration"] + 0.4, start + duration)
        parts.append(
            f"drawtext=fontfile={HOOK_FONT_FILE}:text='{escaped}':fontsize={CAPTION_FONT_SIZE}:"
            f"fontcolor=white:box=1:boxcolor=black@0.55:boxborderw=18:x=(w-text_w)/2:y=h-380:"
            f"line_spacing=6:expansion=none:enable='between(t,{cap_start:.3f},{cap_end:.3f})'"
        )
    vf = ",".join(parts)
    run(["ffmpeg", "-y", "-i", str(video_in), "-vf", vf, str(out_path)])


def assemble(story, work_dir, sfx_dir, music_dir, width, height, out_path):
    work_dir = Path(work_dir)
    scenes = story["scenes"]

    clip_durations = [
        max(scene["voice_duration"] + PADDING_SECONDS, MIN_SCENE_SECONDS) for scene in scenes
    ]

    video_clips, audio_beds = [], []
    for scene, duration in zip(scenes, clip_durations):
        n = scene["scene_number"]
        v_path = work_dir / f"scene_{n:02d}_v.mp4"
        a_path = work_dir / f"scene_{n:02d}_a.wav"
        make_scene_clip(scene["image_path"], scene["camera_motion"], duration, width, height, v_path)
        make_scene_audio_bed(scene, sfx_dir, duration, a_path)
        video_clips.append(v_path)
        audio_beds.append(a_path)

    video_out = work_dir / "video_only.mp4"
    video_hooked = work_dir / "video_with_hook.mp4"
    video_captioned = work_dir / "video_captioned.mp4"
    narration_sfx_out = work_dir / "narration_sfx.wav"
    audio_out = work_dir / "audio_only.wav"

    chain_xfade(list(zip(video_clips, clip_durations)), video_out)
    chain_acrossfade(audio_beds, narration_sfx_out)

    total_duration = sum(clip_durations) - TRANSITION_SECONDS * (len(scenes) - 1)
    mix_background_music(narration_sfx_out, story.get("music_mood", ""), music_dir, total_duration, audio_out)

    add_title_hook(video_out, story.get("video_title", ""), width, video_hooked)

    scene_starts = compute_scene_starts(clip_durations)
    burn_captions(video_hooked, scenes, scene_starts, clip_durations, width, video_captioned)

    run([
        "ffmpeg", "-y", "-i", str(video_captioned), "-i", str(audio_out),
        "-c:v", "libx264", "-c:a", "aac", "-shortest", str(out_path),
    ])


if __name__ == "__main__":
    story_path, work_dir_arg, out_path_arg = sys.argv[1], sys.argv[2], sys.argv[3]
    story = json.loads(Path(story_path).read_text(encoding="utf-8"))

    root = Path(__file__).resolve().parent.parent
    config = json.loads((root / "config.json").read_text(encoding="utf-8"))

    assemble(
        story,
        work_dir_arg,
        root / "assets" / "sfx",
        root / "assets" / "music",
        config["resolution"]["width"],
        config["resolution"]["height"],
        out_path_arg,
    )
    print(out_path_arg)
