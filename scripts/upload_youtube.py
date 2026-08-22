"""Upload the finished video to YouTube via the Data API v3 using a stored refresh token.

Requires env vars YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN (see
scripts/get_youtube_refresh_token.py for how to obtain the refresh token once, manually).
"""

import json
import os
import sys
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

TOKEN_URI = "https://oauth2.googleapis.com/token"
SCOPES = ["https://www.googleapis.com/auth/youtube"]


def get_credentials():
    return Credentials(
        token=None,
        refresh_token=os.environ["YT_REFRESH_TOKEN"],
        client_id=os.environ["YT_CLIENT_ID"],
        client_secret=os.environ["YT_CLIENT_SECRET"],
        token_uri=TOKEN_URI,
        scopes=SCOPES,
    )


def upload_video(video_path, story, privacy_status, category_id):
    creds = get_credentials()
    youtube = build("youtube", "v3", credentials=creds)

    title = story["video_title"][:100]
    description = story["video_description"]
    tags = story.get("tags", [])

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(video_path, chunksize=-1, resumable=True, mimetype="video/mp4")
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"[upload_youtube] upload progress: {int(status.progress() * 100)}%", file=sys.stderr)

    return response


if __name__ == "__main__":
    video_path_arg, story_path_arg = sys.argv[1], sys.argv[2]
    story = json.loads(Path(story_path_arg).read_text(encoding="utf-8"))

    root = Path(__file__).resolve().parent.parent
    config = json.loads((root / "config.json").read_text(encoding="utf-8"))

    result = upload_video(
        video_path_arg, story, config["youtube_privacy_status"], config["youtube_category_id"]
    )
    video_id = result["id"]
    print(f"https://youtube.com/shorts/{video_id}")
