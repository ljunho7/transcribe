#!/usr/bin/env python3
"""
Step 5.5: Analyze final video with Google Cloud Video Intelligence API.
Generates:
  1. YouTube chapters (from shot detection + manifest timing)
  2. Auto-generated tags (from label detection)
  3. Saves results to temp/video_metadata.json for upload_youtube.py

Free tier: 1,000 minutes/month. Usage: ~6 min/day = ~130 min/month.
"""

import json, os, sys, time
from pathlib import Path

VIDEO_FILE    = "temp/final_video.mp4"
METADATA_FILE = "temp/video_metadata.json"
MANIFEST_FILE = "temp/audio/manifest.json"

SECTION_LABELS = {
    "[시장개요]": "시장개요",
    "[뉴스]":     "뉴스",
    "[리서치]":   "리서치",
    "[주요등락]": "주요 등락",
    "[섹터분석]": "섹터 분석",
    "[국가별]":   "국가별 동향",
    "[경제일정]": "경제 일정",
}


def generate_chapters_from_manifest():
    """Generate YouTube chapter timestamps from manifest audio durations."""
    if not os.path.exists(MANIFEST_FILE):
        print("  ⚠️  No manifest file — cannot generate chapters", flush=True)
        return []

    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    chapters = []
    elapsed = 0.0

    for entry in manifest:
        audio_path = Path(entry["audio"])
        section = entry["section"]
        headline = entry.get("headline", "")

        # Get duration
        if audio_path.exists():
            import subprocess
            result = subprocess.run([
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(audio_path)
            ], capture_output=True, text=True)
            try:
                dur = float(result.stdout.strip())
            except ValueError:
                dur = 30.0
        else:
            dur = 30.0

        # Build chapter label
        if section in ("[뉴스]", "[리서치]"):
            label = headline if headline else SECTION_LABELS.get(section, section)
        else:
            label = SECTION_LABELS.get(section, section.strip("[]"))

        # Format timestamp as MM:SS
        mins = int(elapsed // 60)
        secs = int(elapsed % 60)
        timestamp = f"{mins}:{secs:02d}"

        chapters.append({
            "timestamp": timestamp,
            "label": label,
            "seconds": round(elapsed, 1),
        })

        elapsed += dur

    print(f"  📑 Generated {len(chapters)} chapters", flush=True)
    return chapters


def analyze_video_labels():
    """Use Google Cloud Video Intelligence to auto-detect labels/tags."""
    try:
        from google.cloud import videointelligence
    except ImportError:
        print("  ⚠️  google-cloud-videointelligence not installed — skipping label detection", flush=True)
        return []

    if not os.path.exists(VIDEO_FILE):
        print(f"  ⚠️  Video not found: {VIDEO_FILE}", flush=True)
        return []

    try:
        client = videointelligence.VideoIntelligenceServiceClient()

        with open(VIDEO_FILE, "rb") as f:
            input_content = f.read()

        print("  🔍 Analyzing video for labels (this may take 1-2 minutes)...", flush=True)

        operation = client.annotate_video(
            request={
                "features": [videointelligence.Feature.LABEL_DETECTION],
                "input_content": input_content,
            }
        )

        # Wait for completion (typically 30-120 seconds)
        result = operation.result(timeout=300)

        # Extract labels
        labels = set()
        for annotation in result.annotation_results:
            for label in annotation.segment_label_annotations:
                name = label.entity.description
                # Filter for relevant labels
                if label.segments and label.segments[0].confidence > 0.5:
                    labels.add(name)

        # Add Korean financial tags
        ko_tags = ["뉴스", "경제", "금융", "증시", "주식", "투자", "시사", "글로벌뉴스"]
        all_tags = list(labels)[:15] + ko_tags  # max 15 auto + 8 Korean

        print(f"  🏷️  Detected {len(labels)} labels: {list(labels)[:10]}", flush=True)
        return all_tags

    except Exception as e:
        print(f"  ⚠️  Video Intelligence API error: {e}", flush=True)
        # Return default tags as fallback
        return ["뉴스", "경제", "금융", "증시", "주식", "투자", "시사", "글로벌뉴스"]


def main():
    print("[Video Intelligence] Analyzing video...", flush=True)

    metadata = {}

    # Generate chapters from manifest (no API call needed)
    chapters = generate_chapters_from_manifest()
    metadata["chapters"] = chapters

    if chapters:
        print("\n  📑 Chapters:", flush=True)
        for ch in chapters:
            print(f"    {ch['timestamp']}  {ch['label']}", flush=True)

    # Generate chapter text for YouTube description
    chapter_text = "\n".join(f"{ch['timestamp']} {ch['label']}" for ch in chapters)
    metadata["chapter_text"] = chapter_text

    # Auto-detect labels/tags (uses API)
    tags = analyze_video_labels()
    metadata["tags"] = tags
    print(f"\n  🏷️  Tags: {tags}", flush=True)

    # Save metadata
    os.makedirs("temp", exist_ok=True)
    with open(METADATA_FILE, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Video metadata saved → {METADATA_FILE}", flush=True)


if __name__ == "__main__":
    main()
