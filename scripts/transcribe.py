"""
Step 2: Transcribe each downloaded MP3 using Groq's Whisper API.
        - Files over 24MB are split into chunks with FFmpeg
        - Rate limit errors (429) are handled with automatic retry + wait
        - Episodes that can't fit in the hourly quota are skipped gracefully
"""

import json
import os
import re
import time
import subprocess
import math
from groq import Groq
from pathlib import Path

MAX_SIZE_MB   = 24    # Groq's 25MB limit — stay safely under
MAX_RETRIES   = 3     # Retries per chunk on rate limit
DEFAULT_WAIT  = 300   # Default wait (5 min) if we can't parse retry-after


def parse_wait_seconds(error_message):
    """Extract wait time from Groq rate limit error message."""
    match = re.search(r"try again in (\d+)m(\d+)s", str(error_message))
    if match:
        return int(match.group(1)) * 60 + int(match.group(2))
    match = re.search(r"try again in (\d+)s", str(error_message))
    if match:
        return int(match.group(1))
    return DEFAULT_WAIT


def split_audio(file_path, chunk_dir):
    """Split an MP3 into ~24MB chunks using FFmpeg."""
    size_mb = os.path.getsize(file_path) / (1024 * 1024)
    num_chunks = math.ceil(size_mb / MAX_SIZE_MB)

    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", file_path],
        capture_output=True, text=True
    )
    duration = float(result.stdout.strip())
    chunk_duration = math.ceil(duration / num_chunks)

    os.makedirs(chunk_dir, exist_ok=True)
    chunk_paths = []

    for i in range(num_chunks):
        start = i * chunk_duration
        chunk_path = os.path.join(chunk_dir, f"chunk_{i:03d}.mp3")
        subprocess.run([
            "ffmpeg", "-y", "-i", file_path,
            "-ss", str(start), "-t", str(chunk_duration),
            "-c", "copy", chunk_path
        ], capture_output=True)
        if os.path.exists(chunk_path) and os.path.getsize(chunk_path) > 0:
            chunk_paths.append(chunk_path)

    return chunk_paths


def transcribe_single(client, file_path, label=""):
    """Transcribe one audio file with retry on rate limit."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with open(file_path, "rb") as f:
                audio_bytes = f.read()
            result = client.audio.transcriptions.create(
                file=(os.path.basename(file_path), audio_bytes),
                model="whisper-large-v3",
                response_format="text",
                language="en",
            )
            return result
        except Exception as e:
            if "429" in str(e) or "rate_limit" in str(e).lower():
                wait = parse_wait_seconds(str(e))
                print(f"  ⏳ Rate limit hit{' on ' + label if label else ''}. Waiting {wait}s...")
                time.sleep(wait + 5)  # +5s buffer
                if attempt == MAX_RETRIES:
                    raise
            else:
                raise


def transcribe_file(client, file_path):
    """Transcribe audio, splitting large files into chunks."""
    size_mb = os.path.getsize(file_path) / (1024 * 1024)

    if size_mb <= MAX_SIZE_MB:
        return transcribe_single(client, file_path)
    else:
        print(f"    ⚡ File is {size_mb:.1f}MB — splitting into chunks...")
        chunk_dir = file_path.replace(".mp3", "_chunks")
        chunks = split_audio(file_path, chunk_dir)
        print(f"    📦 Split into {len(chunks)} chunks")

        full_transcript = []
        for i, chunk_path in enumerate(chunks):
            print(f"    🎙️  Transcribing chunk {i+1}/{len(chunks)}...")
            result = transcribe_single(client, chunk_path, label=f"chunk {i+1}")
            full_transcript.append(result)
            os.remove(chunk_path)

        try:
            os.rmdir(chunk_dir)
        except Exception:
            pass

        return " ".join(full_transcript)


def transcribe_episodes():
    client = Groq(api_key=os.environ["GROQ_API_KEY"])

    with open("temp/episodes.json", "r") as f:
        episodes = json.load(f)

    if not episodes:
        raise ValueError("No episodes found in temp/episodes.json")

    os.makedirs("temp/transcripts", exist_ok=True)
    skipped = []

    for episode in episodes:
        print(f"\n[Transcribe] {episode['name']} — {episode['title']}")

        safe_name = (
            episode["name"].replace(" ", "_")
                .replace("'", "").replace("'", "")
                .replace("/", "_").replace("-", "_")
        )
        transcript_file = f"temp/transcripts/{safe_name}.txt"

        size_mb = os.path.getsize(episode["file"]) / (1024 * 1024)
        print(f"  📁 File size: {size_mb:.1f}MB")

        try:
            transcription = transcribe_file(client, episode["file"])

            with open(transcript_file, "w", encoding="utf-8") as f:
                f.write(f"SOURCE: {episode['name']}\n")
                f.write(f"EPISODE: {episode['title']}\n")
                f.write(f"DATE: {episode['date']}\n")
                f.write("-" * 60 + "\n\n")
                f.write(transcription)

            print(f"  ✅ Saved transcript ({len(transcription):,} chars) → {transcript_file}")

        except Exception as e:
            print(f"  ❌ Failed to transcribe: {e} — skipping")
            skipped.append(episode["name"])

    if skipped:
        print(f"\n⚠️  Skipped due to errors: {', '.join(skipped)}")

    # Check we have at least something to work with
    transcripts = list(Path("temp/transcripts").glob("*.txt"))
    if not transcripts:
        raise RuntimeError("No transcripts produced at all.")

    print(f"\n✅ Transcription complete. {len(transcripts)} transcript(s) ready.")


if __name__ == "__main__":
    transcribe_episodes()
