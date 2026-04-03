"""
Step 4: Convert Korean script to speech using Google Cloud TTS Neural2.
        Voice: ko-KR-Neural2-A (female, most natural Korean)
        Free tier: 1 million characters/month
        Saves final audio to temp/korean_audio.mp3
"""

import os
import subprocess
from google.cloud import texttospeech

RAW_FILE    = "temp/korean_audio_raw.mp3"
OUTPUT_FILE = "temp/korean_audio.mp3"
SPEED       = 1.5
VOICE_NAME  = "ko-KR-Neural2-A"   # Options: A (female), B (male), C (female), D (male)


def generate_audio():
    with open("temp/korean_script.txt", "r", encoding="utf-8") as f:
        text = f.read().strip()

    if not text:
        raise ValueError("Korean script is empty.")

    os.makedirs("temp", exist_ok=True)

    print(f"[TTS] Generating Korean audio with Google Cloud TTS ({VOICE_NAME})...", flush=True)
    print(f"  Script length: {len(text):,} characters", flush=True)

    client = texttospeech.TextToSpeechClient()

    # Google Cloud TTS has a 5,000 byte limit per request — split if needed
    MAX_BYTES = 4800
    encoded = text.encode("utf-8")

    if len(encoded) <= MAX_BYTES:
        chunks = [text]
    else:
        # Split on sentence endings to avoid cutting mid-word
        import re
        sentences = re.split(r'(?<=[.!?。]) +', text)
        chunks = []
        current = ""
        for sentence in sentences:
            if len((current + " " + sentence).encode("utf-8")) > MAX_BYTES:
                if current:
                    chunks.append(current.strip())
                current = sentence
            else:
                current = (current + " " + sentence).strip()
        if current:
            chunks.append(current.strip())

    print(f"  Generating {len(chunks)} audio chunk(s)...", flush=True)

    audio_parts = []
    for i, chunk in enumerate(chunks):
        synthesis_input = texttospeech.SynthesisInput(text=chunk)
        voice = texttospeech.VoiceSelectionParams(
            language_code="ko-KR",
            name=VOICE_NAME,
        )
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
            speaking_rate=1.0,   # We'll speed up with FFmpeg after
            pitch=0.0,
        )
        response = client.synthesize_speech(
            input=synthesis_input,
            voice=voice,
            audio_config=audio_config,
        )
        chunk_file = f"temp/chunk_{i:03d}.mp3"
        with open(chunk_file, "wb") as f:
            f.write(response.audio_content)
        audio_parts.append(chunk_file)
        print(f"  ✅ Chunk {i+1}/{len(chunks)} done", flush=True)

    # Concatenate chunks if multiple
    if len(audio_parts) == 1:
        os.rename(audio_parts[0], RAW_FILE)
    else:
        concat_list = "temp/concat_list.txt"
        with open(concat_list, "w") as f:
            for p in audio_parts:
                f.write(f"file '{os.path.abspath(p)}'\n")
        subprocess.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", concat_list, "-c", "copy", RAW_FILE
        ], capture_output=True, check=True)
        for p in audio_parts:
            os.remove(p)
        os.remove(concat_list)

    # Speed up with FFmpeg
    print(f"  ⚡ Speeding up {SPEED}x with FFmpeg...", flush=True)
    result = subprocess.run([
        "ffmpeg", "-y", "-i", RAW_FILE,
        "-filter:a", f"atempo={SPEED}",
        "-vn", OUTPUT_FILE,
    ], capture_output=True, text=True)

    if result.returncode != 0:
        print("FFmpeg stderr:", result.stderr[-500:], flush=True)
        raise RuntimeError("FFmpeg speed-up failed.")

    os.remove(RAW_FILE)
    size_mb = os.path.getsize(OUTPUT_FILE) / (1024 * 1024)
    print(f"✅ Audio saved to {OUTPUT_FILE} ({size_mb:.1f} MB) at {SPEED}x speed.", flush=True)


if __name__ == "__main__":
    generate_audio()
