"""Shared constants: character bible, environment rules, negative prompt.

Kept as plain Python strings (not an LLM call) so every scene's image prompt
is built from the exact same wording -- this is the main lever we have for
character/style consistency without a trained LoRA.
"""

CHARACTER_BIBLE = """\
FATHER: 35-year-old Indian village farmer, kind and caring expression, simple cotton dhoti \
and light cotton kurta, barefoot, a traditional woven towel resting on one shoulder.
MOTHER: 32-year-old woman, warm and loving expression, traditional cotton saree, hair neatly \
tied back, small red bindi, gentle smile.
GRANDMOTHER: 65-year-old woman, wrinkled face, white-grey hair tied in a bun, traditional \
cotton saree, wise and caring expression.
SON: 8-year-old boy, cheerful, simple village clothes, curious and playful expression.
DAUGHTER: 6-year-old girl, long braided hair, traditional frock or lehenga, happy and \
innocent expression.
"""

ART_STYLE = (
    "Studio Ghibli-style hand-drawn animated film still, soft painterly background, "
    "hand-painted textures, organic brush strokes, warm cinematic lighting, rich greenery, "
    "vibrant yet natural colors, magical realism, cozy countryside atmosphere, highly detailed, "
    "no CGI sheen, no 3D render look, no photorealism"
)

ENVIRONMENT_RULES = (
    "Traditional Indian village setting only: mud house, earthen courtyard, clay stove (chulha), "
    "thatched roof, earthen and brass utensils, wooden and bamboo baskets, firewood. "
    "Never include: cars, motorcycles, electricity poles, plastic furniture, modern kitchen "
    "appliances, mobile phones, television, or concrete city buildings."
)

NEGATIVE_PROMPT = (
    "text, subtitles, watermark, logo, modern house, city buildings, vehicles, motorcycles, "
    "electric poles, plastic furniture, microwave, refrigerator, gas stove, induction stove, "
    "mobile phone, television, modern clothing, extra people, blurry face, low quality, "
    "bad anatomy, extra fingers, missing fingers, duplicate body parts, distorted hands, "
    "cropped body, oversaturated colors, unrealistic food, inconsistent characters, "
    "inconsistent clothing"
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

# audio_tags an LLM may use per scene; each must map to assets/sfx/<tag>.mp3 for assemble_video.py
KNOWN_AUDIO_TAGS = [
    "rain", "birds", "river", "wind_leaves", "footsteps_wet_soil", "chopping",
    "grinding_stone", "water_pouring", "rice_washing", "dough_kneading", "oil_sizzling",
    "clay_pot_boiling", "wooden_spoon_stirring", "fire_crackling", "utensil_clinks",
    "banana_leaf", "steam", "eating_ambience",
]
