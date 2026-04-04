"""
Generates assets/movers.jpg — S&P 500 top 10 gainers and losers for the day.
Used as a second daily image (separate from background.jpg).
"""

import os, json, datetime

def is_weekly_mode():
    is_sunday = datetime.datetime.utcnow().weekday() == 6
    if is_sunday:
        print("📅 Sunday UTC — using weekly (Fri-to-Fri) returns", flush=True)
    return is_sunday, requests
from datetime import datetime
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw, ImageFont

OUTPUT  = "assets/movers.jpg"
FONTS   = "/usr/share/fonts/opentype/noto"
KO_BOLD = f"{FONTS}/NotoSansCJK-Bold.ttc"
KO_REG  = f"{FONTS}/NotoSansCJK-Regular.ttc"
W, H    = 1920, 1080

DARK     = (8,  12,  22)
DARK2    = (14, 20,  38)
PANEL    = (16, 24,  46)
GREEN    = (0,  200, 110)
GREEN_DIM= (0,   80,  45)
WHITE    = (255, 255, 255)
WHITE_DIM= (190, 200, 220)
GRAY     = ( 55,  65,  85)
KO_RED   = (210,  40,  40)
KO_BLUE  = ( 70, 130, 210)


# ── 1. Fetch S&P 500 top movers ───────────────────────────────────────────

def fetch_movers():
    import yfinance as yf

    # Get S&P 500 tickers from GitHub
    url = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"
    r = requests.get(url, timeout=10)
    lines = r.text.strip().splitlines()[1:]
    tickers = [l.split(",")[0].replace(".", "-") for l in lines]
    names   = {l.split(",")[0].replace(".", "-"): l.split(",")[1] for l in lines}
    print(f"  Loaded {len(tickers)} S&P 500 tickers", flush=True)

    # Batch download
    print(f"  Downloading price data...", flush=True)
    data = yf.download(tickers, ("10d" if is_weekly_mode() else "2d"), auto_adjust=True,
                       progress=False, group_by="ticker")

    changes = {}
    for sym in tickers:
        try:
            closes = data[sym]["Close"].dropna()
            if len(closes) >= 2:
                prev = closes.iloc[-2]
                curr = closes.iloc[-1]
                chg  = (curr - prev) / prev * 100
                changes[sym] = (curr, chg, names.get(sym, sym))
        except Exception:
            pass

    print(f"  Got data for {len(changes)} tickers", flush=True)
    sorted_chg = sorted(changes.items(), key=lambda x: x[1][1])
    losers  = [(s, p, c, n) for s, (p, c, n) in sorted_chg[:10]]
    gainers = [(s, p, c, n) for s, (p, c, n) in sorted_chg[-10:][::-1]]
    return gainers, losers


# ── 2. Generate image ─────────────────────────────────────────────────────

