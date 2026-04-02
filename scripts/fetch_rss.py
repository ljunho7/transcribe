"""
Step 1: Fetch the latest episode from each podcast in sources.json
        Downloads MP3s to temp/audio/ and saves metadata to temp/episodes.json
"""

import json
import os
import feedparser
import requests
from pathlib import Path


def fetch_latest_episodes():
    with open("sources.json", "r") as f:
        sources = json.load(f)

    os.makedirs("temp/audio", exist_ok=True)
    downloaded = []

    for source in sources:
        print(f"[RSS] Fetching: {source['name']}")
        feed = feedparser.parse(source["rss"])

        if not feed.entries:
            print(f"  ⚠️  No entries found for {source['name']}")
            continue

        latest = feed.entries[0]

        # Find the MP3 enclosure URL
        mp3_url = None
        for enclosure in latest.get("enclosures", []):
            if "audio" in enclosure.get("type", ""):
                mp3_url = enclosure["url"]
                break

        if not mp3_url:
            print(f"  ⚠️  No audio enclosure found for {source['name']}")
            continue

        # Build a safe filename
        safe_name = source["name"].replace(" ", "_").replace("'", "").replace("'", "")
        filename = f"temp/audio/{safe_name}.mp3"

        print(f"  Downloading: {mp3_url[:80]}...")
        response = requests.get(mp3_url, stream=True, timeout=120)
        response.raise_for_status()

        with open(filename, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        size_mb = os.path.getsize(filename) / (1024 * 1024)
        print(f"  ✅ Saved {filename} ({size_mb:.1f} MB)")

        downloaded.append({
            "name": source["name"],
            "file": filename,
            "title": latest.get("title", ""),
            "date": latest.get("published", ""),
        })

    # Save metadata for downstream steps
    with open("temp/episodes.json", "w") as f:
        json.dump(downloaded, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Downloaded {len(downloaded)} episode(s).")
    return downloaded


if __name__ == "__main__":
    fetch_latest_episodes()
