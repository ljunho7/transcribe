"""
Step 1: Fetch the latest episode from each podcast in sources.json.
        Only downloads episodes published within max_age_hours (default 24h).
        This prevents downloading stale weekly episodes and keeps Groq usage low.
        Downloads MP3s to temp/audio/ and saves metadata to temp/episodes.json
"""

import json
import os
import time
import feedparser
import requests
from pathlib import Path
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime


def fetch_latest_episodes():
    with open("sources.json", "r") as f:
        sources = json.load(f)

    os.makedirs("temp/audio", exist_ok=True)
    downloaded = []
    skipped = []

    for source in sources:
        name = source["name"]
        max_age_hours = source.get("max_age_hours", 24)
        priority = source.get("priority", 5)

        print(f"[RSS] Fetching: {name}")
        feed = feedparser.parse(source["rss"])

        if not feed.entries:
            print(f"  ⚠️  No entries found")
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
                print(f"  ⏭️  Skipping — episode is {age_hours:.0f}h old (limit: {max_age_hours}h)")
                skipped.append(name)
                continue
            print(f"  ✅ Episode age: {age_hours:.1f}h — within limit")
        else:
            print(f"  ⚠️  No publish date found, downloading anyway")

        # Find MP3 URL
        mp3_url = None
        for enclosure in latest.get("enclosures", []):
            if "audio" in enclosure.get("type", ""):
                mp3_url = enclosure["url"]
                break

        if not mp3_url:
            print(f"  ⚠️  No audio enclosure found")
            continue

        # Download
        safe_name = (
            name.replace(" ", "_")
                .replace("'", "")
                .replace("'", "")
                .replace("/", "_")
                .replace("-", "_")
        )
        filename = f"temp/audio/{safe_name}.mp3"

        print(f"  ⬇️  Downloading: {mp3_url[:80]}...")
        response = requests.get(mp3_url, stream=True, timeout=120)
        response.raise_for_status()

        with open(filename, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        size_mb = os.path.getsize(filename) / (1024 * 1024)
        print(f"  💾 Saved {filename} ({size_mb:.1f} MB)")

        downloaded.append({
            "name": name,
            "file": filename,
            "title": latest.get("title", ""),
            "date": latest.get("published", ""),
            "priority": priority,
        })

    # Sort by priority (lower number = higher priority)
    downloaded.sort(key=lambda x: x.get("priority", 5))

    # Save metadata
    with open("temp/episodes.json", "w") as f:
        json.dump(downloaded, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Downloaded {len(downloaded)} episode(s). Skipped {len(skipped)} stale episode(s).")
    if skipped:
        print(f"   Skipped: {', '.join(skipped)}")

    if not downloaded:
        raise RuntimeError("No episodes downloaded. Nothing to transcribe.")

    return downloaded


if __name__ == "__main__":
    fetch_latest_episodes()
