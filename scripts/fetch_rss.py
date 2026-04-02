"""
Step 1: Fetch the latest episode from each podcast in sources.json.
        Only downloads episodes published within max_age_hours (default 24h).
        Acast sphinx.acast.com URLs are rewritten to feeds.acast.com to avoid 403s.
        Failed downloads are skipped gracefully — pipeline continues.
"""

import json
import os
import re
import feedparser
import requests
from pathlib import Path
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# FT News Briefing stream ID on Acast (constant — only episode ID changes)
ACAST_STREAM_IDS = {
    "ftnewsbriefing": "621e1a5bf5df83377cc948b8",
}


def rewrite_acast_url(url):
    """
    Rewrite blocked sphinx.acast.com URLs to the working feeds.acast.com format.
    sphinx.acast.com/p/acast/s/{show}/e/{episode_id}/media.mp3
      → feeds.acast.com/public/streams/{stream_id}/episodes/{episode_id}.mp3
    """
    match = re.search(r"sphinx\.acast\.com/p/acast/s/([^/]+)/e/([^/]+)/media\.mp3", url)
    if match:
        show_slug = match.group(1)
        episode_id = match.group(2)
        stream_id = ACAST_STREAM_IDS.get(show_slug)
        if stream_id:
            new_url = f"https://feeds.acast.com/public/streams/{stream_id}/episodes/{episode_id}.mp3"
            print(f"  🔀 Rewrote Acast URL → {new_url[:80]}")
            return new_url
    return url


def fetch_latest_episodes():
    with open("sources.json", "r") as f:
        sources = json.load(f)

    os.makedirs("temp/audio", exist_ok=True)
    downloaded = []
    skipped = []
    failed = []

    for source in sources:
        name = source["name"]
        max_age_hours = source.get("max_age_hours", 24)
        priority = source.get("priority", 5)

        print(f"\n[RSS] Fetching: {name}", flush=True)

        try:
            feed = feedparser.parse(source["rss"])

            if not feed.entries:
                print(f"  ⚠️  No entries found", flush=True)
                continue

            latest = feed.entries[0]

            # Parse published date
            pub_date = None
            if latest.get("published"):
                try:
                    pub_date = parsedate_to_datetime(latest["published"])
                    if pub_date.tzinfo is None:
                        pub_date = pub_date.replace(tzinfo=timezone.utc)
                except Exception:
                    pub_date = None

            # Check age
            if pub_date:
                age_hours = (datetime.now(timezone.utc) - pub_date).total_seconds() / 3600
                if age_hours > max_age_hours:
                    print(f"  ⏭️  Skipping — {age_hours:.0f}h old (limit: {max_age_hours}h)", flush=True)
                    skipped.append(name)
                    continue
                print(f"  ✅ Episode age: {age_hours:.1f}h — within limit", flush=True)
            else:
                print(f"  ⚠️  No publish date — downloading anyway", flush=True)

            # Find MP3 URL
            mp3_url = None
            for enclosure in latest.get("enclosures", []):
                if "audio" in enclosure.get("type", ""):
                    mp3_url = enclosure["url"]
                    break

            if not mp3_url:
                print(f"  ⚠️  No audio enclosure found", flush=True)
                continue

            # Rewrite blocked Acast URLs
            mp3_url = rewrite_acast_url(mp3_url)

            # Download
            safe_name = (
                name.replace(" ", "_")
                    .replace("'", "").replace("'", "")
                    .replace("/", "_").replace("-", "_")
            )
            filename = f"temp/audio/{safe_name}.mp3"

            print(f"  ⬇️  Downloading: {mp3_url[:80]}...", flush=True)
            response = requests.get(
                mp3_url, stream=True, timeout=120,
                headers=HEADERS, allow_redirects=True
            )
            response.raise_for_status()

            with open(filename, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            size_mb = os.path.getsize(filename) / (1024 * 1024)
            print(f"  💾 Saved {filename} ({size_mb:.1f} MB)", flush=True)

            downloaded.append({
                "name": name,
                "file": filename,
                "title": latest.get("title", ""),
                "date": latest.get("published", ""),
                "priority": priority,
            })

        except requests.exceptions.HTTPError as e:
            print(f"  ❌ HTTP error: {e} — skipping", flush=True)
            failed.append(name)
        except requests.exceptions.ConnectionError as e:
            print(f"  ❌ Connection error: {e} — skipping", flush=True)
            failed.append(name)
        except Exception as e:
            print(f"  ❌ Unexpected error: {e} — skipping", flush=True)
            failed.append(name)

    # Sort by priority
    downloaded.sort(key=lambda x: x.get("priority", 5))

    with open("temp/episodes.json", "w") as f:
        json.dump(downloaded, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*50}", flush=True)
    print(f"✅ Downloaded : {len(downloaded)} episode(s)", flush=True)
    print(f"⏭️  Skipped   : {len(skipped)} stale episode(s)", flush=True)
    print(f"❌ Failed     : {len(failed)} episode(s) {failed if failed else ''}", flush=True)

    if not downloaded:
        raise RuntimeError("No episodes downloaded. Nothing to transcribe.")

    return downloaded


if __name__ == "__main__":
    fetch_latest_episodes()
