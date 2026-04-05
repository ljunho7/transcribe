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

import os, json, subprocess
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
    FFmpeg: cycle through multiple images for the duration of the audio.
    Each image gets an equal share of the total duration.
    Falls back to single-image path if only one image.
    """
    if len(image_paths) == 1:
        return image_to_clip(image_paths[0], audio_path, clip_path)

    dur   = get_audio_duration(audio_path)
    n     = len(image_paths)
    each  = dur / n

    cmd = ["ffmpeg", "-y"]
    for img in image_paths:
        cmd += ["-loop", "1", "-t", f"{each:.3f}", "-i", str(img)]
    cmd += ["-i", str(audio_path)]

    # Scale each input then concat
    filter_parts = []
    for i in range(n):
        filter_parts.append(
            f"[{i}:v]scale={W}:{H}:force_original_aspect_ratio=decrease,"
            f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2[v{i}]"
        )
    concat_in = "".join(f"[v{i}]" for i in range(n))
    filter_parts.append(f"{concat_in}concat=n={n}:v=1:a=0[vout]")
    filter_complex = ";".join(filter_parts)

    cmd += [
        "-filter_complex", filter_complex,
        "-map", "[vout]",
        "-map", f"{n}:a",
        "-c:v", "libx264",
        "-c:a", "aac", "-b:a", "128k",
        "-pix_fmt", "yuv420p",
        str(clip_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ⚠️  FFmpeg multi-image error: {result.stderr[-300:]}", flush=True)
        return False
    return True


def image_to_clip(image_path, audio_path, clip_path):
    """FFmpeg: loop image for the duration of the audio."""
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", str(image_path),
        "-i", str(audio_path),
        "-c:v", "libx264",
        "-tune", "stillimage",
        "-c:a", "aac",
        "-b:a", "128k",
        "-pix_fmt", "yuv420p",
        "-shortest",
        "-vf", f"scale={W}:{H}",
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

    total_stories = sum(1 for m in manifest if m["section"] == "[뉴스]")
    story_idx = 0

    clip_paths = []
    for i, entry in enumerate(manifest):
        audio    = Path(entry["audio"])
        section  = entry["section"]
        headline = entry.get("headline", "")
        clip_path = CLIPS_DIR / f"clip_{i+1:03d}.mp4"

        print(f"\n  [{i+1}/{len(manifest)}] {audio.name}", flush=True)

        if section == "[뉴스]":
            # Look up charts + bullets from ticker_chart output
            section_key = f"뉴스: {headline}"
            sd_entry    = section_data.get(section_key, {})
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


if __name__ == "__main__":
    assemble()
