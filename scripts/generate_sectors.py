"""
Generates assets/sectors.jpg — S&P 500 GICS sector performance map.
Uses SPDR sector ETFs as proxies. Box size = approx sector weight in S&P 500.
Color = daily return (Korean convention: red=up, blue=down).
"""

import os, json, requests
from datetime import datetime
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw, ImageFont

OUTPUT  = "assets/sectors.jpg"
FONTS   = "/usr/share/fonts/opentype/noto"
KO_BOLD = f"{FONTS}/NotoSansCJK-Bold.ttc"
KO_REG  = f"{FONTS}/NotoSansCJK-Regular.ttc"
W, H    = 1920, 1080

DARK     = (8,  12,  22)
WHITE    = (255, 255, 255)
WHITE_DIM= (200, 210, 225)
GREEN_DIM= (0,   80,  45)
GRAY     = (55,  65,  85)

# Korean convention: red = up, blue = down
# Intensity scales with magnitude
def chg_color(chg):
    if abs(chg) < 0.05:
        return (30, 38, 60)      # neutral
    intensity = min(abs(chg) / 4.0, 1.0)  # cap at 4%
    if chg > 0:
        r = int(80  + 130 * intensity)
        g = int(15  +  10 * (1 - intensity))
        b = int(15  +  10 * (1 - intensity))
        return (r, g, b)
    else:
        r = int(15  +  10 * (1 - intensity))
        g = int(20  +  20 * (1 - intensity))
        b = int(80  + 130 * intensity)
        return (r, g, b)


# Sector ETFs with approx S&P 500 weights (%) and Korean labels
SECTORS = [
    ("XLK",  "IT",         "Information\nTechnology",  32.0),
    ("XLF",  "금융",        "Financials",               13.0),
    ("XLV",  "헬스케어",    "Health Care",              11.5),
    ("XLY",  "임의소비재",  "Consumer\nDiscretionary",  10.5),
    ("XLC",  "통신",        "Communication\nServices",   8.5),
    ("XLI",  "산업재",      "Industrials",               8.0),
    ("XLP",  "필수소비재",  "Consumer\nStaples",         6.0),
    ("XLE",  "에너지",      "Energy",                    3.5),
    ("XLB",  "소재",        "Materials",                 2.5),
    ("XLRE", "부동산",      "Real Estate",               2.5),
    ("XLU",  "유틸리티",    "Utilities",                 2.0),
]


def fetch_sector_returns():
    import yfinance as yf
    tickers = [s[0] for s in SECTORS]
    data = yf.download(tickers, period="5d", auto_adjust=True,
                       progress=False, group_by="ticker")
    results = {}
    for etf, ko, en, weight in SECTORS:
        try:
            closes = data[etf]["Close"].dropna()
            if len(closes) >= 2:
                chg = (closes.iloc[-1] - closes.iloc[-2]) / closes.iloc[-2] * 100
                results[etf] = {"ko": ko, "en": en, "weight": weight, "chg": chg}
                print(f"  ✅ {etf} {ko}: {chg:+.2f}%", flush=True)
        except Exception as e:
            print(f"  ⚠️  {etf}: {e}", flush=True)
            results[etf] = {"ko": ko, "en": en, "weight": weight, "chg": 0.0}
    return results


