"""
Debug script: runs Call 1 (market) + Call 2 (news from pre-translated texts).
Self-contained — no imports from summarize_translate.py.
"""
import os, json, time
from pathlib import Path
from datetime import datetime, timezone, timedelta
from google import genai
from google.genai import types

MODELS = [
    "gemini-3.1-flash-lite-preview",
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash",
]
MAX_RETRIES = 3
RETRY_DELAY = 10


def call_gemini(client, prompt, required_tags, min_chars=500, max_tokens=4096, no_thinking=True):
    last_error = None
    for model in MODELS:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                print(f"  [Gemini] {model} attempt {attempt}/{MAX_RETRIES} "
                      f"({len(prompt):,} chars)...", flush=True)
                config = types.GenerateContentConfig(
                    max_output_tokens=max_tokens,
                    temperature=0.4,
                )
                if no_thinking:
                    config.thinking_config = types.ThinkingConfig(thinking_budget=0)
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=config,
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


def load_market_data():
    try:
        with open("assets/market_data.json") as f:
            return json.load(f)
    except Exception as e:
        print(f"  ⚠️  No market_data.json: {e}", flush=True)
        return {}


def format_market(md):
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
    if md.get("rates"):
        lines.append("[ 금리 ]")
        for name, v in md["rates"].items():
            lines.append(f"  {name}: {v['rate']:.2f}%  ({v['chg_bp']:+.1f}bp)")
    if md.get("gainers"):
        lines.append("[ S&P 500 상위 상승 종목 ]")
        for g in md["gainers"][:10]:
            lines.append(f"  {g['symbol']} ({g['name']}): +{g['chg_pct']:.2f}%")
    if md.get("losers"):
        lines.append("[ S&P 500 상위 하락 종목 ]")
        for l in md["losers"][:10]:
            lines.append(f"  {l['symbol']} ({l['name']}): {l['chg_pct']:.2f}%")
    if md.get("sectors"):
        lines.append("[ 섹터별 수익률 ]")
        for etf, v in sorted(md["sectors"].items(), key=lambda x: -x[1]["chg_pct"]):
            arrow = "▲" if v["chg_pct"] >= 0 else "▼"
            lines.append(f"  {v['ko']}: {arrow}{abs(v['chg_pct']):.2f}%")
    if md.get("countries"):
        lines.append("[ 국가별 ETF ]")
        sorted_c = sorted(md["countries"].items(), key=lambda x: -x[1]["chg_pct"])
        for t, v in sorted_c[:3]:
            lines.append(f"  상위: {v['ko']}({t}): +{v['chg_pct']:.2f}%")
        for t, v in sorted_c[-3:]:
            lines.append(f"  하위: {v['ko']}({t}): {v['chg_pct']:.2f}%")
    return "\n".join(lines)


def run():
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    md = load_market_data()
    market_text = format_market(md)
    KST = timezone(timedelta(hours=9))
    today = datetime.now(KST).strftime("%Y년 %m월 %d일")

    # ── Call 1: Market sections ───────────────────────────────────────────
    print("[Debug] Call 1: Market sections...", flush=True)
    market_prompt = f"""You are a professional Korean financial broadcast journalist.
Today is {today} (Korean Standard Time).
Using ONLY the market data below, generate market commentary sections.
Use EXACTLY these section tags on their own lines:

MARKET DATA:
{market_text}

[시장개요]
(2-3 minute overview. Use exact numbers. Natural broadcast Korean.)

[주요등락]
(1-2 minutes. Top gainers and losers with commentary.)

[섹터분석]
(1-2 minutes. Sectors from best to worst.)

[국가별]
(미국/한국/중국/일본 returns. Top 3 and bottom 3 countries.)

Rules: Korean only, no markdown, opening greeting before [시장개요]"""

    market_script = call_gemini(
        client, market_prompt,
        required_tags=["[시장개요]", "[주요등락]", "[섹터분석]", "[국가별]"],
        min_chars=1000, max_tokens=8192, no_thinking=True
    )

    # ── Load pre-translated texts ─────────────────────────────────────────
    transcript_dir = Path("temp/transcripts")
    sources = sorted(transcript_dir.glob("*.txt"))
    combined = ""
    print(f"\n[Debug] Loading {len(sources)} pre-translated texts...", flush=True)
    for f in sources:
        text = f.read_text(encoding="utf-8")
        combined += f"[출처: {f.stem}]\n{text}\n\n===\n\n"
        print(f"  ✅ {f.name}: {len(text):,} chars", flush=True)
    print(f"  📦 Combined: {len(combined):,} chars\n", flush=True)

    # ── Call 2: Final news section ────────────────────────────────────────
    news_min_chars = min(10000, int(len(combined) * 0.6))
    print(f"[Debug] Call 2: Final news (min {news_min_chars:,} chars)...", flush=True)
    news_prompt = f"""You are a professional Korean financial broadcast journalist.
Today is {today} (Korean Standard Time).
Using ONLY the Korean texts below, generate the news section.
Use EXACTLY this section tag on its own line:

KOREAN TEXTS:
{combined}

[뉴스]
(10-15 news stories. Each story:
- 소제목: short Korean headline under 20 chars, no bold/stars/numbers
- 2-3 paragraphs of detail in natural broadcast Korean
Sort by importance. Merge duplicate topics across sources.
End with one closing sentence after the last story.)

Rules: Korean only, no markdown, no numbering
NEVER repeat the same headline — each story must be unique
Once you have 10-15 distinct stories, STOP immediately
Do not pad or loop"""

    news_script = call_gemini(
        client, news_prompt,
        required_tags=["[뉴스]"],
        min_chars=news_min_chars,
        max_tokens=32768,
        no_thinking=False   # no thinking_config — all tokens for output
    )

    # ── Save ──────────────────────────────────────────────────────────────
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
