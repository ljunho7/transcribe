"""
Debug script: runs only market sections (Call 1) + final news (Call 2).
Reads pre-translated Korean texts from temp/transcripts/ instead of doing Pass 1.
Use with debug_from_translations.yml workflow.
"""
import os, json
from pathlib import Path
from datetime import datetime, timezone, timedelta
from summarize_translate import (
    load_market_data, format_market_for_prompt, call_gemini
)
from google import genai
from google.genai import types

def run():
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    md = load_market_data()
    market_text = format_market_for_prompt(md)
    KST   = timezone(timedelta(hours=9))
    today = datetime.now(KST).strftime("%Y년 %m월 %d일")

    # Call 1: Market sections
    print("[Debug] Call 1: Market sections...", flush=True)
    market_prompt = f"""You are a professional Korean financial broadcast journalist.
Today is {today} (Korean Standard Time).
Using ONLY the market data below, generate the market commentary sections.
Use EXACTLY these section tags on their own lines:
MARKET DATA:
{market_text}

[시장개요]
(2-3 minute market overview using exact numbers. Natural broadcast Korean.)

[주요등락]
(1-2 minutes. S&P 500 top movers — gainers and losers.)

[섹터분석]
(1-2 minutes. Sector performance from best to worst.)

[국가별]
(1. 미국/한국/중국/일본 with returns. 2. 상위 3개국. 3. 하위 3개국.)

Rules: Korean only, no markdown, opening greeting before [시장개요]"""

    market_script = call_gemini(
        client, market_prompt,
        required_tags=["[시장개요]", "[주요등락]", "[섹터분석]", "[국가별]"],
        min_chars=1000, max_tokens=8192
    )

    # Load pre-translated Korean texts
    transcript_dir = Path("temp/transcripts")
    combined = ""
    sources = sorted(transcript_dir.glob("*.txt"))
    print(f"\n[Debug] Loading {len(sources)} pre-translated texts...", flush=True)
    for f in sources:
        text = f.read_text(encoding="utf-8")
        combined += f"[출처: {f.stem}]\n{text}\n\n===\n\n"
        print(f"  ✅ {f.name}: {len(text):,} chars", flush=True)
    print(f"  📦 Combined: {len(combined):,} chars\n", flush=True)

    # Call 2: Final news section
    news_min_chars = min(10000, int(len(combined) * 0.6))
    print(f"[Debug] Call 2: Final news section (min {news_min_chars:,} chars)...", flush=True)
    news_prompt = f"""You are a professional Korean financial broadcast journalist.
Today is {today} (Korean Standard Time).
Using ONLY the Korean texts below, generate the news section.
Use EXACTLY this section tag on its own line:

KOREAN TEXTS:
{combined}

[뉴스]
(10-15 news stories. Each story:
- 소제목: short Korean headline under 20 chars
- 2-3 paragraphs of detail in natural broadcast Korean
Sort by importance. Merge duplicate topics.
End with one closing sentence.)

Rules: Korean only, no markdown, no numbering
NEVER repeat the same headline — each story must be unique
Once you have 10-15 distinct stories, STOP immediately"""

    news_script = call_gemini(
        client, news_prompt,
        required_tags=["[뉴스]"],
        min_chars=news_min_chars,
        max_tokens=32768,
        thinking=True
    )

    korean_script = market_script + "\n\n" + news_script
    os.makedirs("temp", exist_ok=True)
    with open("temp/korean_script.txt", "w", encoding="utf-8") as f:
        f.write(korean_script)

    print(f"\n✅ Script saved ({len(korean_script):,} chars)", flush=True)
    print("\n" + "="*60, flush=True)
    print(korean_script, flush=True)
    print("="*60, flush=True)

if __name__ == "__main__":
    run()
