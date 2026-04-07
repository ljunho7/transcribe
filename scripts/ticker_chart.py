#!/usr/bin/env python3
"""
ticker_chart.py
Reads a Korean finance news script, extracts relevant identifiers per section
using Groq (Llama 3.3 70b), then generates charts from two sources:

  • yfinance  → market prices, ETFs, futures, indices (daily)
  • FRED API  → macro economic series (monthly/weekly)  prefix: FRED:

Usage:
    python ticker_chart.py --script news_script.txt
    python ticker_chart.py --script news_script.txt --skip-groq   # reuse ticker_map.json

Requirements:
    pip install groq yfinance fredapi matplotlib pandas
    export GROQ_API_KEY=your_key_here
    export FRED_API_KEY=your_key_here   # free at fred.stlouisfed.org
"""

import argparse
import json
import os
import re
import sys

# ── Suppress noisy deprecation warnings from yfinance internals ──────────────
import warnings
warnings.filterwarnings("ignore", message=".*utcnow.*deprecated.*")

# ── Dependency check ─────────────────────────────────────────────────────────
try:
    from groq import Groq
except ImportError:
    sys.exit("Missing: pip install groq")
try:
    import yfinance as yf
except ImportError:
    sys.exit("Missing: pip install yfinance")
try:
    from fredapi import Fred
except ImportError:
    sys.exit("Missing: pip install fredapi")
try:
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    import matplotlib.ticker as mticker
    from matplotlib import font_manager
except ImportError:
    sys.exit("Missing: pip install matplotlib")

# ── Korean font setup ─────────────────────────────────────────────────────────
# Matplotlib uses a Latin-only default font. Set a Korean-capable font so
# Hangul glyphs in chart titles (e.g. 월간 변화량) render correctly.
_KOREAN_FONTS = [
    "Malgun Gothic",    # Windows built-in
    "AppleGothic",      # macOS built-in
    "NanumGothic",      # Linux / manual install
    "NanumBarunGothic",
    "Noto Sans CJK KR",
    "DejaVu Sans",      # fallback — no Korean but at least no crash
]
_available = {f.name for f in font_manager.fontManager.ttflist}
for _font in _KOREAN_FONTS:
    if _font in _available:
        plt.rcParams["font.family"] = _font
        break
else:
    # Name-based lookup failed — try finding the font file directly on disk
    import platform, glob
    _found = False
    if platform.system() == "Windows":
        _candidates = glob.glob("C:/Windows/Fonts/malgun*.ttf") + \
                      glob.glob("C:/Windows/Fonts/NanumGothic*.ttf")
    elif platform.system() == "Linux":
        _candidates = glob.glob("/usr/share/fonts/**/Noto*CJK*.otf", recursive=True) + \
                      glob.glob("/usr/share/fonts/**/Noto*CJK*.ttc", recursive=True) + \
                      glob.glob("/usr/share/fonts/**/NanumGothic*.ttf", recursive=True)
    else:
        _candidates = []
    for _path in _candidates:
            try:
                font_manager.fontManager.addfont(_path)
                _prop = font_manager.FontProperties(fname=_path)
                plt.rcParams["font.family"] = _prop.get_name()
                _found = True
                break
            except Exception:
                continue
    if not _found:
        # Last resort: just suppress the glyph warnings, chart still saves fine
        import warnings
        warnings.filterwarnings("ignore", message="Glyph .* missing from")
try:
    import pandas as pd
except ImportError:
    sys.exit("Missing: pip install pandas")

# ── Config ───────────────────────────────────────────────────────────────────
GROQ_API_KEY    = os.environ.get("GROQ_API_KEY", "")
FRED_API_KEY    = os.environ.get("FRED_API_KEY", "")
AV_API_KEY      = os.environ.get("ALPHA_VANTAGE_API_KEY", "")
GROQ_MODEL      = "llama-3.3-70b-versatile"
OUTPUT_DIR      = "temp/charts"
TICKER_MAP_FILE = "temp/ticker_map.json"
PRICE_PERIOD    = "1mo"    # yfinance lookback
FRED_MONTHS     = 24       # how many months of FRED history to show

# FRED_YOY_SERIES and FRED_LABELS loaded from config below (after _ticker_cfg init)

# ── Keyword-to-ticker mapping (loaded from config/ticker_config.json) ────────
TICKER_CONFIG_FILE = os.path.join(os.path.dirname(__file__), "..", "config", "ticker_config.json")

