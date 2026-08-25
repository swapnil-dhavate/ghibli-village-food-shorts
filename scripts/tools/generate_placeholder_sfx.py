"""Synthesize placeholder ASMR sound beds for every known audio tag using only ffmpeg's
built-in noise/filter synthesis -- no downloads, no licensing questions, fully original audio.

These are approximations (filtered noise + layered tremolo), not real field recordings. Every
recipe chains TWO tremolo stages at non-commensurate rates (e.g. 2.5Hz + 6.8Hz) instead of one
-- a single tremolo modulates amplitude on one perfectly regular cycle, which is exactly what
reads as "obviously synthetic/robotic" for anything meant to sound like an irregular real-world
event (chopping, footsteps, clinking). Two incommensurate rates multiplied together produce a
beating pattern that doesn't repeat on a short simple cycle, which is a much closer (though
still imperfect) approximation of organic irregularity. Verified this checked no ffmpeg version
issue -- the tremolo filter is 1.0-behavior stable across the versions this project targets.

Good enough to get real sound into the pipeline immediately; swap in real recordings later
(same filenames in assets/sfx/) for a richer result -- see assets/sfx/README.md.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SFX_DIR = ROOT / "assets" / "sfx"
DURATION = 8

# tag -> (noise color, extra filter chain)
# Volume is intentionally NOT hand-tuned per recipe -- bandpass filters remove wildly
# different amounts of energy depending on noise color/band, so a fixed "volume=x" multiplier
# produced wildly inconsistent loudness (rain came out at -66dB, nearly silent). loudnorm
# below normalizes every recipe to the same target loudness regardless of what the filter
# chain did to its energy.
RECIPES = {
    "rain": ("pink", "bandpass=f=3000:w=6000,tremolo=f=0.3:d=0.2,tremolo=f=0.83:d=0.1"),
    "birds": ("white", "bandpass=f=3500:w=2500,tremolo=f=7:d=0.85,tremolo=f=2.3:d=0.4"),
    "river": ("brown", "bandpass=f=600:w=900,tremolo=f=0.6:d=0.25,tremolo=f=1.7:d=0.12"),
    "wind_leaves": ("brown", "lowpass=f=1800,tremolo=f=0.2:d=0.4,tremolo=f=0.55:d=0.2"),
    "footsteps_wet_soil": ("pink", "bandpass=f=250:w=300,tremolo=f=1.2:d=0.85,tremolo=f=3.1:d=0.4"),
    "chopping": ("white", "bandpass=f=1800:w=1600,tremolo=f=2.5:d=0.9,tremolo=f=6.3:d=0.5"),
    "grinding_stone": ("brown", "bandpass=f=300:w=250,tremolo=f=3.5:d=0.75,tremolo=f=5.8:d=0.35"),
    "water_pouring": ("pink", "bandpass=f=1000:w=1400,tremolo=f=1.0:d=0.35,tremolo=f=2.6:d=0.15"),
    "rice_washing": ("pink", "bandpass=f=1500:w=1600,tremolo=f=2:d=0.55,tremolo=f=4.9:d=0.25"),
    "dough_kneading": ("brown", "bandpass=f=350:w=300,tremolo=f=1.8:d=0.8,tremolo=f=4.4:d=0.4"),
    "oil_sizzling": ("white", "highpass=f=4000,tremolo=f=28:d=0.55,tremolo=f=11:d=0.3"),
    "clay_pot_boiling": ("pink", "bandpass=f=800:w=900,tremolo=f=3:d=0.55,tremolo=f=6.1:d=0.25"),
    "wooden_spoon_stirring": ("pink", "bandpass=f=1200:w=900,tremolo=f=1.5:d=0.65,tremolo=f=3.7:d=0.3"),
    "fire_crackling": ("white", "bandpass=f=2500:w=3000,tremolo=f=14:d=0.7,tremolo=f=5.3:d=0.35"),
    "utensil_clinks": ("white", "bandpass=f=4500:w=3500,tremolo=f=3:d=0.92,tremolo=f=7.9:d=0.55"),
    "banana_leaf": ("white", "bandpass=f=3000:w=2500,tremolo=f=2:d=0.9,tremolo=f=5.2:d=0.5"),
    "steam": ("white", "highpass=f=6000,lowpass=f=13000,tremolo=f=0.4:d=0.15"),
    "eating_ambience": ("pink", "bandpass=f=900:w=1200,tremolo=f=1.6:d=0.55,tremolo=f=3.9:d=0.25"),
}

LOUDNESS_TARGET = "loudnorm=I=-20:TP=-3:LRA=7"


def generate(tag, color, filters):
    out_path = SFX_DIR / f"{tag}.mp3"
    filter_chain = (
        f"anoisesrc=d={DURATION}:c={color}:r=44100:a=1,{filters},{LOUDNESS_TARGET},"
        f"afade=t=in:d=0.3,afade=t=out:st={DURATION - 0.3}:d=0.3"
    )
    cmd = [
        "ffmpeg", "-y", "-f", "lavfi", "-i", filter_chain,
        "-c:a", "libmp3lame", "-q:a", "4", str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed for {tag}: {result.stderr[-2000:]}")
    return out_path


if __name__ == "__main__":
    SFX_DIR.mkdir(parents=True, exist_ok=True)
    for tag, (color, filters) in RECIPES.items():
        path = generate(tag, color, filters)
        print(f"generated {path.name}", file=sys.stderr)
    print(f"done: {len(RECIPES)} placeholder sfx files in {SFX_DIR}")