def generate_movers_image(gainers, losers):
    img  = Image.new("RGB", (W, H), DARK)
    draw = ImageDraw.Draw(img)

    # Gradient
    for y in range(H):
        t = y / H
        r = int(DARK[0] + (DARK2[0]-DARK[0]) * t)
        g = int(DARK[1] + (DARK2[1]-DARK[1]) * t)
        b = int(DARK[2] + (DARK2[2]-DARK[2]) * t)
        draw.line([(0, y), (W, y)], fill=(r, g, b))

    # Center divider
    draw.line([(W//2, 60), (W//2, H-60)], fill=(28, 38, 65), width=1)

    # Left accent bar
    draw.rectangle([(0, 0), (6, H)], fill=GREEN)

    # Fonts
    fh  = ImageFont.truetype(KO_BOLD, 52)
    fm  = ImageFont.truetype(KO_BOLD, 36)
    fr  = ImageFont.truetype(KO_REG,  26)
    fs  = ImageFont.truetype(KO_REG,  22)
    fmono = ImageFont.truetype(KO_REG, 20)

    NY  = ZoneInfo("America/New_York")
    now = datetime.now(NY)

    # Header
    draw.text((80, 40),
              f"S&P 500  주요 등락 종목  ·  {now.strftime('%m/%d  %H:%M')} NY시간",
              font=fs, fill=(70, 85, 120))
    draw.line([(80, 88), (W-80, 88)], fill=GREEN, width=2)

    # Column headers
    col_sym  = 80
    col_name = 220
    col_pct  = 560
    col_price= 680

    for side, items, color, label, x_offset in [
        ("gainers", gainers, KO_RED,  "▲ 상승 TOP 10", 0),
        ("losers",  losers,  KO_BLUE, "▼ 하락 TOP 10", W//2 + 40),
    ]:
        # Section title
        lx = x_offset + 80 if side == "losers" else 80
        draw.text((lx, 105), label, font=fm, fill=color)
        draw.line([(lx, 150), (lx + 820, 150)], fill=(28, 38, 65), width=1)

        # Column labels
        draw.text((lx,           158), "티커",  font=fmono, fill=GRAY)
        draw.text((lx + 130,     158), "종목명",  font=fmono, fill=GRAY)
        draw.text((lx + 480,     158), "등락률", font=fmono, fill=GRAY)
        draw.text((lx + 590,     158), "종가",   font=fmono, fill=GRAY)
        draw.line([(lx, 182), (lx + 820, 182)], fill=(22, 32, 55), width=1)

        # Rows
        for i, (sym, price, chg, name) in enumerate(items):
            ry = 192 + i * 82
            bg_col = (14, 20, 38) if i % 2 == 0 else (18, 26, 46)
            draw.rectangle([(lx-10, ry), (lx+830, ry+78)], fill=bg_col)

            # Rank
            draw.text((lx, ry+8),       f"{i+1:2d}",          font=fmono, fill=GRAY)
            # Ticker
            draw.text((lx+35,  ry+4),   sym,                  font=fm,    fill=color)
            # Name (truncated)
            short_name = name[:22] if len(name) > 22 else name
            draw.text((lx+35,  ry+42),  short_name,           font=fmono, fill=WHITE_DIM)
            # Change %
            arrow = "▲" if chg >= 0 else "▼"
            draw.text((lx+490, ry+16),  f"{arrow}{abs(chg):.2f}%", font=fr, fill=color)
            # Price
            draw.text((lx+600, ry+16),  f"${price:.2f}",      font=fr,    fill=WHITE)

    # Bottom
    draw.rectangle([(0, H-60), (W, H)], fill=(10, 16, 30))
    draw.text((80, H-40),
              "S&P 500 구성 종목 기준  ·  매일 업데이트",
              font=fmono, fill=(45, 55, 75))
    draw.text((W-290, H-40), "ECONOMY BRIEFING", font=fmono, fill=GREEN_DIM)

    os.makedirs("assets", exist_ok=True)
    img.save(OUTPUT, "JPEG", quality=95)
    print(f"✅ Movers image saved → {OUTPUT}", flush=True)

    # Append movers to market_data.json
    try:
        with open("assets/market_data.json") as f:
            data = json.load(f)
    except Exception:
        data = {}
    data["gainers"] = [{"symbol": s, "price": round(p,2), "chg_pct": round(c,2), "name": n}
                       for s, p, c, n in gainers]
    data["losers"]  = [{"symbol": s, "price": round(p,2), "chg_pct": round(c,2), "name": n}
                       for s, p, c, n in losers]
    with open("assets/market_data.json", "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("✅ Movers appended → assets/market_data.json", flush=True)


# ── Main ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("[Movers] Fetching S&P 500 top movers...", flush=True)
    gainers, losers = fetch_movers()
    print("[Movers] Generating image...", flush=True)
    generate_movers_image(gainers, losers)
    # Save to market_data.json
    try:
        with open("assets/market_data.json") as f:
            data = json.load(f)
    except Exception:
        data = {}
    data["gainers"] = [{"symbol": s, "price": round(p,2), "chg_pct": round(c,2), "name": n} for s,p,c,n in gainers]
    data["losers"]  = [{"symbol": s, "price": round(p,2), "chg_pct": round(c,2), "name": n} for s,p,c,n in losers]
    with open("assets/market_data.json", "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("✅ Movers saved → assets/market_data.json", flush=True)
