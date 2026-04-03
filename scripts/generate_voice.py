"""
Step 4: Convert Korean script to speech using gTTS, then speed up 1.5x with FFmpeg.
        Saves final audio to temp/korean_audio.mp3
"""

import os
import subprocess
from gtts import gTTS

RAW_FILE    = "temp/korean_audio_raw.mp3"
OUTPUT_FILE = "temp/korean_audio.mp3"
LANGUAGE    = "ko"
SPEED       = 1.5


def generate_audio():
    with open("temp/korean_script.txt", "r", encoding="utf-8") as f:
        text = f.read().strip()

    if not text:
        raise ValueError("Korean script is empty.")

    os.makedirs("temp", exist_ok=True)

    print(f"[TTS] Generating Korean audio with gTTS...", flush=True)
    print(f"  Script length: {len(text):,} characters", flush=True)

    tts = gTTS(text=text, lang=LANGUAGE, slow=False)
    tts.save(RAW_FILE)

    raw_mb = os.path.getsize(RAW_FILE) / (1024 * 1024)
    print(f"  Raw audio saved ({raw_mb:.1f} MB) — speeding up {SPEED}x...", flush=True)

    cmd = [
        "ffmpeg", "-y",
        "-i", RAW_FILE,
        "-filter:a", f"atempo={SPEED}",
        "-vn",
        OUTPUT_FILE,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("FFmpeg stderr:", result.stderr[-1000:], flush=True)
        raise RuntimeError("FFmpeg speed-up failed.")

    os.remove(RAW_FILE)
    out_mb = os.path.getsize(OUTPUT_FILE) / (1024 * 1024)
    print(f"✅ Audio saved to {OUTPUT_FILE} ({out_mb:.1f} MB) at {SPEED}x speed.", flush=True)


if __name__ == "__main__":
    generate_audio()
