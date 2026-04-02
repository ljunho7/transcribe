"""
Step 3: Read all transcripts, summarize key stories, and translate to Korean
        in a single Gemini API call. Saves result to temp/korean_script.txt
"""

import os
import google.generativeai as genai
from pathlib import Path
from datetime import datetime


def summarize_and_translate():
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    model = genai.GenerativeModel("gemini-1.5-flash")

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
1. Identify the 5–7 most important news stories across all transcripts
2. Write a clear, engaging Korean-language news summary suitable for a 15-minute audio broadcast (~1,800 Korean words)
3. Use natural, conversational Korean — not overly formal, easy to listen to
4. Return ONLY the Korean text — no English, no preamble, no markdown

Structure:
- 인사말 (Opening greeting, 2–3 sentences, mention today's date)
- 5–7 뉴스 항목, each with:
    • 소제목 (Korean heading)
    • 2–3 paragraphs of summary
- 마무리 인사 (Brief closing, 2 sentences)

TRANSCRIPTS:
{all_transcripts}

Korean summary only:"""

    print("[Gemini] Summarizing and translating to Korean...")
    response = model.generate_content(
        prompt,
        generation_config=genai.GenerationConfig(
            max_output_tokens=4096,
            temperature=0.4,
        ),
    )

    korean_script = response.text.strip()

    os.makedirs("temp", exist_ok=True)
    with open("temp/korean_script.txt", "w", encoding="utf-8") as f:
        f.write(korean_script)

    print(f"✅ Korean script saved ({len(korean_script):,} characters).")
    return korean_script


if __name__ == "__main__":
    summarize_and_translate()
