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

# Model fallback chain — ordered by quality, with separate RPD quotas.
# NOTE: gemini-3.1-flash-lite-preview has 8K max output (truncates long text!)
#       so it goes LAST, after gemini-2.5-flash-lite which has 65K output.
MODELS = [
    "gemini-3-flash-preview",       # 65K output, 20 RPD
    "gemini-2.5-flash",             # 65K output, 20 RPD
    "gemini-2.5-flash-lite",        # 65K output, ~100 RPD
    "gemini-3.1-flash-lite-preview", # 8K output only — last resort
]
MAX_RETRIES = 3
RETRY_DELAY = 10

MAX_CHARS_PER_TRANSCRIPT = 20000  # truncate each podcast before translating

# ── Post-translation ad filtering ────────────────────────────────────────────
import re as _re

_AD_PATTERNS = [
    _re.compile(r'.*에서 자세히 알아보.*'),
    _re.compile(r'.*를 방문하세요.*'),
    _re.compile(r'.*닷컴.*에서.*시작하세요.*'),
    _re.compile(r'.*의 지원을 받습니다.*'),
    _re.compile(r'.*의 후원.*받습니다.*'),
    _re.compile(r'.*에서 제공합니다.*'),
    _re.compile(r'.*무료로 사용해 보세요.*'),
    _re.compile(r'.*무료로 시도해.*'),
    _re.compile(r'.*(thehartford|truestage|odoo|care\.org|vantagecore).*', _re.IGNORECASE),
    _re.compile(r'.*구독.*평가.*리뷰.*'),
    _re.compile(r'.*쇼 노트의 링크.*'),
    _re.compile(r'.*팟캐스트.*구독.*'),
    _re.compile(r'.*앱을 다운로드.*'),
    _re.compile(r'.*코드를 사용하.*'),
    _re.compile(r'.*프로모션 코드.*'),
    _re.compile(r'.*후원사.*'),
    _re.compile(r'.*광고.*메시지.*'),
]


def filter_ads(text):
    """Remove lines matching common Korean ad patterns from translated text."""
    lines = text.split('\n')
    filtered = []
    removed = 0
    for line in lines:
        stripped = line.strip()
        if any(p.match(stripped) for p in _AD_PATTERNS):
            removed += 1
            continue
        filtered.append(line)
    if removed:
        print(f"    🚫 Removed {removed} ad line(s)", flush=True)
    return '\n'.join(filtered)


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


def call_gemini(client, prompt, required_tags, min_chars=0, max_tokens=4096, thinking=False, models=None):
    """Try each model until one succeeds with a valid response.
    Only validates required_tags presence — no min_chars rejection to avoid
    wasting API rate limits on retries."""
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
                if missing:
                    print(f"  ⚠️  Missing tags: {missing} ({len(text)} chars)", flush=True)
                    print(f"  Preview: {text[:300]}", flush=True)
                    raise ValueError(f"Missing required tags: {missing}")
                print(f"  ✅ {model}: {len(text):,} chars", flush=True)
                return text
            except Exception as e:
                last_error = e
                err_str = str(e)
                print(f"  Failed: {err_str[:200]}", flush=True)
                # On quota/rate-limit error, skip to next model immediately
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    print(f"  ⚠️  Rate limited on {model} — skipping to next model", flush=True)
                    break
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY)
        print(f"  All retries failed for {model}, trying next...", flush=True)
    raise RuntimeError(f"All models failed. Last: {last_error}")