def _load_ticker_config():
    try:
        with open(TICKER_CONFIG_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"  ⚠  Could not load {TICKER_CONFIG_FILE}: {e}", flush=True)
        return {"keyword_tickers": {}, "categories": {}}

_ticker_cfg = _load_ticker_config()
KEYWORD_TICKERS = _ticker_cfg.get("keyword_tickers", {})
FRED_YOY_SERIES = set(_ticker_cfg.get("fred_yoy_series", []))
FRED_LABELS     = _ticker_cfg.get("fred_labels", {})


def classify_story(title, body):
    """Classify a news story by counting keyword hits per category.
    Returns: 'macro', 'company', 'geopolitical', 'market', or 'other'.
    Title hits count double to weight the story's primary focus."""
    t_low = title.lower()
    b_low = body.lower()

    categories = _ticker_cfg.get("categories", {})
    scores = {}
    for cat, keywords in categories.items():
        title_hits = sum(1 for w in keywords if w in t_low)
        body_hits  = sum(1 for w in keywords if w in b_low)
        scores[cat] = title_hits * 2 + body_hits  # title counts double

    if not scores:
        return "other"
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return "other"
    return best


def keyword_scan(text):
    """Scan text for known keywords and return matching tickers (deduplicated)."""
    found = []
    for keyword, ticker in KEYWORD_TICKERS.items():
        if keyword in text and ticker not in found:
            found.append(ticker)
    return found


def postprocess_tickers(section_data, sections):
    """Clean up Groq output: dedup, filter non-financial, remove fixed-section overlaps."""
    # Collect tickers from fixed sections
    FIXED = {"시장개요", "주요등락", "섹터분석", "국가별"}
    fixed_tickers = set()
    for sec in FIXED:
        for t in section_data.get(sec, {}).get("tickers", []):
            fixed_tickers.add(t)

    seen_tickers = set()

    for section, entry in section_data.items():
        if section in FIXED:
            continue

        tickers = entry.get("tickers", [])
        if not tickers:
            continue

        # Extract title from section key
        title = section.replace("뉴스: ", "")
        body = sections.get(section, "")
        story_type = classify_story(title, body)

        # 1. Non-financial stories → clear tickers
        if story_type == "other":
            print(f"    🚫 [{story_type}] {title[:30]} — clearing tickers", flush=True)
            entry["tickers"] = []
            continue

        # 2. Macro stories → prefer FRED, add keyword suggestions
        if story_type == "macro":
            fred_tickers = [t for t in tickers if t.startswith("FRED:")]
            keyword_hits = keyword_scan(title + " " + body)
            keyword_fred = [t for t in keyword_hits if t.startswith("FRED:")]
            # Merge: Groq FRED + keyword FRED (deduplicated)
            merged = list(dict.fromkeys(fred_tickers + keyword_fred))
            tickers = merged if merged else tickers  # fallback to Groq if no FRED found

        # 3. Geopolitical → add commodity keyword suggestions
        if story_type == "geopolitical":
            keyword_hits = keyword_scan(title + " " + body)
            commodity_hits = [t for t in keyword_hits
                              if not t.startswith("FRED:") and not t.startswith("^")]
            for t in commodity_hits:
                if t not in tickers:
                    tickers.append(t)

        # 4. Remove tickers already in fixed sections
        tickers = [t for t in tickers if t not in fixed_tickers]

        # 5. Deduplicate across news sections (first occurrence wins)
        unique = []
        for t in tickers:
            if t not in seen_tickers:
                unique.append(t)
                seen_tickers.add(t)
        tickers = unique

        if tickers != entry["tickers"]:
            print(f"    🔧 [{story_type}] {title[:30]}: {entry['tickers']} → {tickers}",
                  flush=True)

        entry["tickers"] = tickers

    return section_data


# ── 1. Section parser ─────────────────────────────────────────────────────────

def parse_sections(text):
    sections = {}

    fixed_tags = ["시장개요", "주요등락", "섹터분석", "국가별"]
    for tag in fixed_tags:
        m = re.search(rf'\[{tag}\]\s*(.*?)(?=\[|\Z)', text, re.DOTALL)
        if m:
            sections[tag] = m.group(1).strip()

    m = re.search(r'\[뉴스\](.*?)(?=\Z)', text, re.DOTALL)
    if m:
        news_block = m.group(1).strip()
        # Stories are separated by blank lines (double newline).
        # Within each story, title and body are on consecutive lines (single newline).
        chunks = [c.strip() for c in re.split(r'\n{2,}', news_block) if c.strip()]
        for chunk in chunks:
            lines = chunk.split('\n', 1)
            title = lines[0].strip()
            body  = lines[1].strip() if len(lines) > 1 else ""
            # Skip closing remarks
            if title.startswith('오늘 준비한') or title.startswith('지금까지'):
                break
            # Skip chunks with no body (single-line fragments)
            if not body:
                continue
            sections[f'뉴스: {title}'] = body

    return sections


