"""
Step 2: Transcribe each downloaded MP3.
        Primary:  Groq Whisper API (fast, free tier)
        Fallback: faster-whisper running locally on the GitHub Actions runner
        - Files over 24MB are split into chunks with FFmpeg
        - Rate limit errors (429) are retried with automatic wait
        - If Groq fails entirely, falls back to local faster-whisper
"""

import json
import os
import re
import time
import subprocess
import math
from pathlib import Path
from groq import Groq

MAX_SIZE_MB  = 24
MAX_RETRIES  = 3
DEFAULT_WAIT = 300
MAX_WAIT     = 600   # If Groq asks us to wait more than 10 min, skip to local fallback


# ── Helpers ───────────────────────────────────────────────────────────────────

def parse_wait_seconds(error_message):
    match = re.search(r"try again in (\d+)m(\d+)s", str(error_message))
    if match:
        return int(match.group(1)) * 60 + int(match.group(2))
    match = re.search(r"try again in (\d+)s", str(error_message))
    if match:
        return int(match.group(1))
    return DEFAULT_WAIT


def split_audio(file_path, chunk_dir):
    """Split MP3 into ~24MB chunks using FFmpeg."""
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
        chunk_path = os.path.join(chunk_dir, f"chunk_{i:03d}.mp3")
        subprocess.run([
            "ffmpeg", "-y", "-i", file_path,
            "-ss", str(i * chunk_duration),
            "-t", str(chunk_duration),
            "-c", "copy", chunk_path
        ], capture_output=True)
        if os.path.exists(chunk_path) and os.path.getsize(chunk_path) > 0:
            chunk_paths.append(chunk_path)
    return chunk_paths


# ── Primary: Groq ─────────────────────────────────────────────────────────────

def groq_transcribe_single(client, file_path, label=""):
    """Transcribe one file via Groq with rate-limit retry."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with open(file_path, "rb") as f:
                audio_bytes = f.read()
            return client.audio.transcriptions.create(
                file=(os.path.basename(file_path), audio_bytes),
                model="whisper-large-v3",
                response_format="text",
                language="en",
            )
        except Exception as e:
            if "429" in str(e) or "rate_limit" in str(e).lower():
                wait = parse_wait_seconds(str(e))
                if wait > MAX_WAIT:
                    print(f"  ⏭️  Groq wait too long ({wait}s > {MAX_WAIT}s) — switching to local whisper", flush=True)
                    raise
                print(f"  ⏳ Rate limit{' on ' + label if label else ''}. Waiting {wait}s...", flush=True)
                time.sleep(wait + 5)
                if attempt == MAX_RETRIES:
                    raise
            else:
                raise


def groq_transcribe(client, file_path):
    """Groq transcription with chunking for large files."""
    size_mb = os.path.getsize(file_path) / (1024 * 1024)

    if size_mb <= MAX_SIZE_MB:
        return groq_transcribe_single(client, file_path)

    print(f"    ⚡ {size_mb:.1f}MB — splitting into chunks...", flush=True)
    chunk_dir = file_path.replace(".mp3", "_chunks")
    chunks = split_audio(file_path, chunk_dir)
    print(f"    📦 {len(chunks)} chunks", flush=True)

    parts = []
    for i, chunk_path in enumerate(chunks):
        print(f"    🎙️  Groq chunk {i+1}/{len(chunks)}...", flush=True)
        parts.append(groq_transcribe_single(client, chunk_path, label=f"chunk {i+1}"))
        os.remove(chunk_path)
    try:
        os.rmdir(chunk_dir)
    except Exception:
        pass
    return " ".join(parts)


# ── Fallback: faster-whisper (local) ─────────────────────────────────────────

def local_transcribe(file_path):
    """Transcribe using faster-whisper locally — no API key needed."""
    print(f"  🔄 Using local faster-whisper fallback...", flush=True)

    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("  📦 Installing faster-whisper...", flush=True)
        subprocess.run(
            ["pip", "install", "faster-whisper", "--break-system-packages", "-q"],
            check=True
        )
        from faster_whisper import WhisperModel

    # Use tiny model for speed on GitHub Actions CPU
    model = WhisperModel("tiny", device="cpu", compute_type="int8")
    segments, _ = model.transcribe(file_path, language="en", beam_size=1)
    transcript = " ".join(seg.text.strip() for seg in segments)
    print(f"  ✅ Local transcription complete ({len(transcript):,} chars)", flush=True)
    return transcript


# ── Main ─────────────────────────────────────────────────────────────────────

def transcribe_episodes():
    client = Groq(api_key=os.environ["GROQ_API_KEY"])

    with open("temp/episodes.json", "r") as f:
        episodes = json.load(f)

    if not episodes:
        raise ValueError("No episodes found in temp/episodes.json")

    os.makedirs("temp/transcripts", exist_ok=True)
    skipped = []

    for episode in episodes:
        print(f"\n[Transcribe] {episode['name']} — {episode['title']}", flush=True)

        safe_name = (
            episode["name"].replace(" ", "_")
                .replace("'", "").replace("'", "")
                .replace("/", "_").replace("-", "_")
        )
        transcript_file = f"temp/transcripts/{safe_name}.txt"

        size_mb = os.path.getsize(episode["file"]) / (1024 * 1024)
        print(f"  📁 File size: {size_mb:.1f}MB", flush=True)

        transcription = None

        # Try Groq first
        try:
            transcription = groq_transcribe(client, episode["file"])
            print(f"  ✅ Groq transcript ({len(transcription):,} chars)", flush=True)
        except Exception as e:
            print(f"  ⚠️  Groq failed: {e}", flush=True)

        # Fall back to local whisper
        if not transcription:
            try:
                transcription = local_transcribe(episode["file"])
            except Exception as e:
                print(f"  ❌ Local fallback also failed: {e} — skipping episode", flush=True)
                skipped.append(episode["name"])
                continue

        with open(transcript_file, "w", encoding="utf-8") as f:
            f.write(f"SOURCE: {episode['name']}\n")
            f.write(f"EPISODE: {episode['title']}\n")
            f.write(f"DATE: {episode['date']}\n")
            f.write("-" * 60 + "\n\n")
            f.write(transcription)

        print(f"  💾 Saved → {transcript_file}", flush=True)

    if skipped:
        print(f"\n⚠️  Skipped: {', '.join(skipped)}", flush=True)

    transcripts = list(Path("temp/transcripts").glob("*.txt"))
    if not transcripts:
        raise RuntimeError("No transcripts produced at all.")

    print(f"\n✅ Done. {len(transcripts)} transcript(s) ready.", flush=True)


if __name__ == "__main__":
    transcribe_episodes()