def summarize_and_translate():
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    md = load_market_data()
    market_text = format_market_for_prompt(md)
    return_mode = md.get("return_mode", "daily")
    is_weekly = return_mode == "weekly"
    period_ko = "지난주" if is_weekly else "오늘"
    period_en = "weekly (Friday-to-Friday)" if is_weekly else "daily"
    print(f"📊 Market return mode: {return_mode}", flush=True)

    KST   = timezone(timedelta(hours=9))
    today = datetime.now(KST).strftime("%Y년 %m월 %d일")

    # ── Call 1: Market sections ───────────────────────────────────────────
    print("[Gemini] Call 1: Market sections...", flush=True)
    market_prompt = f"""You are a professional Korean financial broadcast journalist.
Today is {today} (Korean Standard Time).
IMPORTANT: The figures below are {period_en} returns. Use "{period_ko}" (not "오늘") when referring to performance.

Using ONLY the market data below, generate the market commentary sections of a Korean audio script.
Use EXACTLY these section tags on their own lines:

MARKET DATA:
{market_text}

Output format:

[시장개요]
Cover ONLY these key variables in this order:
1. 주요 지수: S&P 500, NASDAQ, DOW, SOX — price and % change for each
2. 외환: USD/KRW, EUR/USD, DXY — mention only if move is notable (>0.3%)
3. 암호화폐: mention only if move is notable (>2%)
4. 금리: 미국 10년물 국채 금리 only — as a key benchmark
   - 연방기금금리: mention ONLY if chg_bp is non-zero (i.e. Fed actually changed rates)
5. One sentence on overall market sentiment
Keep concise — 1-2 minutes max.

[주요등락]
Top 3 gainers and top 3 losers from S&P 500. Name, ticker, % change, one-line reason if notable.
1 minute max.

[섹터분석]
Best 3 and worst 3 sectors only. Skip middle sectors unless there is a notable divergence.
1 minute max.

[국가별]
1. 미국(SPY), 한국(EWY), 중국(MCHI), 일본(EWJ) — each with today's return.
2. 상위 3개국 — top 3 best performing countries.
3. 하위 3개국 — bottom 3 worst performing countries.
1 minute max.

Rules:
- Korean only (tickers/company names in English OK)
- No markdown, no bold, no numbering
- Natural conversational broadcast Korean
- Use exact numbers from the data
- Opening one-sentence greeting before [시장개요]"""

    market_script = call_gemini(
        client, market_prompt,
        required_tags=["[시장개요]", "[주요등락]", "[섹터분석]", "[국가별]"],
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
This is a FULL TRANSLATION task, not a summary. Preserve all details, data points,
quotes, and analysis. The Korean output should be roughly the same length as the
English input (Korean text is naturally more compact, but do NOT omit content).

SKIP these completely — do NOT translate any of the following:
- Sponsor messages ("brought to you by...", "sponsored by...", "support for this comes from...")
- Product/service promotions (IBM, Chase, Hartford, Odoo, TrueStage, CARE, VantageCore, etc.)
- Insurance, credit score, business software, charity pitches
- Calls to action ("visit our website", "download our app", "use code...", "learn more at...")
- Podcast self-promotion ("subscribe", "rate and review", "show notes", "links in description")
- Any paragraph that is clearly an advertisement, not news content

Translate ALL actual news, analysis, interviews, and commentary — do not summarize or shorten.
Write in natural Korean prose — no bullet points, no headers, no tags.
Do NOT add any intro or closing sentence — just the translated content.

TRANSCRIPT:
{text}"""

        try:
            summary = call_gemini(
                client, summary_prompt,
                required_tags=[],
                max_tokens=65536
            )
            summary = filter_ads(summary)
            summaries.append({"source": txt_file.stem, "summary": summary})
            print(f"  ✅ Summary: {len(summary):,} chars", flush=True)
            print(f"  --- Summary preview ---\n{summary}\n  ---", flush=True)
        except Exception as e:
            print(f"  ⚠️  Summary failed for {txt_file.name}: {e} — skipping", flush=True)

    if not summaries:
        raise ValueError("No summaries produced")

    # ── Split summaries into news vs research ──────────────────────────────
    # Load source types from sources.json
    import json as _json
    _source_types = {}
    try:
        with open("sources.json", "r", encoding="utf-8") as f:
            for src in _json.load(f):
                # Map filename stem to type (e.g. "WSJ_Whats_News" → "news")
                _source_types[src["name"].replace(" ", "_").replace("'", "")] = src.get("type", "news")
    except Exception:
        pass

    news_summaries = []
    research_summaries = []
    for s in summaries:
        source_type = _source_types.get(s["source"], "news")
        if source_type == "research":
            research_summaries.append(s)
        else:
            news_summaries.append(s)

    print(f"\n  📰 News sources: {len(news_summaries)}", flush=True)
    print(f"  🔬 Research sources: {len(research_summaries)}", flush=True)

    _STORY_FORMAT = """
Then write each story in this EXACT format:

소제목 (short Korean headline, under 20 chars)
본문 내용 (body paragraph, natural broadcast Korean)

CRITICAL FORMATTING RULES:
- Title and body must be on consecutive lines (single newline between them)
- Stories must be separated by a BLANK LINE (double newline)
- Korean only (company/person names in English OK)
- No markdown, no bold, no numbering, no bullet points
- Each story must be unique — never repeat the same topic
- Once all unique stories are covered, STOP"""

    _GEMINI_MODELS = ["gemini-3-flash-preview", "gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-3.1-flash-lite-preview"]

    # ── Call 2a: News section ────────────────────────────────────────────
    news_script = ""
    if news_summaries:
        news_combined = ""
        for s in news_summaries:
            news_combined += f"[출처: {s['source']}]\n{s['summary']}\n\n===\n\n"
        print(f"\n[Gemini] Call 2a: News section ({len(news_combined):,} chars)...", flush=True)

        news_prompt = f"""You are a professional Korean financial broadcast journalist.
Today is {today} (Korean Standard Time).

Below are Korean translations from several NEWS podcasts. The same story may appear in multiple sources.

Your task:
1. Identify all unique news stories across all sources
2. Where the same story appears in multiple sources, COMBINE them into one richer story
3. Sort stories by importance

KOREAN TEXTS:
{news_combined}

Your response MUST start with this exact tag on its own line:
[뉴스]
{_STORY_FORMAT}"""

        news_script = call_gemini(
            client, news_prompt,
            required_tags=["[뉴스]"],
            max_tokens=32768,
            thinking=False,
            models=_GEMINI_MODELS
        )

    # ── Call 2b: Research/analysis section ────────────────────────────────
    research_script = ""
    if research_summaries:
        research_combined = ""
        for s in research_summaries:
            research_combined += f"[출처: {s['source']}]\n{s['summary']}\n\n===\n\n"
        print(f"\n[Gemini] Call 2b: Research section ({len(research_combined):,} chars)...", flush=True)

        research_prompt = f"""You are a professional Korean financial broadcast journalist.
Today is {today} (Korean Standard Time).

Below are Korean translations from INVESTMENT RESEARCH podcasts (Morgan Stanley, Goldman Sachs, JP Morgan, Barclays).
These contain in-depth market analysis, investment outlooks, and expert commentary.

CRITICAL: Preserve as much detail as possible. These are expert insights that viewers value.
Do NOT summarize or shorten — translate and organize faithfully.
Keep specific data points, forecasts, analyst names, and reasoning.

Your task:
1. Organize each research piece as a separate story
2. Preserve the depth and detail of each analysis
3. Do NOT merge different analysts' views — keep them as separate stories

KOREAN TEXTS:
{research_combined}

Your response MUST start with this exact tag on its own line:
[리서치]
{_STORY_FORMAT}"""

        research_script = call_gemini(
            client, research_prompt,
            required_tags=["[리서치]"],
            max_tokens=65536,
            thinking=False,
            models=_GEMINI_MODELS
        )

    # ── Clean up closing sentences from news/research (will add one at the end)
    def _strip_closing(text):
        lines = text.split("\n")
        return "\n".join(l for l in lines if not l.strip().startswith("지금까지")).strip()

    if news_script:
        news_script = _strip_closing(news_script)
    if research_script:
        research_script = _strip_closing(research_script)

    # ── Combine and save ─────────────────────────────────────────────────
    # Broadcast order: 시장개요 → 뉴스 → 리서치 → 주요등락 → 섹터분석 → 국가별 → 마감
    import re as _re
    _sections = {}
    _current_tag = None
    _current_lines = []
    _intro_lines = []
    for line in market_script.split("\n"):
        stripped = line.strip()
        if stripped in ["[시장개요]", "[주요등락]", "[섹터분석]", "[국가별]"]:
            if _current_tag:
                _sections[_current_tag] = "\n".join(_current_lines)
            _current_tag = stripped
            _current_lines = [line]
        elif _current_tag:
            _current_lines.append(line)
        else:
            _intro_lines.append(line)
    if _current_tag:
        _sections[_current_tag] = "\n".join(_current_lines)

    _intro = "\n".join(_intro_lines).strip()
    _broadcast_order = ["[시장개요]", "[뉴스]", "[리서치]", "[주요등락]", "[섹터분석]", "[국가별]"]
    _parts = []
    if _intro:
        _parts.append(_intro)
    for tag in _broadcast_order:
        if tag == "[뉴스]" and news_script:
            _parts.append(news_script.strip())
        elif tag == "[리서치]" and research_script:
            _parts.append(research_script.strip())
        elif tag in _sections:
            _parts.append(_sections[tag].strip())

    # Add closing sentence after all sections
    _parts.append(f"지금까지 {today} 주요 경제 뉴스였습니다.")

    korean_script = "\n\n".join(_parts)

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
