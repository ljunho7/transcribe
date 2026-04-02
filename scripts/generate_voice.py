"""
Step 4: Convert Korean script to speech using gTTS, then speed up 1.5x with FFmpeg.
        Saves final audio to temp/korean_audio.mp3
"""

import os
import subprocess
from gtts import gTTS

RAW_FILE   = "temp/korean_audio_raw.mp3"
OUTPUT_FILE = "temp/korean_audio.mp3"
LANGUAGE   = "ko"
SPEED      = 1.5


def generate_audio():
    with open("temp/korean_script.txt", "r", encoding="utf-8") as f:
        text = f.read().strip()

    if not text:
        raise ValueError("Korean script is empty.")

    os.makedirs("temp", exist_ok=True)

    print(f"[TTS] Generating Korean audio with gTTS...")
    print(f"  Script length: {len(text):,} characters")

    tts = gTTS(text=text, lang=LANGUAGE, slow=False)
    tts.save(RAW_FILE)

    raw_mb = os.path.getsize(RAW_FILE) / (1024 * 1024)
    print(f"  Raw audio saved ({raw_mb:.1f} MB) — speeding up {SPEED}x...")

    # Speed up with FFmpeg using atempo filter
    # atempo max is 2.0 per filter, so 1.5x is fine in one pass
    cmd = [
        "ffmpeg", "-y",
        "-i", RAW_FILE,
        "-filter:a", f"atempo={SPEED}",
        "-vn",
        OUTPUT_FILE,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("FFmpeg stderr:", result.stderr[-1000:])
        raise RuntimeError("FFmpeg speed-up failed.")

    out_mb = os.path.getsize(OUTPUT_FILE) / (1024 * 1024)
    print(f"Audio saved to {OUTPUT_FILE} ({out_mb:.1f} MB) at {SPEED}x speed.")

    # Clean up raw file
    os.remove(RAW_FILE)


if __name__ == "__main__":
    generate_audio()
