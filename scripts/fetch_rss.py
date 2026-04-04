"""
Step 1: Fetch the latest episode from each podcast in sources.json.
        - Only downloads episodes within max_age_hours
        - For feeds with multiple daily episodes (WSJ, Bloomberg),
          picks the most recently published one automatically
        - Acast sphinx.acast.com URLs rewritten to feeds.acast.com
        - Failed downloads skipped gracefully
"""

import json
import os
import re
import feedparser
import requests
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

ACAST_STREAM_IDS = {
    "ftnewsbriefing": "621e1a5bf5df83377cc948b8",
}

# Feeds that publish multiple episodes per day
# We scan the top N entries and pick the most recently published one
# that is within max_age_hours
MULTI_EPISODE_FEEDS = {
    "WSJ What's News",
    "Bloomberg Daybreak US",
    "Bloomberg Daybreak Asia",
}


def rewrite_acast_url(url):
    match = re.search(r"sphinx\.acast\.com/p/acast/s/([^/]+)/e/([^/]+)/media\.mp3", url)
    if match:
        show_slug = match.group(1)
        episode_id = match.group(2)
        stream_id = ACAST_STREAM_IDS.get(show_slug)
        if stream_id:
            new_url = f"https://feeds.acast.com/public/streams/{stream_id}/episodes/{episode_id}.mp3"
            print(f"  🔀 Rewrote Acast URL → {new_url[:80]}", flush=True)
            return new_url
    return url


def parse_pub_date(entry):
    """Parse published date from a feed entry. Returns datetime or None."""
    if entry.get("published"):
        try:
            pub_date = parsedate_to_datetime(entry["published"])
            if pub_date.tzinfo is None:
                pub_date = pub_date.replace(tzinfo=timezone.utc)
            return pub_date
        except Exception:
            pass
    return None


def pick_episode(feed, name, max_age_hours):
    """
    Pick the best episode from a feed.
    - For multi-episode feeds: scan top 10 entries, pick the most recently
      published one within max_age_hours.
    - For single-episode feeds: just take entries[0] if within max_age_hours.
    Returns (entry, age_hours) or (None, None).
    """
    now = datetime.now(timezone.utc)
    entries = feed.entries[:10]

    if name in MULTI_EPISODE_FEEDS:
        # Sort by publish date descending, pick newest within limit
        dated = []
        for entry in entries:
            pub_date = parse_pub_date(entry)
            if pub_date:
                age_h = (now - pub_date).total_seconds() / 3600
                dated.append((age_h, entry))

        dated.sort(key=lambda x: x[0])  # Newest first (smallest age)

        for age_h, entry in dated:
            if age_h <= max_age_hours:
                return entry, age_h

        return None, None
    else:
        # Standard: just check the latest entry
        if not entries:
            return None, None
        entry = entries[0]
        pub_date = parse_pub_date(entry)
        if pub_date:
            age_h = (now - pub_date).total_seconds() / 3600
            if age_h <= max_age_hours:
                return entry, age_h
            return None, None
        return entry, None  # No date — include anyway


def fetch_latest_episodes():
    with open("sources.json", "r") as f:
        sources = json.load(f)

    os.makedirs("temp/audio", exist_ok=True)

    # On Sunday UTC (Monday KST), extend max_age to 48hr to cover Saturday podcasts
    import datetime
    is_sunday_utc = datetime.datetime.utcnow().weekday() == 6  # 6 = Sunday
    age_multiplier = 2 if is_sunday_utc else 1
    if is_sunday_utc:
        print("📅 Sunday UTC detected — using 48hr podcast age limit", flush=True)
    downloaded = []
    skipped = []
    failed = []

    for source in sources:
        name = source["name"]
        max_age_hours = source.get("max_age_hours", 24) * age_multiplier
        priority = source.get("priority", 5)

        print(f"\n[RSS] Fetching: {name}", flush=True)

        try:
            feed = feedparser.parse(source["rss"])

            if not feed.entries:
                print(f"  ⚠️  No entries found", flush=True)
                continue

            latest, age_h = pick_episode(feed, name, max_age_hours)

            if latest is None:
                print(f"  ⏭️  No episode within {max_age_hours}h limit — skipping", flush=True)
                skipped.append(name)
                continue

            title = latest.get("title", "")
            if age_h is not None:
                print(f"  ✅ '{title}' — {age_h:.1f}h old", flush=True)
            else:
                print(f"  ✅ '{title}' — (no publish date)", flush=True)

            # Find MP3 URL
            mp3_url = None
            for enclosure in latest.get("enclosures", []):
                if "audio" in enclosure.get("type", ""):
                    mp3_url = enclosure["url"]
                    break

            if not mp3_url:
                print(f"  ⚠️  No audio enclosure found", flush=True)
                continue

            mp3_url = rewrite_acast_url(mp3_url)

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
                "title": title,
                "date": latest.get("published", ""),
                "priority": priority,
            })

        except requests.exceptions.HTTPError as e:
            print(f"  ❌ HTTP error: {e} — skipping", flush=True)
            failed.append(name)
        except Exception as e:
            print(f"  ❌ Error: {e} — skipping", flush=True)
            failed.append(name)

    downloaded.sort(key=lambda x: x.get("priority", 5))

    with open("temp/episodes.json", "w") as f:
        json.dump(downloaded, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*50}", flush=True)
    print(f"✅ Downloaded : {len(downloaded)} episode(s)", flush=True)
    print(f"⏭️  Skipped   : {len(skipped)} — {skipped if skipped else ''}", flush=True)
    print(f"❌ Failed     : {len(failed)} — {failed if failed else ''}", flush=True)

    if not downloaded:
        raise RuntimeError("No episodes downloaded.")

    return downloaded


if __name__ == "__main__":
    fetch_latest_episodes()
