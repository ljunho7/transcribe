"""
Step 4: Convert Korean script to speech using Microsoft Edge TTS (free, no API key).
        Uses the high-quality ko-KR-SunHiNeural voice.
        Saves audio to temp/korean_audio.mp3
"""

import asyncio
import os
import edge_tts

# Best Korean voices available in edge-tts:
#   ko-KR-SunHiNeural  — female, clear and natural (recommended)
#   ko-KR-InJoonNeural — male, professional tone
VOICE = "ko-KR-SunHiNeural"
OUTPUT_FILE = "temp/korean_audio.mp3"


async def generate_audio():
    with open("temp/korean_script.txt", "r", encoding="utf-8") as f:
        text = f.read().strip()

    if not text:
        raise ValueError("Korean script is empty.")

    os.makedirs("temp", exist_ok=True)

    print(f"[TTS] Generating audio with voice: {VOICE}")
    print(f"  Script length: {len(text):,} characters")

    communicate = edge_tts.Communicate(text, VOICE)
    await communicate.save(OUTPUT_FILE)

    size_mb = os.path.getsize(OUTPUT_FILE) / (1024 * 1024)
    print(f"✅ Audio saved to {OUTPUT_FILE} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    asyncio.run(generate_audio())
