"""
Step 3: Generate Korean script in separate Gemini calls:
  Call 1:       [시장개요] + [주요등락] + [섹터분석] + [국가별] — market data only
  Pass 1 (N):   Translate each podcast transcript individually into Korean
  Call 2 (final): [뉴스] — from combined Korean summaries
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

MAX_CHARS_PER_TRANSCRIPT = 8000  # truncate each podcast before translating


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
        key4 = ["SPY", "EWY", "MCHI", "EWJ"]
        lines.append("  주요 4개국:")
        for t, v in sorted_c:
            if t in key4:
                arrow = "▲" if v["chg_pct"] >= 0 else "▼"
                lines.append(f"    {v['ko']}({t}): {arrow}{abs(v['chg_pct']):.2f}%")
        lines.append("  상위 3개국:")
        for t, v in sorted_c[:3]:
            lines.append(f"    {v['ko']}({t}): +{v['chg_pct']:.2f}%")
        lines.append("  하위 3개국:")
        for t, v in sorted_c[-3:]:
            lines.append(f"    {v['ko']}({t}): {v['chg_pct']:.2f}%")
    return "\n".join(lines)


def call_gemini(client, prompt, required_tags, min_chars=500, max_tokens=4096, thinking=False, models=None):
    """Try each model until one succeeds with a valid response."""
    last_error = None
    for model in (models or MODELS):
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                print(f"  [Gemini] {model} attempt {attempt}/{MAX_RETRIES} "
                      f"({len(prompt):,} chars)...", flush=True)
                cfg = types.GenerateContentConfig(
                    max_output_tokens=max_tokens,
                    temperature=0.4,
                )
                if not thinking:
                    cfg.thinking_config = types.ThinkingConfig(thinking_budget=0)
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=cfg,
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
        min_chars=1000,
        max_tokens=8192
    )

    # ── Pass 1: Translate each podcast into Korean ────────────────────────
    transcript_dir = Path("temp/transcripts")
    transcript_files = sorted(transcript_dir.glob("*.txt"))
    if not transcript_files:
        raise ValueError("No transcripts found")

    print(f"\n[Gemini] Pass 1: Translating {len(transcript_files)} podcasts into Korean...", flush=True)

    summaries = []
    for txt_file in transcript_files:
        with open(txt_file, "r", encoding="utf-8") as f:
            text = f.read()
        original_len = len(text)
        if len(text) > MAX_CHARS_PER_TRANSCRIPT:
            text = text[:MAX_CHARS_PER_TRANSCRIPT]
        print(f"\n  📄 {txt_file.name}: {original_len:,} → {len(text):,} chars", flush=True)

        summary_prompt = f"""Translate the following English financial podcast transcript into Korean.
Write in natural Korean prose — no bullet points, no headers, no tags.
Do NOT add any intro or closing sentence — just the translated content.
Focus on preserving all key details: financial events, market moves, economic data, company news, geopolitical developments.

TRANSCRIPT:
{text}"""

        try:
            summary = call_gemini(
                client, summary_prompt,
                required_tags=[],
                min_chars=100,
                max_tokens=8192
            )
            summaries.append({"source": txt_file.stem, "summary": summary})
            print(f"  ✅ Summary: {len(summary):,} chars", flush=True)
            print(f"  --- Summary preview ---\n{summary}\n  ---", flush=True)
        except Exception as e:
            print(f"  ⚠️  Summary failed for {txt_file.name}: {e} — skipping", flush=True)

    if not summaries:
        raise ValueError("No summaries produced")

    combined = ""
    for s in summaries:
        combined += f"[출처: {s['source']}]\n{s['summary']}\n\n===\n\n"
    print(f"\n  📦 Combined: {len(combined):,} chars from {len(summaries)} sources\n", flush=True)

    # ── Call 2: Final news section — uses gemini-2.5-flash for reliable long output ──
    print("[Gemini] Call 2: Final news section...", flush=True)
    news_prompt = f"""You are a professional Korean financial broadcast journalist.
Today is {today} (Korean Standard Time).

Below are Korean translations from several financial podcasts. The same story may appear in multiple sources.

Your task:
1. Identify all unique news stories across all sources
2. Where the same story appears in multiple sources, COMBINE them into one richer story
3. Write the final broadcast script

KOREAN TEXTS:
{combined}

Your response MUST start with this exact tag on its own line:
[뉴스]

Then write each story:
- 소제목: short Korean headline (under 20 chars, no bold, no stars, no numbers)
- 중요도에 따라 자연스러운 방송 한국어로 작성 (length based on importance)

Sort stories by importance. End with a single closing sentence.

Rules:
- Korean only (company/person names in English OK)
- No markdown, no bold, no numbering
- Each story must be unique — never repeat the same topic
- Once all unique stories are covered, STOP"""

    # min_chars = 30% of combined size, floor 500, cap 10000
    news_min_chars = max(500, min(10000, int(len(combined) * 0.5)))
    print(f"  🎯 News min_chars set to {news_min_chars:,} (50% of {len(combined):,} combined)", flush=True)

    news_script = call_gemini(
        client, news_prompt,
        required_tags=["[뉴스]"],
        min_chars=news_min_chars,
        max_tokens=32768,
        thinking=False,
        models=["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-3.1-flash-lite-preview"]
    )

    # ── Combine and save ──────────────────────────────────────────────────
    korean_script = market_script + "\n\n" + news_script

    os.makedirs("temp", exist_ok=True)
    with open("temp/korean_script.txt", "w", encoding="utf-8") as f:
        f.write(korean_script)

    print(f"\n✅ Script saved ({len(korean_script):,} chars total)", flush=True)
    print("\n" + "="*60, flush=True)
    print(korean_script, flush=True)
    print("="*60, flush=True)
    return korean_script


if __name__ == "__main__":
    summarize_and_translate()
