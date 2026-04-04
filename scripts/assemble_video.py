"""
Step 5: Assemble final video with 4 sections:
  1. [시장개요]  → full background.jpg (market overview)
  2. [주요등락]  → full movers.jpg
  3. [섹터분석]  → full sectors.jpg
  4. [뉴스]     → left story card + right half of background.jpg (per story)
"""

import os, re, subprocess
from PIL import Image, ImageDraw, ImageFont

BACKGROUND = "assets/background.jpg"
MOVERS     = "assets/movers.jpg"
SECTORS    = "assets/sectors.jpg"
COUNTRIES  = "assets/countries.jpg"
AUDIO      = "temp/korean_audio.mp3"
SCRIPT     = "temp/korean_script.txt"
OUTPUT     = "temp/final_video.mp4"
FRAMES_DIR = "temp/frames"

W, H       = 1920, 1080
LEFT_W     = W // 2
TTS_SPEED  = 1.5
CPS        = 7.0       # chars/sec before speedup (calibrated for Korean TTS)
FADE       = 0.4       # crossfade seconds

FONTS   = "/usr/share/fonts/opentype/noto"
KO_BOLD = f"{FONTS}/NotoSansCJK-Bold.ttc"
KO_REG  = f"{FONTS}/NotoSansCJK-Regular.ttc"

DARK     = (8,  12,  22)
GREEN    = (0, 200, 110)
WHITE    = (255, 255, 255)
WHITE_DIM= (190, 200, 220)
GRAY     = ( 55,  65,  85)


# ── 1. Parse script into sections ─────────────────────────────────────────

def parse_script(text):
    """
    Returns list of segments:
    [{"type": "full"|"story", "image": path, "headline": str, "text": str}]
    """
    TAGS = ["[시장개요]", "[주요등락]", "[섹터분석]", "[국가별]", "[뉴스]"]
    IMAGE_MAP = {
        "[시장개요]": BACKGROUND,
        "[주요등락]": MOVERS,
        "[섹터분석]": SECTORS,
        "[국가별]": COUNTRIES,
    }

    # Split text by section tags
    sections = {}
    current_tag = None
    current_lines = []
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped in TAGS:
            if current_tag:
                sections[current_tag] = "\n".join(current_lines).strip()
            current_tag = stripped
            current_lines = []
        else:
            current_lines.append(line)
    if current_tag:
        sections[current_tag] = "\n".join(current_lines).strip()

    segments = []

    # Opening greeting (text before first tag)
    intro_match = re.split(r'\[시장개요\]', text, maxsplit=1)
    intro_text = intro_match[0].strip() if len(intro_match) > 1 else ""

    # 1-3: Full-screen sections
    for tag in ["[시장개요]", "[주요등락]", "[섹터분석]", "[국가별]"]:
        body = sections.get(tag, "")
        if tag == "[시장개요]" and intro_text:
            body = intro_text + "\n\n" + body
        if body.strip():
            segments.append({
                "type":     "full",
                "image":    IMAGE_MAP[tag],
                "headline": tag,
                "text":     body,
            })

    # 4: News stories — parse individual headlines
    news_text = sections.get("[뉴스]", "")
    if news_text:
        stories = parse_news_stories(news_text)
        for story in stories:
            segments.append({
                "type":     "story",
                "image":    BACKGROUND,
                "headline": story["headline"],
                "text":     story["text"],
            })

    return segments


def parse_news_stories(text):
    """Extract individual stories from the [뉴스] section."""
    lines = text.strip().split("\n")
    stories = []
    current_h = None
    current_body = []
    intro_budget = 200  # skip opening lines

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Skip intro text
        if intro_budget > 0:
            intro_budget -= len(line)
            continue

        # Detect headline: short, no period at end, not too long
        is_headline = (
            5 < len(line) < 35
            and not line.endswith("다.")
            and not line.endswith("다")
            and not line.endswith(".")
        )

        if is_headline:
            if current_h and current_body:
                stories.append({"headline": current_h, "text": " ".join(current_body)})
            current_h = line
            current_body = []
        else:
            current_body.append(line)

    if current_h and current_body:
        stories.append({"headline": current_h, "text": " ".join(current_body)})

    return stories


# ── 2. Estimate timestamps ─────────────────────────────────────────────────

def estimate_timestamps(segments, full_text):
    """Estimate start time (seconds) for each segment."""
    timestamps = []
    pos = 0
    for seg in segments:
        # Find position of this segment's text in the full script
        search = seg["headline"] if seg["type"] == "story" else seg["text"][:30]
        idx = full_text.find(search, pos)
        if idx == -1:
            idx = pos
        secs = idx / CPS / TTS_SPEED
        timestamps.append(max(0.0, secs))
        pos = idx + len(seg["text"])
    return timestamps


# ── 3. Generate frames ─────────────────────────────────────────────────────

def make_full_frame(image_path):
    """Full-screen frame — just use the image as-is."""
    try:
        img = Image.open(image_path).convert("RGB")
        if img.size != (W, H):
            img = img.resize((W, H), Image.LANCZOS)
        return img
    except Exception:
        img = Image.new("RGB", (W, H), DARK)
        return img


def wrap_text(text, font, draw, max_width):
    lines, current = [], ""
    for char in text:
        test = current + char
        if draw.textbbox((0,0), test, font=font)[2] > max_width and current:
            lines.append(current)
            current = char
        else:
            current = test
    if current:
        lines.append(current)
    return lines


