# Narrated Topic Shorts — autonomous daily pipeline

Every day, GitHub Actions:
1. Picks a new general-interest topic (history/science/nature/mystery — no repeats until the
   whole catalog cycles: `data/topic_catalog.json` / `data/state/used_topics.json`).
2. Asks Gemini (free tier) to research the topic (from its own training knowledge, no external
   search) and write a hook-first narrated script + scene breakdown, vertical 9:16.
3. Synthesizes narration audio per scene with **Piper TTS** — free, open-source, runs entirely
   offline/on-CPU inside the job itself, no API key or account.
4. Generates one still image per scene via Pollinations.ai's free `flux` model (all scenes share
   one seed per video for style consistency — see `scripts/generate_images.py`).
5. Assembles a vertical video with ffmpeg: Ken Burns pan/zoom sized to each scene's actual
   narration length, a 3-way audio mix (narration + low-volume ambient SFX + a looped background
   music bed), an opening title card, and burned-in captions synced to the narration.
6. Uploads to YouTube via the Data API v3 as **unlisted** by default — this is the human-approval
   gate: a person reviews the video and manually flips it to public in YouTube Studio. Runs
   daily at 03:30 UTC (09:00 IST) via cron, or on demand via the Actions tab.

This replaced an earlier wordless, food-only ASMR format (character bible, dish catalog, no
narration, fully autonomous public publish) — see `PROJECT_LOG.md` for that history and why it
changed. The old dish catalog/rotation-state files are kept in the repo as a historical record
but are no longer used by the pipeline.

## Known limitations (read before you trust the output)

- **No true generative motion.** There's no free API for actual AI video generation (verified
  directly against real accounts — every hosted video/image-to-video/TTS model that isn't
  plain-text-to-still-image is paid, no exceptions found). Motion here is ffmpeg pan/zoom/
  crossfade over still images.
- **Character/scene consistency will drift** across scenes and across videos — same-seed-per-
  video helps within one video, but there's no trained model or reference-image conditioning
  (the free `kontext` image-to-image model exists but costs ~$0.04/image with no free grant —
  see `generate_images.py`'s docstring).
- **Piper narration is a synthesized voice**, not a real human recording — verified it works and
  sounds reasonably natural (VITS neural TTS, not old robotic TTS), but it's not a substitute
  for professional voiceover.
- **SFX and music**: SFX are synthetic noise-based placeholders (`assets/sfx/`); music tracks
  are real royalty-free files you source yourself into `assets/music/` (see that folder's
  README) — the pipeline degrades gracefully (silence) if either is missing for a given tag/mood.
- **QC isn't perfect.** The Gemini vision QC step catches many off-prompt image renders and
  retries with a new seed, but if every retry still fails, the run fails loudly rather than
  publishing a confirmed-mismatched image (by design — see `generate_images.py`).
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

(`POLLINATIONS_API_KEY` also exists as a secret from an earlier experiment with the paid
`kontext` model — currently unused by the pipeline, harmless to leave or remove.)

### 4. Background music (optional but recommended)
See `assets/music/README.md` — drop free, royalty-free tracks named `calm.mp3`, `cozy.mp3`,
`upbeat.mp3`, `curious.mp3`, `emotional.mp3`. The pipeline runs without them (falls back to no
music for a given mood) but real music is a large quality jump over nothing.

### 5. Push and enable Actions
Push this repo to GitHub, then check the **Actions** tab is enabled. Use **Run workflow**
(workflow_dispatch) to trigger a manual test run before waiting for the daily cron.

## Human approval workflow

Every video uploads as **unlisted**. To publish: open the video's YouTube Studio page, review
it, and change visibility to Public yourself. Nothing publishes automatically without that
manual step (this is a deliberate change from an earlier fully-autonomous-public version).

## Tuning
- `config.json`: `scene_count`, output resolution, image model, `youtube_privacy_status`
  (`"unlisted"` by design — see above).
- `.github/workflows/daily_video.yml`: cron schedule (`30 3 * * *` = 03:30 UTC = 09:00 IST daily).
- `data/topic_catalog.json`: add more topics any time to extend the no-repeat rotation.
- `scripts/assemble_video.py`: `SFX_VOLUME`/`MUSIC_VOLUME`/`PADDING_SECONDS` control the audio
  mix balance and per-scene pacing.

## Local testing
```
pip install -r requirements.txt
set GEMINI_API_KEY=...
python scripts/run_pipeline.py
```
Requires `ffmpeg` on PATH (with `fonts-dejavu-core`/DejaVu Sans Bold available for the title
card and captions). Output lands in `work/<date>/`.