# ── 2. Groq extraction ────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are a US financial markets expert fluent in Korean.
Given a JSON object mapping Korean section names to Korean financial news text,
return a JSON object mapping the SAME section names to objects with two fields:
  "tickers"  — array of market/macro identifiers
  "bullets"  — array of short Korean bullet points (뉴스: sections only)

──────────────────────────────────────────
TICKERS — Two identifier types supported:

TYPE 1 — yfinance tickers (market prices, updated daily):
  - US stocks            →  plain symbol              (AAPL, TSLA, DAL, NKE, STZ)
  - US indices           →  caret prefix               (^GSPC, ^IXIC, ^DJI, ^TNX)
  - Commodity futures    →  equals-F suffix             (CL=F for WTI crude, BZ=F for Brent)
  - Forex                →  equals-X suffix             (EURUSD=X)
  - ETFs / sector funds  →  plain symbol               (SPY, XLK, XLE, EWJ, EWY)

TYPE 2 — FRED macro series (official economic releases):
  Prefix with "FRED:" — ONLY use series IDs from this exact list:
  - FRED:PAYEMS      → US Nonfarm Payrolls
  - FRED:UNRATE      → US Unemployment Rate
  - FRED:CPIAUCSL    → Consumer Price Index (CPI)
  - FRED:PCEPILFE    → Core PCE inflation
  - FRED:FEDFUNDS    → Federal Funds Rate
  - FRED:UMCSENT     → Consumer Sentiment (U of Michigan)
  - FRED:RSXFS       → Retail Sales (ex food services)
  - FRED:ICSA        → Initial Jobless Claims
  - FRED:HOUST       → Housing Starts
  - FRED:GDP         → Gross Domestic Product
  - FRED:DCOILWTICO  → WTI Crude Oil Price
  - FRED:DEXUSEU     → USD/EUR Exchange Rate
  - FRED:DGS10       → 10-Year Treasury Yield
  - FRED:MICH        → U of Michigan Inflation Expectation
  - FRED:EXPINF1YR   → 1-Year Expected Inflation
  - FRED:EXPINF10YR  → 10-Year Expected Inflation
  - FRED:REAINTRATREARAT10Y → 10-Year Real Interest Rate
  - FRED:T10YIE      → 10-Year Breakeven Inflation Rate
  - FRED:GASREGW     → US Regular Gas Price
  - FRED:APU0000708111 → Egg Price (per dozen)
  - FRED:GOLDAMGBD228NLBM → Gold Price
  - FRED:PCOCOUSDM   → Cocoa Price
  - FRED:PALUMUSDM   → Aluminum Price
  - FRED:CBBTCUSD    → Bitcoin Price (Coinbase)
  - FRED:CBETHUSD    → Ethereum Price (Coinbase)

  CRITICAL: Never invent FRED series IDs. Only use IDs from the list above.
  For crude oil always use FRED:DCOILWTICO, never FRED:CRUDE or any other variant.

Ticker rules:
  - Each section's text starts with [MAX N tickers, MAX M bullets]
    You MUST NOT exceed those limits. Use FEWER if the story doesn't
    mention that many distinct instruments.
  - Use [] if no clearly relevant identifier exists
  - Only include identifiers you are highly confident are correct
  - CRITICAL: Only include a STOCK ticker if the story explicitly mentions
    its price movement (e.g., "17% 급등", "14% 하락", "$412 기록").
    Do NOT include tickers for companies that are merely mentioned by name
    without specific price/performance data.
  - For non-financial stories (science, religion, environment, sports),
    return empty tickers []

──────────────────────────────────────────
BULLETS — Korean bullet points for 뉴스: sections only:
  - Follow the [MAX M bullets] limit specified in each section's text
  - Use FEWER bullets if the story has fewer key facts
  - Each bullet: short Korean phrase, 20 characters or fewer
  - No bullet character — just the text (it will be added in rendering)
  - For non-뉴스 sections: always use empty array []