def make_story_frame(headline, card_idx, total_stories, right_bg):
    """Left story card + right half of background."""
    frame = right_bg.copy()

    # Left panel
    left = Image.new("RGB", (LEFT_W, H), DARK)
    draw = ImageDraw.Draw(left)

    # Gradient
    for y in range(H):
        t = y / H
        draw.line([(0,y),(LEFT_W,y)],
                  fill=(int(8+6*t), int(12+8*t), int(22+16*t)))

    # Grid
    for y in range(0, H, 44):
        draw.line([(0,y),(LEFT_W,y)], fill=(18,26,44))

    # Left accent
    draw.rectangle([(0,0),(6,H)], fill=GREEN)

    try:
        fr  = ImageFont.truetype(KO_REG,  26)
        fh  = ImageFont.truetype(KO_BOLD, 72)
    except:
        fr = fh = ImageFont.load_default()

    # Top label
    draw.ellipse([(80,118),(96,134)], fill=GREEN)
    draw.text((110,112), "미국 증시 마감 후 브리핑", font=fr, fill=WHITE_DIM)
    draw.line([(80,158),(LEFT_W-80,158)], fill=GREEN, width=2)

    # Progress bar
    bar_y = H - 100
    progress = (card_idx + 1) / max(total_stories, 1)
    draw.rectangle([(80,bar_y),(LEFT_W-80,bar_y+3)], fill=(25,35,58))
    draw.rectangle([(80,bar_y),(80+int((LEFT_W-160)*progress),bar_y+3)], fill=GREEN)

    # Headline
    pad = 80
    max_w = LEFT_W - pad * 2
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

    start_y = H // 2 - total_h // 2 - 20
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0,0), line, font=font)
        lw = bbox[2] - bbox[0]
        draw.text(((LEFT_W-lw)//2, start_y + i*line_h), line, font=font, fill=WHITE)

    draw.line([(pad, start_y+total_h+20),(LEFT_W-pad, start_y+total_h+20)],
              fill=GREEN, width=2)

    frame.paste(left, (0, 0))
    return frame


# ── 4. Build video ─────────────────────────────────────────────────────────

def get_audio_duration():
    result = subprocess.run([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        AUDIO
    ], capture_output=True, text=True)
    return float(result.stdout.strip())


def build_video(frame_paths, timestamps, audio_duration):
    n = len(frame_paths)

    if n == 1:
        cmd = ["ffmpeg", "-y",
               "-loop", "1", "-i", frame_paths[0],
               "-i", AUDIO,
               "-c:v", "libx264", "-tune", "stillimage",
               "-c:a", "aac", "-b:a", "192k",
               "-shortest", "-pix_fmt", "yuv420p", OUTPUT]
        subprocess.run(cmd, check=True)
        return

    durations = []
    for i in range(n):
        start = timestamps[i]
        end   = timestamps[i+1] if i+1 < n else audio_duration
        durations.append(max(1.0, end - start))

    inputs = []
    for i, path in enumerate(frame_paths):
        inputs += ["-loop", "1", "-t", str(durations[i] + FADE), "-i", path]

    filter_parts = []
    last = "0:v"
    for i in range(1, n):
        offset = sum(durations[:i]) - FADE * i
        out = f"xf{i}"
        filter_parts.append(
            f"[{last}][{i}:v]xfade=transition=fade:duration={FADE}:offset={offset:.2f}[{out}]"
        )
        last = out

    cmd = (["ffmpeg", "-y"]
           + inputs
           + ["-i", AUDIO]
           + ["-filter_complex", ";".join(filter_parts)]
           + ["-map", f"[{last}]", "-map", f"{n}:a"]
           + ["-c:v", "libx264", "-preset", "fast", "-crf", "23"]
           + ["-c:a", "aac", "-b:a", "192k"]
           + ["-pix_fmt", "yuv420p", "-shortest", OUTPUT])
    subprocess.run(cmd, check=True)


# ── Main ──────────────────────────────────────────────────────────────────

def assemble():
    print("[Assemble] Loading script...", flush=True)

    with open(SCRIPT, "r", encoding="utf-8") as f:
        script_text = f.read()

    bg  = Image.open(BACKGROUND)
    segments = parse_script(script_text)

    print(f"  📋 Segments:", flush=True)
    for i, s in enumerate(segments):
        print(f"    [{i+1}] {s['type']:6} | {s['headline'][:40]}", flush=True)

    timestamps   = estimate_timestamps(segments, script_text)
    audio_duration = get_audio_duration()
    print(f"  🎵 Audio: {audio_duration:.1f}s", flush=True)

    for i, (s, t) in enumerate(zip(segments, timestamps)):
        print(f"    [{i+1}] {t:.1f}s — {s['headline'][:40]}", flush=True)

    # Count news stories for progress bar
    total_stories = sum(1 for s in segments if s["type"] == "story")
    story_idx     = 0

    # Right half of background for story frames
    right_bg = bg.copy()

    os.makedirs(FRAMES_DIR, exist_ok=True)
    frame_paths = []

    for i, seg in enumerate(segments):
        if seg["type"] == "full":
            frame = make_full_frame(seg["image"])
        else:
            frame = make_story_frame(seg["headline"], story_idx, total_stories, right_bg)
            story_idx += 1

        path = f"{FRAMES_DIR}/frame_{i:03d}.jpg"
        frame.save(path, "JPEG", quality=92)
        frame_paths.append(path)
        print(f"  🖼️  Frame {i+1}/{len(segments)}: {seg['headline'][:40]}", flush=True)

    print("[Assemble] Building video...", flush=True)
    build_video(frame_paths, timestamps, audio_duration)

    size_mb = os.path.getsize(OUTPUT) / (1024*1024)
    print(f"✅ Video → {OUTPUT} ({size_mb:.1f} MB)", flush=True)


if __name__ == "__main__":
    assemble()
