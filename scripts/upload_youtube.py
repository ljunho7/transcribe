"""
Step 6: Upload the assembled MP4 to YouTube using the Data API v3.
        Uses a stored OAuth refresh token (set once, works forever).

Required GitHub Secrets:
    YOUTUBE_CLIENT_ID
    YOUTUBE_CLIENT_SECRET
    YOUTUBE_REFRESH_TOKEN
"""

import json, os
from datetime import datetime, timezone, timedelta
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


VIDEO_FILE    = "temp/final_video.mp4"
SUBTITLE_FILE = "temp/subtitles.srt"


def upload_to_youtube():
    if not os.path.exists(VIDEO_FILE):
        raise FileNotFoundError(f"Video file not found: {VIDEO_FILE}")

    # Build OAuth credentials from stored refresh token
    creds = Credentials(
        token=None,
        refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
        client_id=os.environ["YOUTUBE_CLIENT_ID"],
        client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
        scopes=[
            "https://www.googleapis.com/auth/youtube.upload",
            "https://www.googleapis.com/auth/youtube.force-ssl",
        ],
    )
    creds.refresh(Request())

    youtube = build("youtube", "v3", credentials=creds)

    # Generate title and description from today's date and script preview
    KST = timezone(timedelta(hours=9))
    today_kr = datetime.now(KST).strftime("%Y년 %m월 %d일")
    today_en = datetime.now(KST).strftime("%Y-%m-%d")

    with open("temp/korean_script.txt", "r", encoding="utf-8") as f:
        full_script = f.read().strip()

    # Load video metadata (chapters + auto-tags) if available
    video_meta = {}
    if os.path.exists("temp/video_metadata.json"):
        with open("temp/video_metadata.json", "r", encoding="utf-8") as f:
            video_meta = json.load(f)

    chapter_text = video_meta.get("chapter_text", "")
    auto_tags = video_meta.get("tags", [])

    # Merge auto-tags with default tags (deduplicated)
    default_tags = ["뉴스", "한국어뉴스", "글로벌뉴스", "경제", "시사", "뉴스요약"]
    all_tags = list(dict.fromkeys(default_tags + auto_tags))[:30]  # YouTube max 30 tags

    # YouTube description: header + chapters + script + tags
    header = f"📰 {today_kr} 주요 글로벌 뉴스를 한국어로 요약해드립니다.\n\n"
    chapters_section = f"📌 목차\n{chapter_text}\n\n" if chapter_text else ""
    footer = f"\n\n#뉴스 #한국어뉴스 #글로벌뉴스 #경제뉴스 #시사 #{today_en.replace('-', '')}"

    # Fit script within 5,000 char limit
    max_script = 5000 - len(header) - len(chapters_section) - len(footer) - 50
    script_text = full_script[:max_script]
    if len(full_script) > max_script:
        script_text += "\n\n(전체 스크립트는 자막을 켜주세요)"

    body = {
        "snippet": {
            "title": f"오늘의 글로벌 뉴스 요약 | {today_kr}",
            "description": header + chapters_section + script_text + footer,
            "tags": all_tags,
            "categoryId": "25",  # News & Politics
            "defaultLanguage": "ko",
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
        },
    }

    print(f"[YouTube] Uploading: {body['snippet']['title']}")

    media = MediaFileUpload(VIDEO_FILE, mimetype="video/mp4", resumable=True, chunksize=4 * 1024 * 1024)

    request = youtube.videos().insert(
        part=",".join(body.keys()),
        body=body,
        media_body=media,
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            pct = int(status.progress() * 100)
            print(f"  Upload progress: {pct}%")

    video_id = response["id"]
    print(f"\n✅ Upload complete!")
    print(f"   Video ID : {video_id}")
    print(f"   URL      : https://www.youtube.com/watch?v={video_id}")

    # Upload subtitles if available
    if os.path.exists(SUBTITLE_FILE):
        upload_captions(youtube, video_id)
    else:
        print(f"  ⚠️  No subtitle file found: {SUBTITLE_FILE}")


def upload_captions(youtube, video_id):
    """Upload SRT subtitles to a YouTube video."""
    try:
        print(f"\n📝 Uploading subtitles for {video_id}...", flush=True)

        caption_body = {
            "snippet": {
                "videoId": video_id,
                "language": "ko",
                "name": "Korean",
                "isDraft": False,
            }
        }

        media = MediaFileUpload(
            SUBTITLE_FILE,
            mimetype="application/x-subrip",
            resumable=False,
        )

        youtube.captions().insert(
            part="snippet",
            body=caption_body,
            media_body=media,
        ).execute()

        print(f"  ✅ Subtitles uploaded successfully", flush=True)

    except Exception as e:
        print(f"  ⚠️  Subtitle upload failed (non-blocking): {e}", flush=True)


if __name__ == "__main__":
    upload_to_youtube()
