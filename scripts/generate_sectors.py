"""
Generates assets/sectors.jpg — S&P 500 GICS sector performance map.
Uses SPDR sector ETFs. Box size = live ETF market cap (millions, sqrt-scaled).
Color = daily return (Korean convention: red=up, blue=down).
"""

import os, json, math, requests
import datetime as dt
from datetime import datetime
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw, ImageFont

def is_weekly_mode():
    is_sunday = dt.datetime.utcnow().weekday() == 6
    if is_sunday:
        print("📅 Sunday UTC — using weekly (Fri-to-Fri) returns", flush=True)
    return is_sunday


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

SECTORS = [
    ("XLK",  "IT",         "Information Technology"),
    ("XLF",  "금융",        "Financials"),
    ("XLV",  "헬스케어",    "Health Care"),
    ("XLY",  "임의소비재",  "Consumer Discretionary"),
    ("XLC",  "통신",        "Communication Services"),
    ("XLI",  "산업재",      "Industrials"),
    ("XLP",  "필수소비재",  "Consumer Staples"),
    ("XLE",  "에너지",      "Energy"),
    ("XLB",  "소재",        "Materials"),
    ("XLRE", "부동산",      "Real Estate"),
    ("XLU",  "유틸리티",    "Utilities"),
]


def _make_chg_color(all_changes):
    """Build a gradient color function normalized to the actual data range.
    Positive: dark neutral → red.  Negative: dark neutral → blue."""
    max_pos = max((c for c in all_changes if c > 0), default=1.0)
    max_neg = min((c for c in all_changes if c < 0), default=-1.0)

    MID  = (22, 30, 52)
    RED  = (210, 40, 40)
    BLUE = (40, 70, 210)

    def chg_color(chg):
        if chg >= 0:
            t = min(chg / max_pos, 1.0) if max_pos > 0 else 0.0
        else:
            t = min(abs(chg) / abs(max_neg), 1.0) if max_neg < 0 else 0.0
        target = RED if chg >= 0 else BLUE
        return (
            int(MID[0] + (target[0] - MID[0]) * t),
            int(MID[1] + (target[1] - MID[1]) * t),
            int(MID[2] + (target[2] - MID[2]) * t),
        )
    return chg_color


def fetch_sector_data():
    import yfinance as yf
    tickers = [s[0] for s in SECTORS]
    period = "10d" if is_weekly_mode() else "5d"
    data = yf.download(tickers, period=period, auto_adjust=True,
                       progress=False, group_by="ticker")
    results = {}
    weekly = is_weekly_mode()
    for etf, ko, en in SECTORS:
        try:
            closes = data[etf]["Close"].dropna()
            if len(closes) < 2:
                print(f"  ⚠️  {etf}: only {len(closes)} rows", flush=True)
                continue
            if weekly:
                iso = closes.index.isocalendar()
                weekly_last = closes.groupby([iso.year, iso.week]).last()
                if len(weekly_last) >= 2:
                    prev, curr = weekly_last.iloc[-2], weekly_last.iloc[-1]
                else:
                    prev, curr = closes.iloc[0], closes.iloc[-1]
            else:
                prev, curr = closes.iloc[-2], closes.iloc[-1]
            chg  = (curr - prev) / prev * 100
            price = closes.iloc[-1]

            # Live market cap for box sizing
            t    = yf.Ticker(etf)
            mcap = getattr(t.fast_info, "market_cap", None) or (price * 1e6)

            results[etf] = {"ko": ko, "en": en, "chg": chg,
                            "price": price, "mcap": mcap}
            print(f"  ✅ {etf} {ko}: {chg:+.2f}%  mcap=${mcap/1e6:,.0f}M", flush=True)
        except Exception as e:
            print(f"  ⚠️  {etf}: {e}", flush=True)
    if not results:
        raise RuntimeError("No market data available — market may be closed (weekend/holiday)")
    return results


