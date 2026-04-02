"""
Step 2: Transcribe each downloaded MP3 using Groq's Whisper API.
        Files over 24MB are automatically split into chunks with FFmpeg.
        Saves transcripts as .txt files to temp/transcripts/
"""

import json
import os
import subprocess
import math
from groq import Groq
from pathlib import Path

MAX_SIZE_MB = 24  # Groq limit is 25MB — stay safely under


def split_audio(file_path, chunk_dir):
    """Split an MP3 into ~24MB chunks using FFmpeg. Returns list of chunk paths."""
    size_mb = os.path.getsize(file_path) / (1024 * 1024)
    num_chunks = math.ceil(size_mb / MAX_SIZE_MB)

    # Get audio duration in seconds
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
            "-ss", str(start),
            "-t", str(chunk_duration),
            "-c", "copy", chunk_path
        ], capture_output=True)
        if os.path.exists(chunk_path) and os.path.getsize(chunk_path) > 0:
            chunk_paths.append(chunk_path)

    return chunk_paths


def transcribe_file(client, file_path):
    """Transcribe a single audio file, splitting if needed."""
    size_mb = os.path.getsize(file_path) / (1024 * 1024)

    if size_mb <= MAX_SIZE_MB:
        # Small enough — transcribe directly
        with open(file_path, "rb") as f:
            audio_bytes = f.read()
        result = client.audio.transcriptions.create(
            file=(os.path.basename(file_path), audio_bytes),
            model="whisper-large-v3",
            response_format="text",
            language="en",
        )
        return result
    else:
        # Too large — split into chunks
        print(f"    ⚡ File is {size_mb:.1f}MB — splitting into chunks...")
        chunk_dir = file_path.replace(".mp3", "_chunks")
        chunks = split_audio(file_path, chunk_dir)
        print(f"    📦 Split into {len(chunks)} chunks")

        full_transcript = []
        for i, chunk_path in enumerate(chunks):
            print(f"    🎙️  Transcribing chunk {i+1}/{len(chunks)}...")
            with open(chunk_path, "rb") as f:
                audio_bytes = f.read()
            result = client.audio.transcriptions.create(
                file=(os.path.basename(chunk_path), audio_bytes),
                model="whisper-large-v3",
                response_format="text",
                language="en",
            )
            full_transcript.append(result)
            os.remove(chunk_path)  # Clean up chunk

        os.rmdir(chunk_dir)
        return " ".join(full_transcript)


def transcribe_episodes():
    client = Groq(api_key=os.environ["GROQ_API_KEY"])

    with open("temp/episodes.json", "r") as f:
        episodes = json.load(f)

    if not episodes:
        raise ValueError("No episodes found in temp/episodes.json")

    os.makedirs("temp/transcripts", exist_ok=True)

    for episode in episodes:
        print(f"[Transcribe] {episode['name']} — {episode['title']}")

        safe_name = (
            episode["name"].replace(" ", "_")
                .replace("'", "").replace("'", "")
                .replace("/", "_").replace("-", "_")
        )
        transcript_file = f"temp/transcripts/{safe_name}.txt"

        size_mb = os.path.getsize(episode["file"]) / (1024 * 1024)
        print(f"  📁 File size: {size_mb:.1f}MB")

        transcription = transcribe_file(client, episode["file"])

        with open(transcript_file, "w", encoding="utf-8") as f:
            f.write(f"SOURCE: {episode['name']}\n")
            f.write(f"EPISODE: {episode['title']}\n")
            f.write(f"DATE: {episode['date']}\n")
            f.write("-" * 60 + "\n\n")
            f.write(transcription)

        print(f"  ✅ Saved transcript ({len(transcription):,} characters) → {transcript_file}")

    print("\n✅ All transcriptions complete.")


if __name__ == "__main__":
    transcribe_episodes()
