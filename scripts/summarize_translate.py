“””
Step 3: Read all transcripts, summarize key stories, and translate to Korean
in a single Gemini API call. Saves result to temp/korean_script.txt
“””

import os
import time
from google import genai
from google.genai import types
from pathlib import Path
from datetime import datetime, timezone, timedelta

MODELS = [
“gemini-3.1-flash-lite-preview”,
“gemini-2.5-flash”,
“gemini-2.5-flash-lite”,
]
MAX_RETRIES = 3
RETRY_DELAY = 10

def summarize_and_translate():
client = genai.Client(api_key=os.environ[“GEMINI_API_KEY”])

```
transcript_dir = Path("temp/transcripts")
all_transcripts = ""

for txt_file in sorted(transcript_dir.glob("*.txt")):
    with open(txt_file, "r", encoding="utf-8") as f:
        all_transcripts += f.read() + "\n\n===\n\n"

if not all_transcripts.strip():
    raise ValueError("No transcripts found in temp/transcripts/")

# Use KST for greeting
KST = timezone(timedelta(hours=9))
today = datetime.now(KST).strftime("%Y년 %m월 %d일")

prompt = f"""You are a professional news summarizer and Korean broadcast journalist focusing on economics, finance and business.
```

Below are transcripts from today’s English-language news podcasts ({today}).

Your task:

1. Identify the 10~15 most important news stories across all transcripts
1. SORT stories by importance using this priority system:
- HIGHEST: Stories mentioned by 3 or more sources (major consensus)
- HIGH: Stories mentioned by 2 sources (cross-source confirmation)
- NORMAL: Stories mentioned by only 1 source but highly significant
- Present the highest importance stories first
1. COMBINE similar stories from different sources into ONE comprehensive story item
- If WSJ and FT both cover the same topic, merge their coverage into a single richer summary
- Use details from all sources to create the most complete picture possible
- Do NOT list the same story twice from different sources
1. Write a clear, engaging Korean-language news summary suitable for a 20-minute audio broadcast in Korean words
1. Use natural, conversational Korean – not overly formal, easy to listen to
1. Return ONLY the Korean text – no English, no preamble, no markdown
1. Do not use stars or bolds.
1. No numbering
1. For each story, do NOT compress or over-summarize – provide enough detail and context so the listener fully understands the story without having heard the original podcast. Each story should be substantive.

Structure:

- 인사말 (Opening greeting, 1 sentence, mention today’s date)
- 10~15 뉴스 항목, each with:
  - 소제목 (Korean heading)
  - 2-3 paragraphs of summary with sufficient detail and context
- 마무리 인사 (Brief closing, 1 sentence)

TRANSCRIPTS:
{all_transcripts}

Korean summary only:”””

```
last_error = None
for model in MODELS:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"[Gemini] Trying {model} (attempt {attempt}/{MAX_RETRIES})...", flush=True)
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    max_output_tokens=8192,
                    temperature=0.4,
                ),
            )
            korean_script = response.text.strip()

            os.makedirs("temp", exist_ok=True)
            with open("temp/korean_script.txt", "w", encoding="utf-8") as f:
                f.write(korean_script)

            print(f"Korean script saved ({len(korean_script):,} characters) using {model}.", flush=True)
            return korean_script

        except Exception as e:
            last_error = e
            print(f"  Failed: {e}", flush=True)
            if attempt < MAX_RETRIES:
                print(f"  Retrying in {RETRY_DELAY}s...", flush=True)
                time.sleep(RETRY_DELAY)

    print(f"  All retries failed for {model}, trying next model...", flush=True)

raise RuntimeError(f"All models failed. Last error: {last_error}")
```

if **name** == “**main**”:
summarize_and_translate()
