"""
Step 4: Split Korean script by section and generate one MP3 per section/story.
Output: temp/audio/01_시장개요.mp3, 02_주요등락.mp3, ..., 05_story_001.mp3, etc.
"""

import os, re, time, subprocess
from pathlib import Path
from gtts import gTTS

SCRIPT_FILE = "temp/korean_script.txt"
AUDIO_DIR   = Path("temp/audio")
TTS_LANG    = "ko"
SPEED       = 1.5   # playback speed multiplier — adjust here

SECTION_ORDER = ["[시장개요]", "[주요등락]", "[섹터분석]", "[국가별]", "[뉴스]"]
SECTION_NAMES = {
    "[시장개요]": "시장개요",
    "[주요등락]": "주요등락",
    "[섹터분석]": "섹터분석",
    "[국가별]":   "국가별",
    "[뉴스]":     "뉴스",
}


def parse_sections(script):
    """Split script into {tag: text} dict in order."""
    sections = {}
    current_tag = None
    current_lines = []

    for line in script.split("\n"):
        stripped = line.strip()
        if stripped in SECTION_ORDER:
            if current_tag and current_lines:
                sections[current_tag] = "\n".join(current_lines).strip()
            current_tag = stripped
            current_lines = []
        else:
            if current_tag:
                current_lines.append(line)

    if current_tag and current_lines:
        sections[current_tag] = "\n".join(current_lines).strip()

    return sections


def parse_news_stories(news_text):
    """Split [뉴스] section into individual stories."""
    stories = []
    current_headline = None
    current_body = []

    for line in news_text.split("\n"):
        line = line.strip()
        if not line:
            continue

        is_headline = (
            5 < len(line) < 35
            and not line.endswith("다.")
            and not line.endswith("다")
            and not line.endswith(".")
        )

        if is_headline and current_headline is None:
            # First headline — treat preceding text as intro
            stories.append({"headline": "뉴스 브리핑", "text": line})
            current_headline = line
            current_body = []
        elif is_headline:
            if current_body:
                stories.append({
                    "headline": current_headline,
                    "text": "\n".join(current_body)
                })
            current_headline = line
            current_body = []
        else:
            current_body.append(line)

    if current_headline and current_body:
        stories.append({
            "headline": current_headline,
            "text": "\n".join(current_body)
        })

    return stories


def tts_to_file(text, path, retries=3):
    """Generate TTS audio with retry, then apply speed adjustment."""
    text = text.strip()
    if not text:
        print(f"  ⚠️  Empty text for {path.name}, skipping", flush=True)
        return False
    for attempt in range(1, retries+1):
        try:
            tts = gTTS(text=text, lang=TTS_LANG, slow=False)
            tts.save(str(path))
            # Speed up using ffmpeg atempo filter
            if SPEED != 1.0:
                tmp = path.with_suffix(".tmp.mp3")
                path.rename(tmp)
                subprocess.run([
                    "ffmpeg", "-y", "-i", str(tmp),
                    "-filter:a", f"atempo={SPEED}",
                    "-q:a", "2",
                    str(path)
                ], capture_output=True, check=True)
                tmp.unlink()
            size = path.stat().st_size
            print(f"  ✅ {path.name}  ({len(text):,} chars, {size:,} bytes, {SPEED}x)", flush=True)
            return True
        except Exception as e:
            print(f"  ⚠️  TTS attempt {attempt} failed: {e}", flush=True)
            if attempt < retries:
                time.sleep(5)
    return False


def generate_voice():
    os.makedirs(AUDIO_DIR, exist_ok=True)

    with open(SCRIPT_FILE, "r", encoding="utf-8") as f:
        script = f.read()

    sections = parse_sections(script)
    print(f"📝 Sections found: {list(sections.keys())}", flush=True)

    manifest = []  # ordered list of (audio_path, section_tag, headline)

    for i, tag in enumerate(SECTION_ORDER):
        text = sections.get(tag, "")
        if not text:
            print(f"  ⚠️  Missing section: {tag}", flush=True)
            continue

        if tag == "[뉴스]":
            stories = parse_news_stories(text)
            print(f"\n📰 [뉴스]: {len(stories)} stories", flush=True)
            for j, story in enumerate(stories):
                fname = AUDIO_DIR / f"05_story_{j+1:03d}.mp3"
                full_text = f"{story['headline']}\n{story['text']}"
                ok = tts_to_file(full_text, fname)
                if ok:
                    manifest.append({
                        "audio":    str(fname),
                        "section":  "[뉴스]",
                        "headline": story["headline"],
                    })
        else:
            fname = AUDIO_DIR / f"{i+1:02d}_{SECTION_NAMES[tag]}.mp3"
            print(f"\n🎙️  {tag}", flush=True)
            ok = tts_to_file(text, fname)
            if ok:
                manifest.append({
                    "audio":   str(fname),
                    "section": tag,
                    "headline": "",
                })

    # Save manifest for assemble_video.py
    import json
    manifest_path = AUDIO_DIR / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Generated {len(manifest)} audio files → {AUDIO_DIR}", flush=True)


if __name__ == "__main__":
    generate_voice()
