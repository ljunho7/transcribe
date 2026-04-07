"""
Step 6: Upload the assembled MP4 to YouTube using the Data API v3.
        Uses a stored OAuth refresh token (set once, works forever).

Required GitHub Secrets:
    YOUTUBE_CLIENT_ID
    YOUTUBE_CLIENT_SECRET
    YOUTUBE_REFRESH_TOKEN
"""

import os
from datetime import datetime, timezone, timedelta
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


VIDEO_FILE = "temp/final_video.mp4"


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
        scopes=["https://www.googleapis.com/auth/youtube.upload"],
    )
    creds.refresh(Request())

    youtube = build("youtube", "v3", credentials=creds)

    # Generate title and description from today's date and script preview
    KST = timezone(timedelta(hours=9))
    today_kr = datetime.now(KST).strftime("%Y년 %m월 %d일")
    today_en = datetime.now(KST).strftime("%Y-%m-%d")

    with open("temp/korean_script.txt", "r", encoding="utf-8") as f:
        full_script = f.read().strip()

    # YouTube description limit is 5,000 chars
    # Header + script + tags, truncate script if needed
    header = f"📰 {today_kr} 주요 글로벌 뉴스를 한국어로 요약해드립니다.\n\n"
    footer = f"\n\n#뉴스 #한국어뉴스 #글로벌뉴스 #경제뉴스 #시사 #{today_en.replace('-', '')}"
    max_script = 5000 - len(header) - len(footer) - 50  # safety margin
    script_text = full_script[:max_script]
    if len(full_script) > max_script:
        script_text += "\n\n(전체 스크립트는 자막을 켜주세요)"

    body = {
        "snippet": {
            "title": f"오늘의 글로벌 뉴스 요약 | {today_kr}",
            "description": header + script_text + footer,
            "tags": ["뉴스", "한국어뉴스", "글로벌뉴스", "경제", "시사", "뉴스요약"],
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


if __name__ == "__main__":
    upload_to_youtube()
