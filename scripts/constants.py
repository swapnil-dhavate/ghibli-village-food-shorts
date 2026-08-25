"""Shared constants: art style, negative prompt, camera motions, audio tags, music moods.

Generalized for any topic (history/science/nature/mystery), not just Indian village food --
the old CHARACTER_BIBLE / ENVIRONMENT_RULES / CHARACTER_REFERENCE_IMAGES were specific to the
food-channel format and are gone now that there's no fixed recurring cast.
"""

# NOTE: "Studio Ghibli anime style" tested poorly on the free image backend (drifts into
# photorealistic/3D-render looks instead of illustration). "Flat 2D children's book
# illustration style" tested reliably better -- see generate_script.py's build_prompt rule 2.
# Kept as the style anchor here since it's a proven-reliable lever on this backend, even
# though the content domain is no longer food-specific.
ART_STYLE = (
    "flat 2D children's book illustration style, warm colors, soft painterly background, "
    "vibrant yet natural colors, highly detailed, no CGI sheen, no 3D render look, no "
    "photorealism"
)

NEGATIVE_PROMPT = (
    "text, subtitles, watermark, logo, modern clothing, extra people, blurry face, low "
    "quality, bad anatomy, extra fingers, missing fingers, duplicate body parts, distorted "
    "hands, cropped body, oversaturated colors, inconsistent style"
)

# Maps a scene's requested camera_motion to an ffmpeg zoompan direction used by assemble_video.py
CAMERA_MOTIONS = {
    "static": "static",
    "push_in": "push_in",
    "pull_out": "pull_out",
    "pan_left": "pan_left",
    "pan_right": "pan_right",
    "tilt_up": "tilt_up",
    "tilt_down": "tilt_down",
}

# audio_tags an LLM may use per scene; each must map to assets/sfx/<tag>.mp3 for assemble_video.py.
# Broadened from the old food-only list (chopping/oil_sizzling/etc.) to cover history, science,
# nature, and mystery topics.
KNOWN_AUDIO_TAGS = [
    "wind", "rain", "birds", "river", "ocean_waves", "thunder", "fire_crackling",
    "footsteps", "heartbeat", "clock_ticking", "crowd_ambience", "low_drone",
    "cave_echo", "wind_chimes",
]

# music_mood an LLM picks once per video (whole-video background bed, not per-scene) --
# each must map to assets/music/<mood>.mp3. See assets/music/README.md for sourcing.
MUSIC_MOODS = ["calm", "cozy", "upbeat", "curious", "emotional"]
