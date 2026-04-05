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
        warnings.filterwarnings("ignore", message="Glyph .* missing from current font")
try:
    import pandas as pd
except ImportError:
    sys.exit("Missing: pip install pandas")

# ── Config ───────────────────────────────────────────────────────────────────
GROQ_API_KEY    = os.environ.get("GROQ_API_KEY", "")
FRED_API_KEY    = os.environ.get("FRED_API_KEY", "")
GROQ_MODEL      = "llama-3.3-70b-versatile"
OUTPUT_DIR      = "temp/charts"
TICKER_MAP_FILE = "temp/ticker_map.json"
PRICE_PERIOD    = "1mo"    # yfinance lookback
FRED_MONTHS     = 24       # how many months of FRED history to show

# Series that should be displayed as YoY % change instead of raw level/index.
# These are cumulative levels or price indices where YoY is more informative.
FRED_YOY_SERIES = {
    "CPIAUCSL",   # CPI All Items
    "CPILFESL",   # Core CPI (ex food & energy)
    "PCEPI",      # PCE Price Index
    "PCEPILFE",   # Core PCE (ex food & energy)
    "PPIFIS",     # PPI Final Demand
    "PPIACO",     # PPI All Commodities
    "RSXFS",      # Retail Sales (level in millions $)
    "INDPRO",     # Industrial Production (index level)
    "GDP",        # GDP (level in billions)
    "HOUST",      # Housing Starts (level in thousands)
}

# Human-readable labels for FRED series IDs shown in chart titles
FRED_LABELS = {
    "PAYEMS":     "Nonfarm Payrolls (thousands)",
    "UNRATE":     "Unemployment Rate (%)",
    "CPIAUCSL":   "CPI YoY (%)",
    "CPILFESL":   "Core CPI YoY (%)",
    "PCEPI":      "PCE Inflation YoY (%)",
    "PCEPILFE":   "Core PCE YoY (%)",
    "FEDFUNDS":   "Fed Funds Rate (%)",
    "DGS10":      "10-Year Treasury Yield (%)",
    "DGS2":       "2-Year Treasury Yield (%)",
    "RSXFS":      "Retail Sales YoY (%)",
    "UMCSENT":    "Consumer Sentiment (U of Michigan)",
    "INDPRO":     "Industrial Production YoY (%)",
    "HOUST":      "Housing Starts YoY (%)",
    "ICSA":       "Initial Jobless Claims (thousands)",
    "GDP":        "GDP YoY (%)",
    "DCOILWTICO": "WTI Crude Oil Price ($/barrel)",
    "DEXUSEU":    "USD/EUR Exchange Rate",
}

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
        chunks = [c.strip() for c in re.split(r'\n{2,}', news_block) if c.strip()]
        i = 0
        while i < len(chunks) - 1:
            title = chunks[i]
            body  = chunks[i + 1]
            if title.startswith('오늘 준비한'):
                break
            if len(title) > 30 and ('년' in title[:10] or title[0].isdigit()):
                i += 1
                continue
            sections[f'뉴스: {title}'] = body
            i += 2

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

  CRITICAL: Never invent FRED series IDs. Only use IDs from the list above.
  For crude oil always use FRED:DCOILWTICO, never FRED:CRUDE or any other variant.

Ticker rules:
  - Each section's text starts with [MAX N tickers, MAX M bullets]
    You MUST NOT exceed those limits. Use FEWER if the story doesn't
    mention that many distinct instruments.
  - Use [] if no clearly relevant identifier exists
  - Only include identifiers you are highly confident are correct

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
    return result


# ── 3. Chart generation ───────────────────────────────────────────────────────

def _safe_filename(section_label, identifier):
    # Use section type (e.g. "뉴스") + ticker only
    section_type = section_label.split(":")[0].split("：")[0].strip()
    safe_type  = re.sub(r'[^\w]', '_', section_type)
    safe_ident = re.sub(r'[^\w]', '_', identifier)
    return os.path.join(OUTPUT_DIR, f"{safe_type}__{safe_ident}.png")


