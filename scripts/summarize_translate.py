"""
Step 3: Generate Korean script in two separate Gemini calls:
  Call 1: [시장개요] + [주요등락] + [섹터분석] + [국가별] — market data only
  Call 2: [뉴스] — transcripts only
"""

import os, json, time
from google import genai
from google.genai import types
from pathlib import Path
from datetime import datetime, timezone, timedelta

MODELS = [
    "gemini-3.1-flash-lite-preview",
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash",
]
MAX_RETRIES = 3
RETRY_DELAY = 10


def load_market_data():
    try:
        with open("assets/market_data.json") as f:
            return json.load(f)
    except Exception as e:
        print(f"  ⚠️  No market_data.json: {e}", flush=True)
        return {}


def format_market_for_prompt(md):
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
            lines.append(f"  {name}: {v['rate']:.2f}%  ({v['chg_bp']:+.1f}bp)")
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
        for etf, v in sorted(md["sectors"].items(), key=lambda x: -x[1]["chg_pct"]):
            arrow = "▲" if v["chg_pct"] >= 0 else "▼"
            lines.append(f"  {v['ko']}: {arrow}{abs(v['chg_pct']):.2f}%")
    if md.get("countries"):
        lines.append("[ 국가별 ETF 수익률 ]")
        sorted_c = sorted(md["countries"].items(), key=lambda x: -x[1]["chg_pct"])
        top3    = [(t, v) for t, v in sorted_c[:3]]
        bottom3 = [(t, v) for t, v in sorted_c[-3:]]
        key4    = ["SPY", "EWY", "MCHI", "EWJ"]
        lines.append("  주요 4개국:")
        for t, v in sorted_c:
            if t in key4:
                arrow = "▲" if v["chg_pct"] >= 0 else "▼"
                lines.append(f"    {v['ko']}({t}): {arrow}{abs(v['chg_pct']):.2f}%")
        lines.append("  상위 3개국:")
        for t, v in top3:
            lines.append(f"    {v['ko']}({t}): +{v['chg_pct']:.2f}%")
        lines.append("  하위 3개국:")
        for t, v in bottom3:
            lines.append(f"    {v['ko']}({t}): {v['chg_pct']:.2f}%")
    return "\n".join(lines)


def call_gemini(client, prompt, required_tags, min_chars=500, max_tokens=16384):
    """Try each model until one succeeds with a valid response."""
    last_error = None
    for model in MODELS:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                print(f"  [Gemini] {model} attempt {attempt}/{MAX_RETRIES} "
                      f"({len(prompt):,} chars)...", flush=True)
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        max_output_tokens=max_tokens,
                        temperature=0.4,
                        thinking_config=types.ThinkingConfig(thinking_level="none"),
                    ),
                )
                text = response.text.strip()
                missing = [t for t in required_tags if t not in text]
                if missing or len(text) < min_chars:
                    print(f"  ⚠️  Invalid ({len(text)} chars, missing: {missing})", flush=True)
                    print(f"  Preview: {text[:300]}", flush=True)
                    raise ValueError(f"Invalid response: missing {missing}")
                print(f"  ✅ {model}: {len(text):,} chars", flush=True)
                return text
            except Exception as e:
                last_error = e
                print(f"  Failed: {e}", flush=True)
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY)
        print(f"  All retries failed for {model}, trying next...", flush=True)
    raise RuntimeError(f"All models failed. Last: {last_error}")


def summarize_and_translate():
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    md = load_market_data()
    market_text = format_market_for_prompt(md)

    transcript_dir = Path("temp/transcripts")
    all_transcripts = ""
    for txt_file in sorted(transcript_dir.glob("*.txt")):
        with open(txt_file, "r", encoding="utf-8") as f:
            all_transcripts += f.read() + "\n\n===\n\n"
    if not all_transcripts.strip():
        raise ValueError("No transcripts found")

    KST   = timezone(timedelta(hours=9))
    today = datetime.now(KST).strftime("%Y년 %m월 %d일")

    # ── Call 1: Market sections ───────────────────────────────────────────
    print("[Gemini] Call 1: Market sections...", flush=True)
    market_prompt = f"""You are a professional Korean financial broadcast journalist.
Today is {today} (Korean Standard Time).

Using ONLY the market data below, generate the market commentary sections of a Korean audio script.
Use EXACTLY these section tags on their own lines:

MARKET DATA:
{market_text}

Output format:

[시장개요]
(2-3 minute market overview. Walk through each index, FX rate, crypto, and interest rates using the exact numbers above. Natural broadcast Korean. Note notable moves. End with overall market sentiment.)

[주요등락]
(1-2 minutes. S&P 500 top movers — top gainers and top losers with brief commentary. Use exact names and % figures from the data.)

[섹터분석]
(1-2 minutes. Sector performance walkthrough from best to worst. Note any notable divergences.)

[국가별]
(1-2 minutes. Follow this structure:
1. 미국(SPY), 한국(EWY), 중국(MCHI), 일본(EWJ) — each with today's return.
2. 상위 3개국 — top 3 best performing countries.
3. 하위 3개국 — bottom 3 worst performing countries.
Concise and broadcast-style.)

Rules:
- Korean only (tickers/company names in English OK)
- No markdown, no bold, no numbering
- Natural conversational broadcast Korean
- Use exact numbers from the data
- Opening one-sentence greeting before [시장개요]"""

    market_script = call_gemini(
        client, market_prompt,
        required_tags=["[시장개요]", "[주요등락]", "[섹터분석]", "[국가별]"],
        min_chars=1000
    )

    # ── Call 2: News section ──────────────────────────────────────────────
    print("[Gemini] Call 2: News section...", flush=True)
    news_prompt = f"""You are a professional Korean financial broadcast journalist.
Today is {today} (Korean Standard Time).

Using ONLY the podcast transcripts below, generate the news section of a Korean audio script.
Use EXACTLY this section tag on its own line:

PODCAST TRANSCRIPTS:
{all_transcripts}

Output format:

[뉴스]
(15-20 minute section. 10-15 news stories from the transcripts. Each story:
- 소제목: short Korean headline (under 20 chars, no bold/stars/numbers)
- 2-3 paragraphs of detail in natural broadcast Korean
Sort by cross-source importance. Combine duplicate stories.
End with one closing sentence after the last story.)

Rules:
- Korean only (company/person names in English OK)
- No markdown, no bold, no numbering
- Natural conversational broadcast Korean
- NEVER repeat the same headline or story — each story must be unique
- Once you have covered 10-15 distinct stories, STOP immediately
- Do not pad or loop — end with a single closing sentence after the last story"""

    news_script = call_gemini(
        client, news_prompt,
        required_tags=["[뉴스]"],
        min_chars=10000,
        max_tokens=65536
    )

    # ── Combine and save ──────────────────────────────────────────────────
    korean_script = market_script + "\n\n" + news_script

    os.makedirs("temp", exist_ok=True)
    with open("temp/korean_script.txt", "w", encoding="utf-8") as f:
        f.write(korean_script)

    print(f"✅ Script saved ({len(korean_script):,} chars total)", flush=True)
    print("\n" + "="*60, flush=True)
    print(korean_script, flush=True)
    print("="*60, flush=True)
    return korean_script


if __name__ == "__main__":
    summarize_and_translate()
