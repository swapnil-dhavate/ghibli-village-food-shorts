# Ghibli Village Food Shorts — autonomous daily pipeline

Every day, GitHub Actions:
1. Picks a new Indian regional dish (no repeats until the whole catalog cycles — `data/dish_catalog.json` / `data/state/used_dishes.json`).
2. Asks Gemini (free tier) to write a wordless, scene-by-scene story + image prompts for a vertical Studio Ghibli-style ASMR short, using a fixed character bible (`scripts/constants.py`) for consistency.
3. Generates one still image per scene via Pollinations.ai (free, no key).
4. Assembles a vertical video with ffmpeg: Ken Burns pan/zoom per scene, crossfade transitions, and an ASMR sound bed mixed from `assets/sfx/`.
5. Uploads the result to your YouTube channel via the Data API v3.

## Known limitations (read before you trust the output)

- **No true generative motion.** There's no free API for actual AI video generation (rain
  falling, faces blinking, etc.) without a paid tier. Motion here is ffmpeg pan/zoom/crossfade
  over still images — the ASMR sound design carries a lot of the "alive" feeling.
- **Character consistency will drift.** Every scene's image prompt restates the same character
  bible in words, which is the only real lever without a trained LoRA (that needs a GPU to
  train). Expect the family to look *similar*, not pixel-identical, across scenes.
- **YouTube policy risk.** A channel publishing daily, fully AI-generated, zero human review can
  read as "reused/repetitious content" to YouTube's spam policies. `config.json` defaults
  `youtube_privacy_status` to `"unlisted"` on purpose — watch the first several runs yourself
  before flipping it to `"public"`.
- **Free-tier quotas.** Gemini's free tier and Pollinations.ai both have rate limits. One run/day
  should comfortably fit; don't lower the cron interval without checking quotas.

## One-time setup (you have to do this manually — I can't do it for you)

### 1. Gemini API key (free)
Go to https://aistudio.google.com/apikey, create a key. This becomes the `GEMINI_API_KEY`
secret.

### 2. YouTube Data API v3 access
1. In Google Cloud Console, create a project → enable **YouTube Data API v3**.
2. Create an **OAuth 2.0 Client ID** of type **Desktop app**. Note the client ID and secret.
3. On your own machine (not CI), run the one-time helper to mint a refresh token:
   ```
   pip install google-auth-oauthlib
   set YT_CLIENT_ID=...
   set YT_CLIENT_SECRET=...
   python scripts/get_youtube_refresh_token.py
   ```
   This opens a browser — log into the Google account that owns your YouTube channel and
   approve the upload scope. It prints a refresh token.

### 3. Add GitHub secrets
In the repo's Settings → Secrets and variables → Actions, add:
- `GEMINI_API_KEY`
- `YT_CLIENT_ID`
- `YT_CLIENT_SECRET`
- `YT_REFRESH_TOKEN`

### 4. Add ASMR sound effects
See `assets/sfx/README.md` — the pipeline runs without them (falls back to silence per scene)
but the whole point is ASMR, so add them before you care about output quality.

### 5. Push and enable Actions
Push this repo to GitHub, then check the **Actions** tab is enabled. Use **Run workflow**
(workflow_dispatch) to trigger a manual test run before waiting for the daily cron.

## Tuning
- `config.json`: `scene_count`, `video_duration_seconds`, output resolution, image model,
  and `youtube_privacy_status` (flip to `"public"` once you're happy with quality).
- `.github/workflows/daily_video.yml`: cron schedule (`0 5 * * *` = 05:00 UTC daily).
- `data/dish_catalog.json`: add more dishes any time to extend the no-repeat rotation.

## Local testing
```
pip install -r requirements.txt
set GEMINI_API_KEY=...
python scripts/run_pipeline.py
```
Requires `ffmpeg` on PATH. Output lands in `work/<date>/`.
