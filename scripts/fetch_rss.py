"""
Step 1: Fetch the latest episode from each podcast in sources.json.
        Only downloads episodes published within max_age_hours (default 24h).
        Failed downloads are skipped gracefully — pipeline continues.
"""

import json
import os
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

        print(f"\n[RSS] Fetching: {name}")

        try:
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
                print(f"  ⚠️  No publish date, downloading anyway")

            # Find MP3 URL
            mp3_url = None
            for enclosure in latest.get("enclosures", []):
                if "audio" in enclosure.get("type", ""):
                    mp3_url = enclosure["url"]
                    break

            if not mp3_url:
                print(f"  ⚠️  No audio enclosure found")
                continue

            # Download with browser-like headers
            safe_name = (
                name.replace(" ", "_")
                    .replace("'", "").replace("'", "")
                    .replace("/", "_").replace("-", "_")
            )
            filename = f"temp/audio/{safe_name}.mp3"

            print(f"  ⬇️  Downloading: {mp3_url[:80]}...")
            response = requests.get(
                mp3_url, stream=True, timeout=120,
                headers=HEADERS, allow_redirects=True
            )
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

        except requests.exceptions.HTTPError as e:
            print(f"  ❌ HTTP error: {e} — skipping")
            failed.append(name)
        except requests.exceptions.ConnectionError as e:
            print(f"  ❌ Connection error: {e} — skipping")
            failed.append(name)
        except Exception as e:
            print(f"  ❌ Unexpected error: {e} — skipping")
            failed.append(name)

    # Sort by priority
    downloaded.sort(key=lambda x: x.get("priority", 5))

    with open("temp/episodes.json", "w") as f:
        json.dump(downloaded, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*50}")
    print(f"✅ Downloaded : {len(downloaded)} episode(s)")
    print(f"⏭️  Skipped   : {len(skipped)} stale episode(s)")
    print(f"❌ Failed     : {len(failed)} episode(s) {failed if failed else ''}")

    if not downloaded:
        raise RuntimeError("No episodes downloaded. Nothing to transcribe.")

    return downloaded


if __name__ == "__main__":
    fetch_latest_episodes()
