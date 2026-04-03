"""
Step 5: Assemble final video.
        - Parses korean_script.txt to extract story headlines (소제목)
        - Estimates timestamp for each story based on character count + TTS speed
        - Generates a left-panel title card per story
        - Composites with static right half of background.jpg
        - FFmpeg assembles into final MP4 with smooth crossfades
"""

import os
import re
import subprocess
import json
from PIL import Image, ImageDraw, ImageFont

BACKGROUND   = "assets/background.jpg"
AUDIO        = "temp/korean_audio.mp3"
SCRIPT       = "temp/korean_script.txt"
OUTPUT       = "temp/final_video.mp4"
FRAMES_DIR   = "temp/frames"

W, H         = 1920, 1080
LEFT_W       = int(W * 0.50)   # Left panel width
TTS_SPEED    = 1.5             # Speed factor applied to audio
CHARS_PER_SEC = 7.0            # Korean TTS chars/sec before speed-up
FADE_SECS    = 0.5             # Crossfade duration between cards

FONTS   = "/usr/share/fonts/opentype/noto"
KO_BOLD = f"{FONTS}/NotoSansCJK-Bold.ttc"
KO_REG  = f"{FONTS}/NotoSansCJK-Regular.ttc"

DARK      = (8,  12,  22)
GREEN     = (0,  200, 110)
WHITE     = (255, 255, 255)
WHITE_DIM = (190, 200, 220)
GRAY      = ( 55,  65,  85)


# ── 1. Parse script into stories ──────────────────────────────────────────

def parse_stories(script_text):
    """
    Extract (headline, body) pairs from Korean script.
    Headlines are lines that are short (< 30 chars) and not part of
    the opening/closing greeting.
    """
    lines = script_text.strip().split("\n")
    stories = []
    current_headline = None
    current_body = []

    # Skip opening greeting (인사말) — usually first 1-3 short lines
    intro_done = False
    intro_char_budget = 150

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Detect headline: short line (< 35 chars), not ending in period
        is_headline = (
            len(line) < 35
            and not line.endswith(".")
            and not line.endswith("다.")
            and not line.endswith("다")
            and len(line) > 3
        )

        if not intro_done:
            intro_char_budget -= len(line)
            if intro_char_budget <= 0:
                intro_done = True
            continue

        if is_headline:
            # Save previous story
            if current_headline and current_body:
                stories.append({
                    "headline": current_headline,
                    "body": " ".join(current_body),
                })
            current_headline = line
            current_body = []
        else:
            current_body.append(line)

    # Last story
    if current_headline and current_body:
        stories.append({
            "headline": current_headline,
            "body": " ".join(current_body),
        })

    return stories


def estimate_timestamps(stories, script_text):
    """
    Estimate start time (seconds) for each story based on
    cumulative character count and TTS playback speed.
    """
    # Find where each story starts in the full script
    timestamps = []
    pos = 0
    for story in stories:
        idx = script_text.find(story["headline"], pos)
        if idx == -1:
            idx = pos
        chars_before = idx
        secs = chars_before / CHARS_PER_SEC / TTS_SPEED
        timestamps.append(max(0.0, secs))
        pos = idx + len(story["headline"])
    return timestamps


# ── 2. Generate left-panel title cards ───────────────────────────────────

def wrap_text(text, font, draw, max_width):
    """Wrap text to fit within max_width pixels."""
    words = list(text)  # Korean: split by character for wrapping
    lines = []
    current = ""
    for char in text:
        test = current + char
        bbox = draw.textbbox((0,0), test, font=font)
        if bbox[2] > max_width and current:
            lines.append(current)
            current = char
        else:
            current = test
    if current:
        lines.append(current)
    return lines


def make_title_card(headline, card_index, total):
    """Generate left-panel 960x1080 image for a story headline."""
    img  = Image.new("RGB", (LEFT_W, H), DARK)
    draw = ImageDraw.Draw(img)

    # Gradient
    for y in range(H):
        t = y / H
        r = int(DARK[0] + 6*t)
        g = int(DARK[1] + 8*t)
        b = int(DARK[2] + 16*t)
        draw.line([(0,y),(LEFT_W,y)], fill=(r,g,b))

    # Grid
    for y in range(0, H, 44):
        draw.line([(0,y),(LEFT_W,y)], fill=(18,26,44))

    # Left accent bar
    draw.rectangle([(0,0),(6,H)], fill=GREEN)

    # Top label
    try:
        fr  = ImageFont.truetype(KO_REG,  26)
        fh  = ImageFont.truetype(KO_BOLD, 72)
        fs  = ImageFont.truetype(KO_REG,  24)
    except:
        fr = fh = fs = ImageFont.load_default()

    draw.ellipse([(80,118),(96,134)], fill=GREEN)
    draw.text((110,112), "미국 증시 마감 후 브리핑", font=fr, fill=WHITE_DIM)
    draw.line([(80,158),(LEFT_W-80,158)], fill=GREEN, width=2)

    # Story indicator bar (thin green line at bottom of text area)
    progress = (card_index + 1) / total
    bar_y = H - 100
    draw.rectangle([(80, bar_y),(LEFT_W-80, bar_y+3)], fill=(25,35,58))
    draw.rectangle([(80, bar_y),(80 + int((LEFT_W-160)*progress), bar_y+3)],
                   fill=GREEN)

    # Headline — large, centered vertically
    padding = 80
    max_w   = LEFT_W - padding * 2

    # Try fitting on 1-2 lines
    for font_size in [80, 66, 54, 44]:
        try:
            font = ImageFont.truetype(KO_BOLD, font_size)
        except:
            font = ImageFont.load_default()
        lines = wrap_text(headline, font, draw, max_w)
        line_h = font_size + 16
        total_h = len(lines) * line_h
        if total_h < H * 0.45 or font_size == 44:
            break

    # Draw headline lines centered
    start_y = H // 2 - total_h // 2 - 20
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0,0), line, font=font)
        lw   = bbox[2] - bbox[0]
        x    = (LEFT_W - lw) // 2
        y    = start_y + i * line_h
        draw.text((x, y), line, font=font, fill=WHITE)

    # Decorative green underline under headline
    draw.line([(padding, start_y + total_h + 20),
               (LEFT_W - padding, start_y + total_h + 20)],
              fill=GREEN, width=2)

    return img


