"""
Step 5: Assemble video — one clip per audio file, then concatenate.
Each clip = image (looped) + audio. Perfect sync guaranteed.

Clip mapping:
  01_시장개요.mp3   → background.jpg   (full frame)
  02_주요등락.mp3   → movers.jpg       (full frame)
  03_섹터분석.mp3   → sectors.jpg      (full frame)
  04_국가별.mp3     → countries.jpg    (full frame)
  05_story_NNN.mp3 → story card image (left panel + right background)
"""

import os, json, re, subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

AUDIO_DIR  = Path("temp/audio")
CLIPS_DIR  = Path("temp/clips")
OUTPUT     = "temp/final_video.mp4"
SECTION_DATA_FILE = Path("temp/ticker_map.json")
W, H       = 1920, 1080
DARK       = (8, 12, 22)
WHITE      = (255, 255, 255)
WHITE_DIM  = (180, 190, 210)
GREEN      = (0, 200, 110)
AMBER      = (255, 167, 38)
LEFT_W     = int(W * 0.6)   # 1152 — chart panel
RIGHT_W    = W - LEFT_W     # 768  — bullets panel

FPS       = 25
KB_ZOOM   = 0.05     # Ken Burns: 5% total zoom over clip duration
FADE_DUR  = 0.5      # seconds for fade in/out between clips

FONTS = "/usr/share/fonts/opentype/noto"
KO_BOLD = f"{FONTS}/NotoSansCJK-Bold.ttc"
KO_REG  = f"{FONTS}/NotoSansCJK-Regular.ttc"

IMAGES = {
    "[시장개요]": "assets/background.jpg",
    "[주요등락]": "assets/movers.jpg",
    "[섹터분석]": "assets/sectors.jpg",
    "[국가별]":   "assets/countries.jpg",
}


def wrap_text(text, font, draw, max_width):
    words = list(text)  # Korean: split by character
    lines, cur = [], ""
    for ch in words:
        test = cur + ch
        bbox = draw.textbbox((0,0), test, font=font)
        if bbox[2]-bbox[0] > max_width and cur:
            lines.append(cur)
            cur = ch
        else:
            cur = test
    if cur:
        lines.append(cur)
    return lines