def prefetch_price_data(tickers):
    """Download price history + names one ticker at a time with delays.
    Avoids Yahoo rate limits that batch yf.download() triggers.
    Returns {ticker: {"close": Series, "name": str}}."""
    if not tickers:
        return {}

    import time
    print(f"\n📦  Downloading {len(tickers)} tickers individually ...", flush=True)

    cache = {}
    for i, ticker in enumerate(tickers):
        if i > 0:
            time.sleep(1.5)  # 1.5s between each ticker

        for attempt in range(3):
            try:
                if attempt > 0:
                    wait = 10 * attempt
                    print(f"    ⏳ Retry {attempt+1}/3 for {ticker} in {wait}s ...", flush=True)
                    time.sleep(wait)

                t = yf.Ticker(ticker)
                hist = t.history(period=PRICE_PERIOD)

                if hist.empty or len(hist) < 3:
                    print(f"    ⚠  No price data for {ticker}", flush=True)
                    break

                closes = hist["Close"].squeeze()
                try:
                    name = (t.info.get("shortName") or t.info.get("longName") or "")
                except Exception:
                    name = ""

                cache[ticker] = {"close": closes, "name": name}
                print(f"    ✓  {ticker} ({name or '?'}): {len(closes)} rows", flush=True)
                break

            except Exception as exc:
                if "Too Many Requests" in str(exc) and attempt < 2:
                    continue
                print(f"    ✗  {ticker}: {exc}", flush=True)
                break

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
            # Fallback: individual fetch (shouldn't happen with prefetch)
            t    = yf.Ticker(ticker)
            data = t.history(period=PRICE_PERIOD)
            if data.empty or len(data) < 3:
                print(f"\n    ⚠  No price data for {ticker}")
                return False
            close = data["Close"].squeeze()
            try:
                info      = t.info
                full_name = info.get("shortName") or info.get("longName") or ""
            except Exception:
                full_name = ""

        if len(close) < 3:
            print(f"\n    ⚠  Not enough data for {ticker}")
            return False

        pct   = (close.iloc[-1] / close.iloc[0] - 1) * 100
        color = "#00e676" if pct >= 0 else "#ff5252"
        title_line = f"{full_name}  ({ticker})" if full_name else ticker

        fig, ax = plt.subplots(figsize=(16, 9))
        fig.patch.set_facecolor("#0d1117")
        ax.set_facecolor("#161b22")

        ax.plot(close.index, close.values, color=color, linewidth=3, zorder=3)
        # Subtle fill — just a hint of color, not a dark blob
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
            color=color, fontsize=15, fontweight="bold", va="center"
        )

        ax.set_title(f"{title_line}   {pct:+.2f}%  (1 month)",
                     color="white", fontsize=24, pad=18, fontweight="bold")
        ax.tick_params(colors="#bbbbbb", labelsize=15)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
        ax.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=0))
        plt.xticks(rotation=30, ha="right")
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(
            lambda x, _: f"{x:,.0f}" if abs(x) >= 100 else f"{x:.2f}"
        ))
        for spine in ax.spines.values():
            spine.set_edgecolor("#30363d")
        ax.grid(axis="y", color="#30363d", linestyle="--", linewidth=0.6, zorder=0)

        plt.tight_layout()
        plt.savefig(output_path, dpi=120, bbox_inches="tight",
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

        fig, ax = plt.subplots(figsize=(16, 9))
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
            f"{change_label}\nLatest: {latest:.2f}   ({sign}{delta:.2f} vs prior)",
            color="white", fontsize=18, pad=16, fontweight="bold", linespacing=1.6
        )
        ax.tick_params(colors="#bbbbbb", labelsize=15)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
        plt.xticks(rotation=30, ha="right")
        for spine in ax.spines.values():
            spine.set_edgecolor("#30363d")
        ax.grid(axis="y", color="#30363d", linestyle="--", linewidth=0.6, zorder=0)
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(
            lambda x, _: f"{x:+,.0f}" if plot_change else (
                f"{x:,.0f}" if abs(x) >= 100 else f"{x:.2f}"
            )
        ))

        plt.tight_layout()
        plt.savefig(output_path, dpi=120, bbox_inches="tight",
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


def make_chart(identifier, output_path):
    """Route to the right chart function based on identifier prefix."""
    if identifier.startswith("FRED:"):
        return make_macro_chart(identifier[5:], output_path)
    else:
        return make_price_chart(identifier, output_path)


def generate_charts(section_data):
    """
    For every section, generate charts for its tickers.
    Mutates section_data in-place, adding a "charts" key to each entry.
    Returns section_data.
    """
    global _price_cache
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Collect all yfinance tickers and batch-download in one API call
    yf_tickers = []
    for entry in section_data.values():
        for ident in entry.get("tickers", []):
            if not ident.startswith("FRED:") and ident not in yf_tickers:
                yf_tickers.append(ident)

    if yf_tickers:
        _price_cache = prefetch_price_data(yf_tickers)

    for section, entry in section_data.items():
        tickers = entry.get("tickers", [])
        if not tickers:
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
    args = parser.parse_args()

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
        with open(TICKER_MAP_FILE, "w", encoding="utf-8") as f:
            json.dump(section_data, f, ensure_ascii=False, indent=2)
        print(f"Section data saved → {TICKER_MAP_FILE}")

    print("\nSection data:")
    for section, entry in section_data.items():
        print(f"  {section}:")
        print(f"    tickers: {entry.get('tickers', [])}")
        if entry.get("bullets"):
            print(f"    bullets: {entry.get('bullets', [])}")

    # ── Generate charts ───────────────────────────────────────────────────
    section_data = generate_charts(section_data)

    # ── Save final section_data.json for assemble_video.py ───────────────
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
