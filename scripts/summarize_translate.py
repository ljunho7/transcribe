"""
Step 3: Read all transcripts, summarize key stories, and translate to Korean
        in a single Gemini API call. Saves result to temp/korean_script.txt
"""

import os
import time
from google import genai
from google.genai import types
from pathlib import Path
from datetime import datetime

# Try preferred model first, fall back if unavailable
MODELS = [
    "gemini-3.1-flash-lite-preview",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
]
MAX_RETRIES = 3
RETRY_DELAY = 10  # seconds between retries


def summarize_and_translate():
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    # Read all transcript files
    transcript_dir = Path("temp/transcripts")
    all_transcripts = ""

    for txt_file in sorted(transcript_dir.glob("*.txt")):
        with open(txt_file, "r", encoding="utf-8") as f:
            all_transcripts += f.read() + "\n\n===\n\n"

    if not all_transcripts.strip():
        raise ValueError("No transcripts found in temp/transcripts/")

    today = datetime.now().strftime("%Y년 %m월 %d일")

    prompt = f"""You are a professional news summarizer and Korean broadcast journalist.

Below are transcripts from today's English-language news podcasts ({today}).

Your task:
1. Identify the 5-7 most important news stories across all transcripts
2. Write a clear, engaging Korean-language news summary suitable for a 15-minute audio broadcast (~1,800 Korean words)
3. Use natural, conversational Korean -- not overly formal, easy to listen to
4. Return ONLY the Korean text -- no English, no preamble, no markdown

Structure:
- 인사말 (Opening greeting, 2-3 sentences, mention today's date)
- 5-7 뉴스 항목, each with:
    - 소제목 (Korean heading)
    - 2-3 paragraphs of summary
- 마무리 인사 (Brief closing, 2 sentences)

TRANSCRIPTS:
{all_transcripts}

Korean summary only:"""

    # Try each model with retries
    last_error = None
    for model in MODELS:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                print(f"[Gemini] Trying {model} (attempt {attempt}/{MAX_RETRIES})...")
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        max_output_tokens=4096,
                        temperature=0.4,
                    ),
                )
                korean_script = response.text.strip()

                os.makedirs("temp", exist_ok=True)
                with open("temp/korean_script.txt", "w", encoding="utf-8") as f:
                    f.write(korean_script)

                print(f"Korean script saved ({len(korean_script):,} characters) using {model}.")
                return korean_script

            except Exception as e:
                last_error = e
                print(f"  Failed: {e}")
                if attempt < MAX_RETRIES:
                    print(f"  Retrying in {RETRY_DELAY}s...")
                    time.sleep(RETRY_DELAY)

        print(f"  All retries failed for {model}, trying next model...")

    raise RuntimeError(f"All models failed. Last error: {last_error}")


if __name__ == "__main__":
    summarize_and_translate()