def make_story_frame(headline, card_idx, total_stories, right_bg):
    """Left story card + right half of background."""
    # Create full 1920x1080 frame, paste right_bg on the right half
    frame = Image.new("RGB", (W, H), DARK)
    frame.paste(right_bg, (LEFT_W, 0))

    left = Image.new("RGB", (LEFT_W, H), DARK)
    draw = ImageDraw.Draw(left)

    # Gradient background
    for y in range(H):
        t = y / H
        draw.line([(0,y),(LEFT_W,y)],
                  fill=(int(8+6*t), int(12+8*t), int(22+16*t)))

    # Grid lines
    for y in range(0, H, 44):
        draw.line([(0,y),(LEFT_W,y)], fill=(18,26,44))

    # Left accent bar
    draw.rectangle([(0,0),(6,H)], fill=GREEN)

    try:
        fr = ImageFont.truetype(KO_REG,  26)
        fh = ImageFont.truetype(KO_BOLD, 72)
    except Exception as e:
        print(f"  ⚠️  Font load failed: {e}", flush=True)
        fr = fh = ImageFont.load_default()

    # Top label
    draw.ellipse([(80,118),(96,134)], fill=GREEN)
    draw.text((110,112), "미국 증시 마감 후 브리핑", font=fr, fill=WHITE_DIM)
    draw.line([(80,158),(LEFT_W-80,158)], fill=GREEN, width=2)

    # Progress bar
    bar_y = H - 100
    progress = (card_idx + 1) / max(total_stories, 1)
    draw.rectangle([(80,bar_y),(LEFT_W-80,bar_y+3)], fill=(25,35,58))
    draw.rectangle([(80,bar_y),(80+int((LEFT_W-160)*progress),bar_y+3)],
                   fill=GREEN)

    # Headline — auto-size to fit
    pad = 80
    max_w = LEFT_W - pad * 2
    font = fh
    for font_size in [72, 60, 50, 42, 34]:
        try:
            font = ImageFont.truetype(KO_BOLD, font_size)
        except:
            font = ImageFont.load_default()
        lines = wrap_text(headline, font, draw, max_w)
        line_h = font_size + 16
        total_h = len(lines) * line_h
        if total_h < H * 0.45 or font_size == 34:
            break

    start_y = H // 2 - total_h // 2 - 20
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0,0), line, font=font)
        lw = bbox[2]-bbox[0]
        draw.text(((LEFT_W-lw)//2, start_y + i*line_h), line,
                  font=font, fill=WHITE)

    draw.line([(pad, start_y+total_h+20),(LEFT_W-pad, start_y+total_h+20)],
              fill=GREEN, width=2)

    frame.paste(left, (0,0))
    return frame


def get_audio_duration(audio_path):
    """Return audio duration in seconds using ffprobe."""
    result = subprocess.run([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(audio_path)
    ], capture_output=True, text=True)
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 30.0   # safe fallback


def make_bullets_panel(headline, bullets):
    """
    Right 40% panel (RIGHT_W x H) with dark background,
    Korean bullet points, and section headline.
    """
    panel = Image.new("RGB", (RIGHT_W, H), DARK)
    draw  = ImageDraw.Draw(panel)

    # Subtle gradient
    for y in range(H):
        t = y / H
        draw.line([(0, y), (RIGHT_W, y)],
                  fill=(int(8+4*t), int(12+6*t), int(22+12*t)))

    # Left accent bar
    draw.rectangle([(0, 0), (5, H)], fill=AMBER)

    try:
        f_label   = ImageFont.truetype(KO_REG,  24)
        f_bullet  = ImageFont.truetype(KO_REG,  34)
        f_headline= ImageFont.truetype(KO_BOLD, 40)
    except Exception:
        f_label = f_bullet = f_headline = ImageFont.load_default()

    # Top label
    draw.text((40, 60), "핵심 포인트", font=f_label, fill=AMBER)
    draw.line([(40, 100), (RIGHT_W - 40, 100)], fill=AMBER, width=1)

    # Bullet points — vertically centered in the middle band
    bullet_char = "▶"
    line_h      = 60
    total_h     = len(bullets) * line_h
    start_y     = H // 2 - total_h // 2 - 40

    for i, text in enumerate(bullets):
        y = start_y + i * line_h
        draw.text((40, y), bullet_char, font=f_bullet, fill=AMBER)
        draw.text((90, y), text,        font=f_bullet, fill=WHITE)

    # Headline at bottom
    draw.line([(40, H - 160), (RIGHT_W - 40, H - 160)], fill=GREEN, width=1)
    # Wrap headline if long
    words = list(headline)
    lines, cur = [], ""
    for ch in words:
        test = cur + ch
        bbox = draw.textbbox((0, 0), test, font=f_headline)
        if bbox[2] - bbox[0] > RIGHT_W - 80 and cur:
            lines.append(cur)
            cur = ch
        else:
            cur = test
    if cur:
        lines.append(cur)
    for i, line in enumerate(lines[:2]):   # max 2 lines
        draw.text((40, H - 140 + i * 48), line, font=f_headline, fill=WHITE_DIM)

    return panel


def make_news_chart_frame(chart_path, bullets_panel):
    """
    Composite frame: chart resized to LEFT_W x H on left,
    bullets panel on right. If chart_path is None, uses dark left panel.
    """
    frame = Image.new("RGB", (W, H), DARK)

    if chart_path is not None:
        chart = Image.open(str(chart_path)).convert("RGB")
        chart = chart.resize((LEFT_W, H), Image.LANCZOS)
        frame.paste(chart, (0, 0))
    else:
        # Dark gradient left panel (no chart available)
        left = Image.new("RGB", (LEFT_W, H), DARK)
        draw = ImageDraw.Draw(left)
        for y in range(H):
            t = y / H
            draw.line([(0, y), (LEFT_W, y)],
                      fill=(int(8+6*t), int(12+8*t), int(22+16*t)))
        draw.rectangle([(0, 0), (6, H)], fill=GREEN)
        frame.paste(left, (0, 0))

    frame.paste(bullets_panel, (LEFT_W, 0))
    return frame


def images_to_clip(image_paths, audio_path, clip_path):
    """
    FFmpeg: cycle through multiple images with Ken Burns zoom and
    crossfade transitions between them. Overall fade in/out applied.
    """
    if len(image_paths) == 1:
        return image_to_clip(image_paths[0], audio_path, clip_path)

    dur   = get_audio_duration(audio_path)
    n     = len(image_paths)
    each  = dur / n
    frames_each = int(each * FPS)
    zoom_rate   = KB_ZOOM / max(frames_each, 1)

    cmd = ["ffmpeg", "-y"]
    for img in image_paths:
        cmd += ["-i", str(img)]
    cmd += ["-i", str(audio_path)]

    filter_parts = []

    # Ken Burns on each image (alternate zoom in / zoom out)
    for i in range(n):
        if i % 2 == 0:
            zoom_expr = f"z='min({1+KB_ZOOM},pzoom+{zoom_rate:.8f})'"
        else:
            zoom_expr = f"z='max(1.0,{1+KB_ZOOM}-{zoom_rate:.8f}*on)'"
        filter_parts.append(
            f"[{i}:v]scale=2048:1152,setsar=1,"
            f"zoompan={zoom_expr}"
            f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":d={frames_each}:s={W}x{H}:fps={FPS}[kb{i}]"
        )

    # Chain crossfade transitions between segments
    prev = "kb0"
    for i in range(1, n):
        offset = (i) * (each - FADE_DUR)
        out_label = f"xf{i}" if i < n - 1 else "vraw"
        filter_parts.append(
            f"[{prev}][kb{i}]xfade=transition=fade:duration={FADE_DUR}"
            f":offset={offset:.3f}[{out_label}]"
        )
        prev = out_label

    # Overall fade in/out
    total_dur = n * each - (n - 1) * FADE_DUR
    filter_parts.append(
        f"[vraw]fade=t=in:st=0:d={FADE_DUR},"
        f"fade=t=out:st={max(0, total_dur-FADE_DUR):.3f}:d={FADE_DUR}[vout]"
    )

    filter_complex = ";".join(filter_parts)

    cmd += [
        "-filter_complex", filter_complex,
        "-map", "[vout]",
        "-map", f"{n}:a",
        "-c:v", "libx264",
        "-c:a", "aac", "-b:a", "128k",
        "-pix_fmt", "yuv420p",
        "-shortest",
        str(clip_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ⚠️  FFmpeg multi-image error: {result.stderr[-300:]}", flush=True)
        return False
    return True


def image_to_clip(image_path, audio_path, clip_path):
    """FFmpeg: single image → video with Ken Burns zoom + fade in/out."""
    dur = get_audio_duration(audio_path)
    total_frames = int(dur * FPS)
    zoom_rate = KB_ZOOM / max(total_frames, 1)

    vf = (
        f"scale=2048:1152,setsar=1,"
        f"zoompan=z='min({1+KB_ZOOM},pzoom+{zoom_rate:.8f})'"
        f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        f":d={total_frames}:s={W}x{H}:fps={FPS},"
        f"fade=t=in:st=0:d={FADE_DUR},"
        f"fade=t=out:st={max(0, dur-FADE_DUR):.3f}:d={FADE_DUR}"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", str(image_path),
        "-i", str(audio_path),
        "-vf", vf,
        "-map", "0:v", "-map", "1:a",
        "-c:v", "libx264",
        "-c:a", "aac", "-b:a", "128k",
        "-pix_fmt", "yuv420p",
        "-t", f"{dur:.3f}",
        str(clip_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ⚠️  FFmpeg error: {result.stderr[-300:]}", flush=True)
        return False
    return True


def assemble():
    os.makedirs(CLIPS_DIR, exist_ok=True)
    os.makedirs("temp", exist_ok=True)

    # Load manifest
    manifest_path = AUDIO_DIR / "manifest.json"
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    # Load section data (charts + bullets) from ticker_chart step
    section_data = {}
    if SECTION_DATA_FILE.exists():
        with open(SECTION_DATA_FILE, "r", encoding="utf-8") as f:
            section_data = json.load(f)
        print(f"📂 Loaded section data: {len(section_data)} sections", flush=True)
    else:
        print("  ⚠️  No section_data found — news sections will use story card fallback", flush=True)

    print(f"🎬 Assembling {len(manifest)} clips...", flush=True)

    # Load right-side background for story card fallback
    right_bg = None
    if os.path.exists("assets/background.jpg"):
        bg = Image.open("assets/background.jpg").convert("RGB")
        bg_w, bg_h = bg.size
        right_crop = bg.crop((bg_w // 2, 0, bg_w, bg_h))
        right_bg = right_crop.resize((W - LEFT_W, H))
    else:
        print("  ⚠️  assets/background.jpg not found — using dark gradient fallback", flush=True)
        right_bg = Image.new("RGB", (W - LEFT_W, H), DARK)
        draw_fb = ImageDraw.Draw(right_bg)
        for y in range(H):
            t = y / H
            draw_fb.line([(0, y), (W - LEFT_W, y)],
                         fill=(int(8+10*t), int(12+15*t), int(22+30*t)))

    total_stories = sum(1 for m in manifest if m["section"] in ("[뉴스]", "[리서치]"))
    story_idx = 0

    clip_paths = []
    for i, entry in enumerate(manifest):
        audio    = Path(entry["audio"])
        section  = entry["section"]
        headline = entry.get("headline", "")
        clip_path = CLIPS_DIR / f"clip_{i+1:03d}.mp4"

        print(f"\n  [{i+1}/{len(manifest)}] {audio.name}", flush=True)

        if section in ("[뉴스]", "[리서치]"):
            # Look up charts + bullets from ticker_chart output.
            # Keys in ticker_map.json may include body text after the headline,
            # so use prefix matching instead of exact key lookup.
            tag_prefix = "리서치" if section == "[리서치]" else "뉴스"
            section_key = f"{tag_prefix}: {headline}"
            sd_entry = section_data.get(section_key, {})
            if not sd_entry:
                for k, v in section_data.items():
                    if k.startswith(section_key):
                        sd_entry = v
                        break
            charts      = [p for p in sd_entry.get("charts", []) if os.path.exists(p)]
            bullets     = sd_entry.get("bullets", [])

            if charts:
                # ── Chart path: cycle charts on left, bullets on right ────
                print(f"    📊 {len(charts)} chart(s) + {len(bullets)} bullet(s)", flush=True)
                bullets_panel = make_bullets_panel(headline, bullets)
                frame_paths   = []
                for ci, chart_path in enumerate(charts):
                    frame = make_news_chart_frame(chart_path, bullets_panel)
                    fp    = CLIPS_DIR / f"frame_{i+1:03d}_{ci+1}.jpg"
                    frame.save(str(fp), "JPEG", quality=92)
                    frame_paths.append(fp)
                ok = images_to_clip(frame_paths, audio, clip_path)
            elif bullets:
                # ── No charts but has bullets: dark left + bullets right ──
                print(f"    📝 No charts, {len(bullets)} bullet(s) — using bullets layout", flush=True)
                bullets_panel = make_bullets_panel(headline, bullets)
                frame = make_news_chart_frame(None, bullets_panel)
                frame_path = CLIPS_DIR / f"frame_{i+1:03d}.jpg"
                frame.save(str(frame_path), "JPEG", quality=92)
                ok = image_to_clip(frame_path, audio, clip_path)
            else:
                # ── Fallback: original story card ─────────────────────────
                print(f"    ⚠️  No charts or bullets — using story card fallback", flush=True)
                frame_path = CLIPS_DIR / f"frame_{i+1:03d}.jpg"
                frame = make_story_frame(headline, story_idx, total_stories, right_bg)
                frame.save(str(frame_path), "JPEG", quality=92)
                ok = image_to_clip(frame_path, audio, clip_path)

            story_idx += 1

        else:
            image_path = IMAGES.get(section, "assets/background.jpg")
            if not os.path.exists(str(image_path)):
                print(f"  ⚠️  Image not found: {image_path}, using dark fallback", flush=True)
                fallback = Image.new("RGB", (W, H), DARK)
                image_path = CLIPS_DIR / f"fallback_{i+1:03d}.jpg"
                fallback.save(str(image_path))
            ok = image_to_clip(image_path, audio, clip_path)

        if ok:
            size_mb = clip_path.stat().st_size / 1e6
            print(f"  ✅ clip_{i+1:03d}.mp4  ({size_mb:.1f} MB)", flush=True)
            clip_paths.append(clip_path)
        else:
            print(f"  ❌ Failed: {clip_path.name}", flush=True)

    if not clip_paths:
        raise RuntimeError("No clips were created")

    # Write concat list
    concat_file = Path("temp/concat.txt")
    with open(concat_file, "w") as f:
        for p in clip_paths:
            f.write(f"file '{p.resolve()}'\n")

    # Concatenate all clips
    print(f"\n🔗 Concatenating {len(clip_paths)} clips → {OUTPUT}", flush=True)
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_file),
        "-c", "copy",
        OUTPUT,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Concatenation failed: {result.stderr[-500:]}")

    size_mb = Path(OUTPUT).stat().st_size / 1e6
    print(f"✅ Final video: {OUTPUT}  ({size_mb:.1f} MB)", flush=True)

    # ── Generate SRT subtitles ───────────────────────────────────────────
    generate_subtitles(manifest)


def _fmt_srt_time(secs):
    """Format seconds as SRT timestamp: HH:MM:SS,mmm"""
    h = int(secs // 3600)
    m = int((secs % 3600) // 60)
    s = int(secs % 60)
    ms = int((secs % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _split_sentences(text):
    """Split Korean text into sentences on common endings."""
    # Split on sentence-ending patterns followed by space or newline
    parts = re.split(r'(?<=[다요죠]\.)\s+|(?<=[다요죠])\s*\n', text)
    return [s.strip() for s in parts if s.strip()]


def generate_subtitles(manifest):
    """Generate SRT subtitle file from manifest audio durations."""
    srt_path = Path("temp/subtitles.srt")

    # Load script for subtitle text
    script_file = Path("temp/korean_script.txt")
    if not script_file.exists():
        print("  ⚠️  korean_script.txt not found — skipping subtitles", flush=True)
        return

    with open(script_file, "r", encoding="utf-8") as f:
        script = f.read()

    # Parse all sections including [뉴스] and [리서치]
    TAGS = ["[시장개요]", "[뉴스]", "[리서치]", "[주요등락]", "[섹터분석]", "[국가별]"]
    section_texts = {}
    current_tag = None
    current_lines = []
    for line in script.split("\n"):
        stripped = line.strip()
        if stripped in TAGS:
            if current_tag and current_lines:
                section_texts[current_tag] = "\n".join(current_lines).strip()
            current_tag = stripped
            current_lines = []
        else:
            if current_tag:
                current_lines.append(line)
    if current_tag and current_lines:
        section_texts[current_tag] = "\n".join(current_lines).strip()

    # Build subtitle entries with timestamps
    srt_entries = []
    elapsed = 0.0
    idx = 1

    for entry in manifest:
        audio_path = Path(entry["audio"])
        section = entry["section"]
        headline = entry.get("headline", "")

        dur = get_audio_duration(audio_path) if audio_path.exists() else 10.0

        # Get subtitle text for this clip
        if section in ("[뉴스]", "[리서치]") and headline:
            # Find story body from the section text
            tag = section
            full_text = section_texts.get(tag, "")
            story_text = ""
            chunks = [c.strip() for c in re.split(r'\n{2,}', full_text) if c.strip()]
            for chunk in chunks:
                lines = chunk.split('\n', 1)
                if lines[0].strip() == headline and len(lines) > 1:
                    story_text = lines[1].strip()
                    break
            if not story_text:
                story_text = headline
        else:
            # Fixed sections — use full section text
            story_text = section_texts.get(section, "")

        if not story_text:
            # Skip empty sections
            elapsed += dur
            continue

        # Split into sentences for readable subtitle chunks
        sentences = _split_sentences(story_text)
        if not sentences:
            sentences = [story_text[:80]]

        seg_dur = dur / len(sentences)

        for sent in sentences:
            start = elapsed
            end = elapsed + seg_dur
            srt_entries.append(
                f"{idx}\n{_fmt_srt_time(start)} --> {_fmt_srt_time(end)}\n{sent}\n"
            )
            idx += 1
            elapsed += seg_dur

    with open(srt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(srt_entries))

    print(f"📝 Subtitles: {srt_path}  ({idx-1} entries)", flush=True)


if __name__ == "__main__":
    assemble()