def squarify(items, x, y, w, h):
    if not items:
        return []
    total = sum(v for _, v in items)
    if total == 0:
        return []
    rects = []
    remaining = list(items)
    rx, ry, rw, rh = x, y, w, h
    while remaining:
        use_width = rw >= rh
        row, row_weight, best_ar = [], 0, float("inf")
        for item in remaining:
            row.append(item)
            row_weight += item[1]
            frac = row_weight / total
            if use_width:
                row_h = rh * frac if frac > 0 else rh
                cell_w = (rw * item[1] / row_weight) if row_weight > 0 else rw
                ar = max(row_h/cell_w, cell_w/row_h) if cell_w > 0 else float("inf")
            else:
                row_w = rw * frac if frac > 0 else rw
                cell_h = (rh * item[1] / row_weight) if row_weight > 0 else rh
                ar = max(row_w/cell_h, cell_h/row_w) if cell_h > 0 else float("inf")
            if ar > best_ar and len(row) > 1:
                row.pop(); row_weight -= item[1]; break
            best_ar = ar
        remaining = remaining[len(row):]
        total = sum(v for _, v in remaining)
        row_frac = row_weight / (row_weight + total) if (row_weight + total) > 0 else 1.0
        if use_width:
            strip_h = int(rh * row_frac)
            cx = rx
            for key, wt in row:
                cw = int(rw * wt / row_weight)
                rects.append((key, cx, ry, cw, strip_h))
                cx += cw
            ry += strip_h; rh -= strip_h
        else:
            strip_w = int(rw * row_frac)
            cy = ry
            for key, wt in row:
                ch2 = int(rh * wt / row_weight)
                rects.append((key, rx, cy, strip_w, ch2))
                cy += ch2
            rx += strip_w; rw -= strip_w
    return rects


