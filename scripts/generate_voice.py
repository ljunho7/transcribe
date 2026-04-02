"""
Step 4: Convert Korean script to speech using gTTS (Google Translate TTS).
        Free, no API key needed, works on GitHub Actions.
        Saves audio to temp/korean_audio.mp3
"""

import os
from gtts import gTTS

OUTPUT_FILE = "temp/korean_audio.mp3"
LANGUAGE = "ko"  # Korean


def generate_audio():
    with open("temp/korean_script.txt", "r", encoding="utf-8") as f:
        text = f.read().strip()

    if not text:
        raise ValueError("Korean script is empty.")

    os.makedirs("temp", exist_ok=True)

    print(f"[TTS] Generating Korean audio with gTTS...")
    print(f"  Script length: {len(text):,} characters")

    tts = gTTS(text=text, lang=LANGUAGE, slow=False)
    tts.save(OUTPUT_FILE)

    size_mb = os.path.getsize(OUTPUT_FILE) / (1024 * 1024)
    print(f"Audio saved to {OUTPUT_FILE} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    generate_audio()