# ── 3. Composite left + right panels ─────────────────────────────────────

def composite_frame(left_img, right_bg):
    """Paste left card onto right half of background."""
    frame = right_bg.copy()
    frame.paste(left_img, (0, 0))
    return frame


# ── 4. Build video with FFmpeg ────────────────────────────────────────────

def get_audio_duration():
    result = subprocess.run([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        AUDIO
    ], capture_output=True, text=True)
    return float(result.stdout.strip())


def build_video(frame_paths, timestamps, audio_duration):
    """Use FFmpeg filter_complex to crossfade between frames."""

    if len(frame_paths) == 1:
        # Only one story — simple static video
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", frame_paths[0],
            "-i", AUDIO,
            "-c:v", "libx264", "-tune", "stillimage",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest", "-pix_fmt", "yuv420p",
            OUTPUT
        ]
        subprocess.run(cmd, check=True)
        return

    # Build xfade filter chain
    n = len(frame_paths)
    durations = []
    for i in range(n):
        start = timestamps[i]
        end   = timestamps[i+1] if i+1 < n else audio_duration
        dur   = max(1.0, end - start)
        durations.append(dur)

    # FFmpeg inputs
    inputs = []
    for path in frame_paths:
        inputs += ["-loop", "1", "-t", str(durations[frame_paths.index(path)] + FADE_SECS),
                   "-i", path]

    # Build xfade chain
    filter_parts = []
    last_out = "0:v"
    for i in range(1, n):
        offset = sum(durations[:i]) - FADE_SECS * i
        out_label = f"xf{i}"
        filter_parts.append(
            f"[{last_out}][{i}:v]xfade=transition=fade:duration={FADE_SECS}:offset={offset:.2f}[{out_label}]"
        )
        last_out = out_label

    filter_str = ";".join(filter_parts)

    cmd = (
        ["ffmpeg", "-y"]
        + inputs
        + ["-i", AUDIO]
        + ["-filter_complex", filter_str]
        + ["-map", f"[{last_out}]", "-map", f"{n}:a"]
        + ["-c:v", "libx264", "-preset", "fast", "-crf", "23"]
        + ["-c:a", "aac", "-b:a", "192k"]
        + ["-pix_fmt", "yuv420p", "-shortest"]
        + [OUTPUT]
    )
    subprocess.run(cmd, check=True)


# ── Main ──────────────────────────────────────────────────────────────────

def assemble():
    print("[Assemble] Loading script and background...", flush=True)

    with open(SCRIPT, "r", encoding="utf-8") as f:
        script_text = f.read()

    bg = Image.open(BACKGROUND)
    right_bg = bg.copy()  # Full 1920x1080 — left half will be overwritten per frame

    # Parse stories
    stories = parse_stories(script_text)
    print(f"  📰 Found {len(stories)} stories", flush=True)

    if not stories:
        print("  ⚠️  No stories parsed — falling back to static background", flush=True)
        stories = [{"headline": "오늘의 글로벌 경제 뉴스", "body": script_text}]

    # Estimate timestamps
    timestamps = estimate_timestamps(stories, script_text)
    audio_duration = get_audio_duration()
    print(f"  🎵 Audio duration: {audio_duration:.1f}s", flush=True)

    for i, (s, t) in enumerate(zip(stories, timestamps)):
        print(f"  [{i+1:02d}] {t:.1f}s — {s['headline']}", flush=True)

    # Generate frames
    os.makedirs(FRAMES_DIR, exist_ok=True)
    frame_paths = []

    for i, story in enumerate(stories):
        left_card = make_title_card(story["headline"], i, len(stories))
        frame     = composite_frame(left_card, right_bg)
        path      = f"{FRAMES_DIR}/frame_{i:03d}.jpg"
        frame.save(path, "JPEG", quality=92)
        frame_paths.append(path)
        print(f"  🖼️  Frame {i+1}/{len(stories)} saved", flush=True)

    # Build video
    print("[Assemble] Building video with FFmpeg...", flush=True)
    build_video(frame_paths, timestamps, audio_duration)

    size_mb = os.path.getsize(OUTPUT) / (1024*1024)
    print(f"✅ Video saved → {OUTPUT} ({size_mb:.1f} MB)", flush=True)


if __name__ == "__main__":
    assemble()
