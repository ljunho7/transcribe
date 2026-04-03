"""
Step 3: Read all transcripts + market_data.json, generate a structured Korean script
        with 4 tagged sections:
        [시장개요] - market data walkthrough
        [주요등락] - top movers commentary
        [섹터분석] - sector performance
        [뉴스]     - 10-15 news stories
"""

import os, json, time
from google import genai
from google.genai import types
from pathlib import Path
from datetime import datetime, timezone, timedelta

MODELS = [
    "gemini-2.5-flash-preview-04-17",
    "gemini-2.5-flash",
    "gemini-2.0-flash",
]
MAX_RETRIES = 3
RETRY_DELAY = 10


def load_market_data():
    """Load market data JSON saved by generate_background/movers/sectors."""
    try:
        with open("assets/market_data.json") as f:
            return json.load(f)
    except Exception as e:
        print(f"  ⚠️  No market_data.json: {e}", flush=True)
        return {}


def format_market_for_prompt(md):
    """Format market data into readable text for the prompt."""
    lines = []

    if md.get("equity"):
        lines.append("[ 주요 지수 ]")
        for name, v in md["equity"].items():
            arrow = "▲" if v["chg_pct"] >= 0 else "▼"
            lines.append(f"  {name}: {v['price']:,.2f}  {arrow}{abs(v['chg_pct']):.2f}%")

    if md.get("fx"):
        lines.append("[ 외환 ]")
        for name, v in md["fx"].items():
            arrow = "▲" if v["chg_pct"] >= 0 else "▼"
            lines.append(f"  {name}: {v['price']}  {arrow}{abs(v['chg_pct']):.2f}%")

    if md.get("crypto"):
        lines.append("[ 암호화폐 ]")
        for name, v in md["crypto"].items():
            arrow = "▲" if v["chg_pct"] >= 0 else "▼"
            lines.append(f"  {name}: ${v['price']:,.0f}  {arrow}{abs(v['chg_pct']):.2f}%")

    if md.get("rates"):
        lines.append("[ 금리 ]")
        for name, v in md["rates"].items():
            bp = v["chg_bp"]
            lines.append(f"  {name}: {v['rate']:.2f}%  ({bp:+.1f}bp)")

    if md.get("gainers"):
        lines.append("[ S&P 500 상위 상승 종목 ]")
        for g in md["gainers"][:10]:
            lines.append(f"  {g['symbol']} ({g['name']}): +{g['chg_pct']:.2f}%  ${g['price']:.2f}")

    if md.get("losers"):
        lines.append("[ S&P 500 상위 하락 종목 ]")
        for l in md["losers"][:10]:
            lines.append(f"  {l['symbol']} ({l['name']}): {l['chg_pct']:.2f}%  ${l['price']:.2f}")

    if md.get("sectors"):
        lines.append("[ GICS 섹터별 수익률 ]")
        sorted_s = sorted(md["sectors"].items(), key=lambda x: -x[1]["chg_pct"])
        for etf, v in sorted_s:
            arrow = "▲" if v["chg_pct"] >= 0 else "▼"
            lines.append(f"  {v['ko']}: {arrow}{abs(v['chg_pct']):.2f}%")

    return "\n".join(lines)


def summarize_and_translate():
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    # Load transcripts
    transcript_dir = Path("temp/transcripts")
    all_transcripts = ""
    for txt_file in sorted(transcript_dir.glob("*.txt")):
        with open(txt_file, "r", encoding="utf-8") as f:
            all_transcripts += f.read() + "\n\n===\n\n"

    if not all_transcripts.strip():
        raise ValueError("No transcripts found")

    # Load market data
    md = load_market_data()
    market_text = format_market_for_prompt(md)

    KST = timezone(timedelta(hours=9))
    today = datetime.now(KST).strftime("%Y년 %m월 %d일")

    prompt = f"""You are a professional Korean financial broadcast journalist.

Today is {today} (Korean Standard Time).

Below is today's market data and podcast transcripts. Generate a complete Korean audio script
structured into exactly 4 sections with these exact tags on their own lines.

MARKET DATA (use these exact numbers):
{market_text}

PODCAST TRANSCRIPTS:
{all_transcripts}

Output format — use EXACTLY these section tags:

[시장개요]
(2-3 minute market overview. Walk through each index, FX rate, crypto, and interest rates using the exact numbers above. Use natural broadcast Korean. Mention notable moves. End with overall market sentiment summary.)

[주요등락]
(1-2 minute commentary on S&P 500 top movers. Briefly explain WHY each major gainer/loser moved if mentioned in transcripts. Group by theme if possible.)

[섹터분석]
(1-2 minute sector performance walkthrough. Go from best to worst performing sector. Note any notable divergences or themes across sectors.)

[뉴스]
(15-20 minute section. 10-15 news stories from the transcripts. Each story:
- 소제목: short Korean headline (under 20 chars, no bold/stars/numbers)
- 2-3 paragraphs of detail
Sort by cross-source importance. Combine duplicate stories.)

Rules:
- Return ONLY Korean text with the 4 section tags
- No English except tickers/company names
- No markdown, no bold, no numbering
- Natural conversational Korean throughout
- Use exact market numbers from the data above
- Opening greeting: one sentence at very start before [시장개요]
- Closing: one sentence at very end after last news story"""

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

                # Verify sections exist
                for tag in ["[시장개요]", "[주요등락]", "[섹터분석]", "[뉴스]"]:
                    if tag not in korean_script:
                        print(f"  ⚠️  Missing section tag: {tag}", flush=True)

                print(f"✅ Script saved ({len(korean_script):,} chars) using {model}.", flush=True)
                return korean_script

            except Exception as e:
                last_error = e
                print(f"  Failed: {e}", flush=True)
                if attempt < MAX_RETRIES:
                    print(f"  Retrying in {RETRY_DELAY}s...", flush=True)
                    time.sleep(RETRY_DELAY)

        print(f"  All retries failed for {model}, trying next...", flush=True)

    raise RuntimeError(f"All models failed. Last error: {last_error}")


if __name__ == "__main__":
    summarize_and_translate()
