"""
Step 2: Transcribe each downloaded MP3 using Groq's Whisper API (free tier).
        Saves transcripts as .txt files to temp/transcripts/
"""

import json
import os
from groq import Groq
from pathlib import Path


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
            episode["name"].replace(" ", "_").replace("'", "").replace("'", "")
        )
        transcript_file = f"temp/transcripts/{safe_name}.txt"

        with open(episode["file"], "rb") as f:
            audio_bytes = f.read()

        transcription = client.audio.transcriptions.create(
            file=(os.path.basename(episode["file"]), audio_bytes),
            model="whisper-large-v3",
            response_format="text",
            language="en",
        )

        with open(transcript_file, "w", encoding="utf-8") as f:
            f.write(f"SOURCE: {episode['name']}\n")
            f.write(f"EPISODE: {episode['title']}\n")
            f.write(f"DATE: {episode['date']}\n")
            f.write("-" * 60 + "\n\n")
            f.write(transcription)

        char_count = len(transcription)
        print(f"  ✅ Saved transcript ({char_count:,} characters) → {transcript_file}")

    print("\n✅ All transcriptions complete.")


if __name__ == "__main__":
    transcribe_episodes()
