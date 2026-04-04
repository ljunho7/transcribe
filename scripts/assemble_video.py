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
W, H       = 1920, 1080
DARK       = (8, 12, 22)
WHITE      = (255, 255, 255)
WHITE_DIM  = (180, 190, 210)
GREEN      = (0, 200, 110)
LEFT_W     = W // 2

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

    print(f"🎬 Assembling {len(manifest)} clips...", flush=True)

    # Load right-side background for story cards
    right_bg = None
    if os.path.exists("assets/background.jpg"):
        bg = Image.open("assets/background.jpg").convert("RGB")
        bg_w, bg_h = bg.size
        right_crop = bg.crop((bg_w // 2, 0, bg_w, bg_h))
        right_bg = right_crop.resize((W - LEFT_W, H))
    else:
        # Generate a simple dark gradient fallback
        print("  ⚠️  assets/background.jpg not found — using dark gradient fallback", flush=True)
        right_bg = Image.new("RGB", (W - LEFT_W, H), DARK)
        draw_fb = ImageDraw.Draw(right_bg)
        for y in range(H):
            t = y / H
            draw_fb.line([(0,y),(W-LEFT_W,y)],
                         fill=(int(8+10*t), int(12+15*t), int(22+30*t)))

    # Count news stories for progress bar
    total_stories = sum(1 for m in manifest if m["section"] == "[뉴스]")
    story_idx = 0

    clip_paths = []
    for i, entry in enumerate(manifest):
        audio  = Path(entry["audio"])
        section = entry["section"]
        headline = entry.get("headline", "")
        clip_path = CLIPS_DIR / f"clip_{i+1:03d}.mp4"

        print(f"\n  [{i+1}/{len(manifest)}] {audio.name}", flush=True)

        if section == "[뉴스]":
            # Generate story card frame
            frame_path = CLIPS_DIR / f"frame_{i+1:03d}.jpg"
            if right_bg:
                frame = make_story_frame(headline, story_idx, total_stories, right_bg)
            else:
                frame = Image.new("RGB", (W, H), DARK)
            frame.save(str(frame_path), "JPEG", quality=92)
            story_idx += 1
            image_path = frame_path
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