def generate_sector_image(sectors):
    # Build gradient color function from actual data range
    all_changes = [v["chg"] for v in sectors.values()]
    chg_color = _make_chg_color(all_changes)

    img  = Image.new("RGB", (W, H), DARK)
    draw = ImageDraw.Draw(img)

    for y in range(H):
        t = y/H
        draw.line([(0,y),(W,y)], fill=(int(8+6*t),int(12+8*t),int(22+16*t)))

    draw.rectangle([(0,0),(6,H)], fill=(0,200,110))

    fh    = ImageFont.truetype(KO_BOLD, 48)
    fm    = ImageFont.truetype(KO_BOLD, 36)
    fr    = ImageFont.truetype(KO_REG,  26)
    fs    = ImageFont.truetype(KO_REG,  20)
    fmono = ImageFont.truetype(KO_REG,  18)

    NY  = ZoneInfo("America/New_York")
    now = datetime.now(NY)

    weekly_tag = "  ·  주간 수익률" if is_weekly_mode() else ""
    draw.text((80, 28), "S&P 500  섹터별 수익률", font=fh, fill=WHITE)
    draw.text((780, 40),
              f"SPDR ETF 시가총액 기준  ·  {now.strftime('%m/%d  %H:%M')} NY시간{weekly_tag}",
              font=fs, fill=(70,85,120))
    draw.line([(80,90),(W-80,90)], fill=(0,200,110), width=2)

    # Sort by mcap, use sqrt for box sizing
    items = [(etf, math.sqrt(v["mcap"])) for etf, v in sectors.items()]
    items.sort(key=lambda x: -x[1])

    PAD = 6
    rects = squarify(items, 80, 105, W-160, H-155)

    for (etf, rx, ry, rw, rh) in rects:
        if etf not in sectors:
            continue
        v     = sectors[etf]
        color = chg_color(v["chg"])
        draw.rectangle([(rx+PAD,ry+PAD),(rx+rw-PAD,ry+rh-PAD)], fill=color)
        draw.rectangle([(rx+PAD,ry+PAD),(rx+rw-PAD,ry+rh-PAD)], outline=(0,0,0), width=1)

        cx  = rx + rw//2
        cy2 = ry + rh//2
        area = rw * rh
        box_w = rw - PAD*2
        box_h = rh - PAD*2

        if area > 200000:
            fko, fch = fm, fr
        elif area > 80000:
            fko, fch = fr, fmono
        else:
            fko, fch = fmono, fmono

        arrow   = "▲" if v["chg"] >= 0 else "▼"
        # Gradient text color
        tc = min(abs(v["chg"]) / 3.0, 1.0)
        if v["chg"] >= 0:
            chg_col = (255, int(220 - 60*tc), int(220 - 60*tc))
        else:
            chg_col = (int(220 - 70*tc), int(220 - 30*tc), 255)
        chg_str = f"{arrow}{abs(v['chg']):.2f}%"
        ko_text = v["ko"]

        name_h = fko.size + 4
        chg_h  = fch.size + 4

        if name_h + chg_h < box_h - 20:
            start_y = cy2 - (name_h + chg_h)//2
            bk = draw.textbbox((0,0), ko_text, font=fko)
            tw = bk[2]-bk[0]
            if tw < box_w - 4:
                draw.text((cx-tw//2, start_y), ko_text, font=fko, fill=WHITE)
            bch = draw.textbbox((0,0), chg_str, font=fch)
            tcw = bch[2]-bch[0]
            if tcw < box_w - 4:
                draw.text((cx-tcw//2, start_y+name_h), chg_str, font=fch, fill=chg_col)
        elif chg_h < box_h - 8:
            bch = draw.textbbox((0,0), chg_str, font=fch)
            tcw = bch[2]-bch[0]
            if tcw < box_w - 4:
                draw.text((cx-tcw//2, cy2-fch.size//2), chg_str, font=fch, fill=chg_col)

    # Legend
    # Gradient legend bar
    lx, ly = W-440, H-45
    bar_w, bar_h = 180, 14
    bar_y = ly + 2
    for i in range(bar_w):
        t = i / (bar_w - 1)  # 0 → 1 (blue → red)
        if t < 0.5:
            s = 1 - t * 2
            c = (int(22 + (40-22)*s), int(30 + (70-30)*s), int(52 + (210-52)*s))
        else:
            s = (t - 0.5) * 2
            c = (int(22 + (210-22)*s), int(30 + (40-30)*s), int(52 + (40-52)*s))
        draw.line([(lx+i, bar_y), (lx+i, bar_y+bar_h)], fill=c)
    draw.text((lx,         ly+18), "하락", font=fmono, fill=(60,100,210))
    draw.text((lx+bar_w-30, ly+18), "상승", font=fmono, fill=(200,60,60))
    draw.text((lx+bar_w+15, ly), "  (한국식: 적=상승, 청=하락)", font=fmono, fill=GRAY)

    bottom_label = "SPDR 섹터 ETF 기준  ·  USD 주간 수익률  ·  박스크기 = ETF 시가총액" if is_weekly_mode() else "SPDR 섹터 ETF 기준  ·  USD 수익률  ·  박스크기 = ETF 시가총액"
    draw.text((80,H-40), bottom_label, font=fmono, fill=(45,55,75))

    os.makedirs("assets", exist_ok=True)
    img.save(OUTPUT, "JPEG", quality=95)
    print(f"✅ Sector map saved → {OUTPUT}", flush=True)

    # Append to market_data.json
    try:
        with open("assets/market_data.json") as f:
            data = json.load(f)
    except Exception:
        data = {}
    data["sectors"] = {etf: {"ko": v["ko"], "chg_pct": round(v["chg"],2)}
                       for etf, v in sectors.items()}
    with open("assets/market_data.json", "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("✅ Sectors saved → assets/market_data.json", flush=True)


if __name__ == "__main__":
    print("[Sectors] Fetching sector ETF data...", flush=True)
    sectors = fetch_sector_data()
    print("[Sectors] Generating sector map...", flush=True)
    generate_sector_image(sectors)