def generate_sector_image(sectors):
    img  = Image.new("RGB", (W, H), DARK)
    draw = ImageDraw.Draw(img)

    # Background
    for y in range(H):
        t = y / H
        draw.line([(0, y), (W, y)],
                  fill=(int(8+6*t), int(12+8*t), int(22+16*t)))

    # Left accent
    draw.rectangle([(0, 0), (6, H)], fill=(0, 200, 110))

    # Fonts
    fh   = ImageFont.truetype(KO_BOLD, 48)
    fm   = ImageFont.truetype(KO_BOLD, 32)
    fr   = ImageFont.truetype(KO_REG,  24)
    fs   = ImageFont.truetype(KO_REG,  20)
    fmono= ImageFont.truetype(KO_REG,  18)

    NY  = ZoneInfo("America/New_York")
    now = datetime.now(NY)

    # Header
    draw.text((80, 28),
              "S&P 500  섹터별 수익률",
              font=fh, fill=WHITE)
    draw.text((780, 40),
              f"GICS 섹터  ·  {now.strftime('%m/%d  %H:%M')} NY시간",
              font=fs, fill=(70, 85, 120))
    draw.line([(80, 90), (W-80, 90)], fill=(0, 200, 110), width=2)

    # ── Treemap layout ────────────────────────────────────────────────
    # Fixed layout: row-based proportional to weight
    # Sort by weight descending
    sorted_s = sorted(sectors.items(), key=lambda x: -x[1]["weight"])
    total_w  = sum(s["weight"] for s in sectors.values())

    PAD    = 6
    MAP_X  = 80
    MAP_Y  = 105
    MAP_W  = W - 160
    MAP_H  = H - 155

    # Squarify-style row layout
    def layout_row(items, x, y, w, h):
        """Layout items in a horizontal row."""
        total = sum(i["weight"] for i in items)
        cx = x
        rects = []
        for i, item in enumerate(items):
            iw = int(w * item["weight"] / total)
            if i == len(items) - 1:
                iw = w - (cx - x)  # fill remainder
            rects.append((cx, y, iw, h, item))
            cx += iw
        return rects

    # Split into rows: row1 = top 3 (heavy), row2 = next 4, row3 = last 4
    rows_def = [
        (sorted_s[:3],  0.42),   # IT, Financials, Healthcare
        (sorted_s[3:7], 0.33),   # Discret, Comm, Industrials, Staples
        (sorted_s[7:],  0.25),   # Energy, Materials, RE, Utilities
    ]

    all_rects = []
    cy = MAP_Y
    for row_items, row_frac in rows_def:
        rh = int(MAP_H * row_frac)
        items = [{"weight": sectors[etf]["weight"], "etf": etf, **sectors[etf]}
                 for etf, _ in row_items]
        rects = layout_row(items, MAP_X, cy, MAP_W, rh - PAD)
        all_rects.extend(rects)
        cy += rh

    # Draw rectangles
    for (rx, ry, rw, rh, item) in all_rects:
        # Background color based on return
        color = chg_color(item["chg"])
        draw.rectangle([(rx+PAD, ry+PAD), (rx+rw-PAD, ry+rh-PAD)],
                       fill=color)

        # Border
        draw.rectangle([(rx+PAD, ry+PAD), (rx+rw-PAD, ry+rh-PAD)],
                       outline=(255,255,255,30), width=1)

        cx = rx + rw // 2
        cy2 = ry + rh // 2

        # Choose font size based on box size
        box_area = rw * rh
        if box_area > 200000:
            fko, fen, fchg = fh, fr, fm
        elif box_area > 80000:
            fko, fen, fchg = fm, fmono, fr
        else:
            fko, fen, fchg = fr, fmono, fmono

        # Korean sector name
        ko_text = item["ko"]
        bbox = draw.textbbox((0,0), ko_text, font=fko)
        tw = bbox[2] - bbox[0]
        draw.text((cx - tw//2, cy2 - 45), ko_text, font=fko, fill=WHITE)

        # % change
        arrow  = "▲" if item["chg"] >= 0 else "▼"
        chg_col= (255, 180, 180) if item["chg"] >= 0 else (180, 200, 255)
        if abs(item["chg"]) >= 0.05:
            chg_text = f"{arrow} {abs(item['chg']):.2f}%"
        else:
            chg_text = f"{item['chg']:.2f}%"
        bbox2 = draw.textbbox((0,0), chg_text, font=fchg)
        tw2 = bbox2[2] - bbox2[0]
        draw.text((cx - tw2//2, cy2 + 5), chg_text, font=fchg, fill=chg_col)

    # Legend
    lx = W - 400
    ly = H - 45
    draw.text((lx, ly), "■ 상승", font=fmono, fill=(200, 80, 80))
    draw.text((lx+80, ly), "■ 보합", font=fmono, fill=(60, 70, 100))
    draw.text((lx+160, ly), "■ 하락", font=fmono, fill=(80, 100, 200))
    draw.text((lx+240, ly), "  (한국식: 적=상승, 청=하락)", font=fmono, fill=GRAY)

    # Bottom
    draw.text((80, H-40),
              "SPDR 섹터 ETF 기준  ·  S&P 500 섹터 비중 반영",
              font=fmono, fill=(45, 55, 75))

    os.makedirs("assets", exist_ok=True)
    img.save(OUTPUT, "JPEG", quality=95)
    print(f"✅ Sector map saved → {OUTPUT}", flush=True)

    # Append sectors to market_data.json
    try:
        with open("assets/market_data.json") as f:
            data = json.load(f)
    except Exception:
        data = {}
    data["sectors"] = {etf: {"ko": info["ko"], "chg_pct": round(info["chg"],2)}
                       for etf, info in sectors.items()}
    with open("assets/market_data.json", "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("✅ Sectors saved → assets/market_data.json", flush=True)


if __name__ == "__main__":
    print("[Sectors] Fetching sector ETF returns...", flush=True)
    sectors = fetch_sector_returns()
    print("[Sectors] Generating sector map...", flush=True)
    generate_sector_image(sectors)