──────────────────────────────────────────
Output format example:
{
  "시장개요": {"tickers": ["^GSPC", "^IXIC"], "bullets": []},
  "뉴스: 글로벌 증시 동향 (long story)": {
    "tickers": ["^GSPC", "CL=F", "INTC", "META", "NKE"],
    "bullets": ["3대 지수 3% 상승", "브렌트유 8% 급등", "인텔 17% 급등", "메타·알파벳 반등", "나이키 14% 폭락"]
  },
  "뉴스: 나이키 중국 매출 경고 (short story)": {
    "tickers": ["NKE"],
    "bullets": ["중국 매출 20% 감소 경고", "7분기 연속 감소"]
  }
}

Return ONLY the JSON object — no markdown fences, no explanation."""


def extract_section_data(sections):
    """Call Groq and return {section: {tickers, bullets}} for all sections."""
    if not GROQ_API_KEY:
        sys.exit("GROQ_API_KEY environment variable not set.")

    client = Groq(api_key=GROQ_API_KEY)

    # Shorten section keys to save tokens — Groq echoes keys in its response.
    # Long paragraph-as-title keys can eat the entire token budget.
    short_to_full = {}
    compact = {}
    for i, (k, v) in enumerate(sections.items()):
        short_key = k[:60] if len(k) > 60 else k
        # Ensure uniqueness
        if short_key in compact:
            short_key = f"{short_key}…{i}"
        short_to_full[short_key] = k
        # Compute per-section ticker/bullet limits based on text length
        full_len = len(v)
        if full_len < 200:
            max_t, max_b = 1, 2
        elif full_len < 500:
            max_t, max_b = 2, 3
        elif full_len < 1000:
            max_t, max_b = 3, 4
        else:
            max_t, max_b = min(5, 10), min(5, 10)
        compact[short_key] = f"[MAX {max_t} tickers, MAX {max_b} bullets] " + v[:400]

    user_message = json.dumps(compact, ensure_ascii=False, indent=2)

    print(f"Calling Groq ({GROQ_MODEL}) for ticker + bullet extraction...")
    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_message},
        ],
        temperature=0.1,
        max_tokens=4000,
    )

    raw = response.choices[0].message.content.strip()
    raw = re.sub(r'^```(?:json)?\s*', '', raw)
    raw = re.sub(r'\s*```$', '',       raw)

    print("── Groq raw response ────────────────────")
    print(raw)
    print("─────────────────────────────────────────\n")

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        sys.exit(f"JSON parse error from Groq response: {e}\nRaw:\n{raw}")

    # Map short keys back to full section names and normalise fields
    result = {}
    for short_key, val in parsed.items():
        full_key = short_to_full.get(short_key, short_key)
        if isinstance(val, list):
            result[full_key] = {"tickers": val, "bullets": []}
        else:
            result[full_key] = {
                "tickers": val.get("tickers", []),
                "bullets": val.get("bullets", []),
            }

    # Post-process: classify stories, dedup, filter non-financial, add keyword hints
    print("\n── Post-processing tickers ──────────────")
    result = postprocess_tickers(result, sections)

    return result


# ── 3. Chart generation ───────────────────────────────────────────────────────

def _safe_filename(section_label, identifier):
    # Use section type (e.g. "뉴스") + ticker only
    section_type = section_label.split(":")[0].split("：")[0].strip()
    safe_type  = re.sub(r'[^\w]', '_', section_type)
    safe_ident = re.sub(r'[^\w]', '_', identifier)
    return os.path.join(OUTPUT_DIR, f"{safe_type}__{safe_ident}.png")


def _fetch_alpha_vantage(ticker):
    """Fetch ~30 days of daily closes from Alpha Vantage.
    Returns (pd.Series of closes, name_str) or (None, None) on failure."""
    import requests as req

    if not AV_API_KEY:
        return None, None

    # Alpha Vantage doesn't support indices (^GSPC) or futures (CL=F) —
    # skip these rather than using proxy ETFs which have different price levels
    if ticker.startswith("^") or ticker.endswith("=F") or ticker.endswith("=X"):
        return None, None

    av_ticker = ticker

    try:
        url = (f"https://www.alphavantage.co/query?function=TIME_SERIES_DAILY"
               f"&symbol={av_ticker}&outputsize=compact&apikey={AV_API_KEY}")
        r = req.get(url, timeout=15)
        data = r.json()

        if "Time Series (Daily)" not in data:
            err = data.get("Note") or data.get("Information") or data.get("Error Message", "")
            print(f"    ⚠  AV: {av_ticker}: {err[:80]}", flush=True)
            return None, None

        ts = data["Time Series (Daily)"]
        # Parse into pandas Series, take last ~25 trading days
        import pandas as pd
        dates  = sorted(ts.keys())[-25:]
        closes = pd.Series(
            {pd.Timestamp(d): float(ts[d]["4. close"]) for d in dates}
        )
        closes.index.name = "Date"

        # Get name from search endpoint (optional, don't fail on it)
        name = ""
        try:
            search_url = (f"https://www.alphavantage.co/query?function=SYMBOL_SEARCH"
                          f"&keywords={av_ticker}&apikey={AV_API_KEY}")
            sr = req.get(search_url, timeout=10).json()
            matches = sr.get("bestMatches", [])
            if matches:
                name = matches[0].get("2. name", "")
        except Exception:
            pass

        return closes, name

    except Exception as exc:
        print(f"    ⚠  AV error for {av_ticker}: {exc}", flush=True)
        return None, None


def prefetch_price_data(tickers):
    """Download price history + names. Tries yfinance first, falls back
    to Alpha Vantage on rate-limit errors.
    Returns {ticker: {"close": Series, "name": str}}."""
    if not tickers:
        return {}

    import time
    print(f"\n📦  Downloading {len(tickers)} tickers (yfinance → Alpha Vantage fallback) ...",
          flush=True)

    cache = {}
    yf_blocked = False  # once yfinance is rate-limited, skip it for remaining tickers

    for i, ticker in enumerate(tickers):
        if i > 0:
            time.sleep(1.0)

        # ── Try yfinance first (unless already blocked) ──────────────
        if not yf_blocked:
            try:
                t = yf.Ticker(ticker)
                hist = t.history(period=PRICE_PERIOD)
                if not hist.empty and len(hist) >= 3:
                    closes = hist["Close"].squeeze()
                    try:
                        name = (t.info.get("shortName") or t.info.get("longName") or "")
                    except Exception:
                        name = ""
                    cache[ticker] = {"close": closes, "name": name}
                    print(f"    ✓  {ticker} ({name or '?'}): {len(closes)} rows [yfinance]",
                          flush=True)
                    continue
            except Exception as exc:
                if "Too Many Requests" in str(exc) or "Rate" in str(exc):
                    print(f"    ⚠  yfinance rate-limited — switching to Alpha Vantage for all remaining",
                          flush=True)
                    yf_blocked = True
                else:
                    print(f"    ⚠  yfinance {ticker}: {exc}", flush=True)

        # ── Fallback: Alpha Vantage ──────────────────────────────────
        closes, name = _fetch_alpha_vantage(ticker)
        if closes is not None and len(closes) >= 3:
            cache[ticker] = {"close": closes, "name": name}
            print(f"    ✓  {ticker} ({name or '?'}): {len(closes)} rows [Alpha Vantage]",
                  flush=True)
        else:
            print(f"    ✗  {ticker}: no data from yfinance or Alpha Vantage", flush=True)

    print(f"    📊 Fetched {len(cache)}/{len(tickers)} tickers", flush=True)
    return cache


# Module-level cache filled by generate_charts() before chart rendering
_price_cache = {}


def make_price_chart(ticker, output_path):
    """1-month daily price chart. Dark background, green/red line."""
    try:
        if ticker in _price_cache:
            close     = _price_cache[ticker]["close"]
            full_name = _price_cache[ticker]["name"]
        else:
            # Fallback: try Alpha Vantage then yfinance
            close, full_name = _fetch_alpha_vantage(ticker)
            if close is None or len(close) < 3:
                try:
                    t    = yf.Ticker(ticker)
                    data = t.history(period=PRICE_PERIOD)
                    if data.empty or len(data) < 3:
                        print(f"\n    ⚠  No price data for {ticker}")
                        return False
                    close = data["Close"].squeeze()
                    try:
                        full_name = (t.info.get("shortName") or t.info.get("longName") or "")
                    except Exception:
                        full_name = ""
                except Exception:
                    print(f"\n    ⚠  No price data for {ticker}")
                    return False

        if len(close) < 3:
            print(f"\n    ⚠  Not enough data for {ticker}")
            return False

        pct   = (close.iloc[-1] / close.iloc[0] - 1) * 100
        color = "#00e676" if pct >= 0 else "#ff5252"
        title_line = full_name if full_name else ticker

        fig, ax = plt.subplots(figsize=(12, 9))
        fig.patch.set_facecolor("#0d1117")
        ax.set_facecolor("#161b22")

        ax.plot(close.index, close.values, color=color, linewidth=3, zorder=3)
        ax.fill_between(close.index, close.values, close.min(),
                        alpha=0.06, color=color)

        # Y-axis: zoom into the actual price range with 10% padding
        lo, hi  = close.min(), close.max()
        pad     = (hi - lo) * 0.10 if hi != lo else hi * 0.05
        ax.set_ylim(lo - pad, hi + pad)

        # Annotate last price on the right edge
        ax.annotate(
            f"{close.iloc[-1]:,.2f}",
            xy=(close.index[-1], close.iloc[-1]),
            xytext=(8, 0), textcoords="offset points",
            color=color, fontsize=14, fontweight="bold", va="center"
        )

        ax.set_title(f"{title_line}   {pct:+.2f}%  (1개월)",
                     color="white", fontsize=20, pad=14, fontweight="bold")
        ax.tick_params(colors="#bbbbbb", labelsize=13)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
        ax.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=0))
        plt.xticks(rotation=0, ha="center")
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(
            lambda x, _: f"{x:,.0f}" if abs(x) >= 100 else f"{x:.2f}"
        ))
        for spine in ax.spines.values():
            spine.set_edgecolor("#30363d")
        ax.grid(axis="y", color="#30363d", linestyle="--", linewidth=0.6, zorder=0)

        fig.subplots_adjust(left=0.12, right=0.92, top=0.90, bottom=0.10)
        plt.savefig(output_path, dpi=100, bbox_inches="tight",
                    facecolor=fig.get_facecolor())
        plt.close()
        return True

    except Exception as exc:
        print(f"\n    ✗  Price chart failed for {ticker}: {exc}")
        try:
            plt.close()
        except Exception:
            pass
        return False


def make_macro_chart(fred_id, output_path):
    """
    Last FRED_MONTHS of FRED data — amber line chart on dark background.

    Two special cases:
    1. Cumulative-level series (e.g. PAYEMS): variation < 2% of mean
       → plot MoM change instead so the chart isn't a flat wall.
    2. "50-midpoint" series (sentiment, PMI, diffusion indices):
       mean between 35–75 → y-axis centered on 50, with a dashed reference line.
    """
    if not FRED_API_KEY:
        print(f"\n    ⚠  FRED_API_KEY not set — skipping {fred_id}")
        return False

    try:
        fred   = Fred(api_key=FRED_API_KEY)
        series = fred.get_series(fred_id).dropna()

        if series.empty:
            print(f"\n    ⚠  No FRED data for {fred_id}")
            return False

        series = series.iloc[-(FRED_MONTHS + 12):]   # fetch extra for YoY calc

        # ── YoY % change for price index series ──────────────────────────
        if fred_id in FRED_YOY_SERIES:
            series = (series.pct_change(12) * 100).dropna()

        series = series.iloc[-FRED_MONTHS:]   # trim to display window
        label  = FRED_LABELS.get(fred_id, fred_id)
        latest = series.iloc[-1]
        prev   = series.iloc[-2] if len(series) > 1 else latest
        delta  = latest - prev
        sign   = "+" if delta >= 0 else ""

        # ── Case 1: flat-wall detection → switch to MoM change ───────────
        mean_val      = series.mean()
        rel_variation = (series.max() - series.min()) / abs(mean_val) if mean_val else 1
        plot_change   = rel_variation < 0.02

        if plot_change:
            plot_series  = series.diff().dropna()
            change_label = f"{label}  —  MoM Change"
        else:
            plot_series  = series
            change_label = label

        # ── Case 2: 50-midpoint series ────────────────────────────────────
        # Applies to sentiment / PMI / diffusion indices clustered near 50
        plot_mean     = plot_series.mean()
        is_50_midpoint = 35 <= plot_mean <= 75 and not plot_change

        lo, hi = plot_series.min(), plot_series.max()
        if is_50_midpoint:
            # Center y-axis on 50, symmetric padding
            half_range = max(abs(hi - 50), abs(lo - 50)) * 1.25
            half_range = max(half_range, 5)   # minimum ±5 around 50
            ymin, ymax = 50 - half_range, 50 + half_range
        else:
            pad  = (hi - lo) * 0.15 if hi != lo else abs(hi) * 0.10
            ymin, ymax = lo - pad, hi + pad

        color = "#ffa726"   # amber

        fig, ax = plt.subplots(figsize=(12, 9))
        fig.patch.set_facecolor("#0d1117")
        ax.set_facecolor("#161b22")

        # Line + subtle fill
        ax.plot(plot_series.index, plot_series.values,
                color=color, linewidth=3, zorder=3)
        ax.fill_between(plot_series.index, plot_series.values,
                        50 if is_50_midpoint else plot_series.min(),
                        alpha=0.08, color=color)

        # 50-reference line
        if is_50_midpoint:
            ax.axhline(50, color="#ffffff", linewidth=1.2,
                       linestyle="--", alpha=0.35, zorder=2)
            ax.text(plot_series.index[0], 50.4, "50",
                    color="#aaaaaa", fontsize=13, va="bottom")

        ax.set_ylim(ymin, ymax)

        # Annotate latest value
        fmt = f"{plot_series.iloc[-1]:+,.0f}" if plot_change else f"{latest:.2f}"
        ax.annotate(
            fmt,
            xy=(plot_series.index[-1], plot_series.iloc[-1]),
            xytext=(8, 0), textcoords="offset points",
            color=color, fontsize=15, fontweight="bold", va="center"
        )
        # Dot on latest point
        ax.scatter([plot_series.index[-1]], [plot_series.iloc[-1]],
                   color="#ffcc02", s=80, zorder=5)

        ax.set_title(
            f"{change_label}\n최근: {latest:.2f}   ({sign}{delta:.2f} 전기 대비)",
            color="white", fontsize=16, pad=14, fontweight="bold", linespacing=1.6
        )
        ax.tick_params(colors="#bbbbbb", labelsize=13)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%y/%m"))
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
        plt.xticks(rotation=0, ha="center")
        for spine in ax.spines.values():
            spine.set_edgecolor("#30363d")
        ax.grid(axis="y", color="#30363d", linestyle="--", linewidth=0.6, zorder=0)
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(
            lambda x, _: f"{x:+,.0f}" if plot_change else (
                f"{x:,.0f}" if abs(x) >= 100 else f"{x:.2f}"
            )
        ))

        fig.subplots_adjust(left=0.12, right=0.92, top=0.88, bottom=0.10)
        plt.savefig(output_path, dpi=100, bbox_inches="tight",
                    facecolor=fig.get_facecolor())
        plt.close()
        return True

    except Exception as exc:
        print(f"\n    ✗  FRED chart failed for {fred_id}: {exc}")
        try:
            plt.close()
        except Exception:
            pass
        return False


# FRED fallback for yfinance tickers — loaded from config/ticker_config.json
YFINANCE_TO_FRED = _ticker_cfg.get("yfinance_to_fred", {})


def make_chart(identifier, output_path):
    """Route to the right chart function based on identifier prefix.
    Falls back to FRED for yfinance tickers that failed to fetch."""
    if identifier.startswith("FRED:"):
        return make_macro_chart(identifier[5:], output_path)

    # Try price chart first
    ok = make_price_chart(identifier, output_path)
    if ok:
        return True

    # Fallback: try FRED equivalent if available
    fred_id = YFINANCE_TO_FRED.get(identifier)
    if fred_id and FRED_API_KEY:
        print(f"    ↪ Falling back to FRED:{fred_id}", flush=True)
        return make_macro_chart(fred_id, output_path)

    return False


def generate_charts(section_data):
    """
    For every section, generate charts for its tickers.
    Mutates section_data in-place, adding a "charts" key to each entry.
    Returns section_data.
    """
    global _price_cache
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Fixed sections use pre-generated images (background/movers/sectors/countries)
    # — skip chart generation for them to avoid wasting yfinance API calls
    SKIP_SECTIONS = {"시장개요", "주요등락", "섹터분석", "국가별"}

    # Collect yfinance tickers only from 뉴스 sections
    yf_tickers = []
    for section, entry in section_data.items():
        if section in SKIP_SECTIONS:
            continue
        for ident in entry.get("tickers", []):
            if not ident.startswith("FRED:") and ident not in yf_tickers:
                yf_tickers.append(ident)

    if yf_tickers:
        _price_cache = prefetch_price_data(yf_tickers)

    for section, entry in section_data.items():
        tickers = entry.get("tickers", [])
        if not tickers or section in SKIP_SECTIONS:
            entry["charts"] = []
            continue

        print(f"\n📊  {section}")
        paths = []
        for ident in tickers:
            out = _safe_filename(section, ident)
            chart_type = "FRED" if ident.startswith("FRED:") else "price"
            print(f"    → {ident} [{chart_type}] ... ", end="", flush=True)
            ok = make_chart(ident, out)
            if ok:
                print(f"saved → {out}")
                paths.append(out)
        entry["charts"] = paths

    return section_data


# ── 4. Main ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Extract tickers/FRED series + bullets from a Korean finance script and generate charts."
    )
    parser.add_argument("--script",    required=False,
                        default="temp/korean_script.txt",
                        help="Path to Korean script (default: temp/korean_script.txt)")
    parser.add_argument("--skip-groq", action="store_true",
                        help=f"Skip Groq call and load {TICKER_MAP_FILE} instead")

    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--extract-only", action="store_true",
                      help="Only extract tickers/bullets (no chart generation)")
    mode.add_argument("--charts-only", action="store_true",
                      help="Only generate charts from existing ticker_map.json")

    args = parser.parse_args()

    # ── Charts-only mode: load ticker_map and generate charts ────────────
    if args.charts_only:
        if not os.path.exists(TICKER_MAP_FILE):
            sys.exit(f"ticker_map.json not found: {TICKER_MAP_FILE}")
        print(f"Loading section data from {TICKER_MAP_FILE}")
        with open(TICKER_MAP_FILE, encoding="utf-8") as f:
            section_data = json.load(f)
        section_data = generate_charts(section_data)
        with open(TICKER_MAP_FILE, "w", encoding="utf-8") as f:
            json.dump(section_data, f, ensure_ascii=False, indent=2)
        total = sum(len(e.get("charts", [])) for e in section_data.values())
        print(f"\n── Done (charts-only) ───────────────────")
        print(f"Total charts generated: {total}")
        for s, entry in section_data.items():
            for p in entry.get("charts", []):
                print(f"  {s} → {p}")
        return

    # ── Parse script ─────────────────────────────────────────────────────
    if not os.path.exists(args.script):
        sys.exit(f"Script file not found: {args.script}")
    with open(args.script, encoding="utf-8") as f:
        script_text = f.read()

    sections = parse_sections(script_text)
    print(f"Parsed {len(sections)} sections:")
    for name in sections:
        preview = sections[name][:60].replace('\n', ' ')
        print(f"  [{name}]  {preview}…")

    # ── Load or extract section data ──────────────────────────────────────
    if args.skip_groq and os.path.exists(TICKER_MAP_FILE):
        print(f"\nLoading section data from {TICKER_MAP_FILE}")
        with open(TICKER_MAP_FILE, encoding="utf-8") as f:
            section_data = json.load(f)
    else:
        section_data = extract_section_data(sections)
        os.makedirs("temp", exist_ok=True)
        with open(TICKER_MAP_FILE, "w", encoding="utf-8") as f:
            json.dump(section_data, f, ensure_ascii=False, indent=2)
        print(f"Section data saved → {TICKER_MAP_FILE}")

    print("\nSection data:")
    for section, entry in section_data.items():
        print(f"  {section}:")
        print(f"    tickers: {entry.get('tickers', [])}")
        if entry.get("bullets"):
            print(f"    bullets: {entry.get('bullets', [])}")

    # ── Extract-only mode: stop here ─────────────────────────────────────
    if args.extract_only:
        print(f"\n── Done (extract-only) ──────────────────")
        return

    # ── Generate charts ───────────────────────────────────────────────────
    section_data = generate_charts(section_data)

    # ── Save final section_data with chart paths ─────────────────────────
    os.makedirs("temp", exist_ok=True)
    with open(TICKER_MAP_FILE, "w", encoding="utf-8") as f:
        json.dump(section_data, f, ensure_ascii=False, indent=2)

    # ── Summary ───────────────────────────────────────────────────────────
    total = sum(len(e.get("charts", [])) for e in section_data.values())
    print(f"\n── Done ─────────────────────────────────")
    print(f"Total charts generated: {total}")

    for s, entry in section_data.items():
        for p in entry.get("charts", []):
            print(f"  {s} → {p}")
    no_charts = [s for s, e in section_data.items() if not e.get("charts")]
    if no_charts:
        print("Sections using fallback image:")
        for s in no_charts:
            print(f"  {s}")


if __name__ == "__main__":
    main()
