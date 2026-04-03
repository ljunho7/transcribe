"""
Step 0: Fetch live market data and generate assets/background.jpg
        Uses yfinance (free, no API key) for US indices + KRW rate + commodities.
        Falls back to placeholder values if market is closed or fetch fails.
"""

import os
import math
import random
from datetime import datetime, timezone, timedelta
from PIL import Image, ImageDraw, ImageFont

# ── Config ────────────────────────────────────────────────────────────────
OUTPUT   = "assets/background.jpg"
FONTS    = "/usr/share/fonts/opentype/noto"
KO_BOLD  = f"{FONTS}/NotoSansCJK-Bold.ttc"
KO_REG   = f"{FONTS}/NotoSansCJK-Regular.ttc"
MONO     = "temp_mono.ttf"  # downloaded below if needed

W, H = 1920, 1080

# ── Palette ───────────────────────────────────────────────────────────────
DARK        = (8,  12,  22)
DARK2       = (14, 20,  38)
PANEL       = (18, 26,  50)
GREEN       = (0,  210, 120)
GREEN_DIM   = (0,  100,  55)
GREEN_FAINT = (0,   35,  20)
RED_PRICE   = (220,  70,  70)
WHITE       = (255, 255, 255)
WHITE_DIM   = (190, 200, 220)
GRAY        = ( 55,  65,  85)


# ── 1. Fetch market data ──────────────────────────────────────────────────

def fetch_market_data():
    """Fetch live market data. Returns dict of {label: (price, change_pct)}"""
    try:
        import yfinance as yf

        symbols = {
            "S&P 500":  "^GSPC",
            "NASDAQ":   "^IXIC",
            "DOW":      "^DJI",
            "USD/KRW":  "KRW=X",
            "WTI":      "CL=F",
            "금(Gold)": "GC=F",
        }

        result = {}
        for label, sym in symbols.items():
            try:
                ticker = yf.Ticker(sym)
                hist = ticker.history(period="2d")
                if len(hist) >= 2:
                    prev  = hist["Close"].iloc[-2]
                    curr  = hist["Close"].iloc[-1]
                    chg   = (curr - prev) / prev * 100
                    result[label] = (curr, chg)
                elif len(hist) == 1:
                    curr = hist["Close"].iloc[-1]
                    result[label] = (curr, 0.0)
            except Exception as e:
                print(f"  ⚠️  {label} ({sym}): {e}")

        if result:
            print(f"  ✅ Fetched {len(result)} market indicators")
            return result

    except ImportError:
        print("  ⚠️  yfinance not installed")
    except Exception as e:
        print(f"  ⚠️  Market fetch failed: {e}")

    # Fallback — return empty so placeholders are used
    return {}


def format_price(label, price):
    """Format price based on what it represents."""
    if "KRW" in label or "원" in label:
        return f"{price:,.1f}"
    elif price > 10000:
        return f"{price:,.0f}"
    elif price > 100:
        return f"{price:,.2f}"
    else:
        return f"{price:.2f}"


# ── 2. Generate background ────────────────────────────────────────────────

def generate_background(market_data):
    img  = Image.new("RGB", (W, H), DARK)
    draw = ImageDraw.Draw(img)

    # Gradient
    for y in range(H):
        t = y / H
        r = int(DARK[0] + (DARK2[0]-DARK[0]) * t)
        g = int(DARK[1] + (DARK2[1]-DARK[1]) * t)
        b = int(DARK[2] + (DARK2[2]-DARK[2]) * t)
        draw.line([(0, y), (W, y)], fill=(r, g, b))

    # Right panel
    for x in range(int(W*0.52), W):
        t = (x - W*0.52) / (W*0.48)
        r  = int(DARK[0] + (PANEL[0]-DARK[0]) * t)
        gc = int(DARK[1] + (PANEL[1]-DARK[1]) * t)
        b  = int(DARK[2] + (PANEL[2]-DARK[2]) * t)
        draw.line([(x, 0), (x, H)], fill=(r, gc, b))

    # Grid
    for y in range(0, H, 44):
        draw.line([(0, y), (W, y)], fill=(18, 26, 44))
    for x in range(0, W, 88):
        draw.line([(x, 0), (x, H)], fill=(18, 26, 44))

    # Abstract upward chart
    random.seed(42)
    val = 200
    pts = []
    cx0, cy0, cw, ch = int(W*0.56), H//2+100, int(W*0.38), 300
    for i in range(90):
        val += random.randint(-5, 12)
        x = cx0 + int(i/89 * cw)
        y = cy0 + ch//2 - int((val-200) * 0.6)
        pts.append((x, max(cy0-ch//2, min(cy0+ch//2, y))))

    overlay = Image.new("RGBA", (W, H), (0,0,0,0))
    ov = ImageDraw.Draw(overlay)
    ov.polygon([(pts[0][0], cy0+ch//2)] + pts + [(pts[-1][0], cy0+ch//2)],
               fill=(0, 210, 120, 22))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    for i in range(len(pts)-1):
        draw.line([pts[i], pts[i+1]], fill=GREEN, width=3)

    ex, ey = pts[-1]
    for r_s, a in [(20,10),(12,28),(7,75),(4,200)]:
        ov2 = Image.new("RGBA", (W,H), (0,0,0,0))
        ImageDraw.Draw(ov2).ellipse([(ex-r_s,ey-r_s),(ex+r_s,ey+r_s)],
                                     fill=(0,210,120,a))
        img = Image.alpha_composite(img.convert("RGBA"), ov2).convert("RGB")
        draw = ImageDraw.Draw(img)
    draw.ellipse([(ex-5,ey-5),(ex+5,ey+5)], fill=WHITE)

    # Decorative candlesticks
    random.seed(7)
    cx = int(W*0.56) - 130
    for _ in range(8):
        bh  = random.randint(15, 50)
        by  = cy0 - 100 + random.randint(-50, 50)
        up  = random.random() > 0.35
        col = GREEN if up else RED_PRICE
        draw.rectangle([(cx-8, by),(cx+8, by+bh)], fill=col)
        draw.line([(cx, by-10),(cx, by)], fill=col, width=2)
        draw.line([(cx, by+bh),(cx, by+bh+10)], fill=col, width=2)
        cx += 26

    # Left accent bar
    draw.rectangle([(0, 0), (6, H)], fill=GREEN)

    # Horizontal rules
    draw.line([(80, 155),(int(W*0.50), 155)], fill=GREEN, width=2)
    draw.line([(80, H-160),(int(W*0.50), H-160)], fill=GRAY, width=1)

    # ── Fonts ─────────────────────────────────────────────────────────────
    try:
        from PIL import ImageFont as IF
        fh = IF.truetype(KO_BOLD, 138)
        fl = IF.truetype(KO_BOLD,  76)
        fm = IF.truetype(KO_BOLD,  46)
        fr = IF.truetype(KO_REG,   28)
        fs = IF.truetype(KO_REG,   22)
    except Exception:
        fh = fl = fm = fr = fs = IF.load_default()

    # ── Left side text ────────────────────────────────────────────────────
    draw.ellipse([(80,118),(96,134)], fill=GREEN)
    draw.text((110, 112), "미국 증시 마감 후 브리핑", font=fr, fill=WHITE_DIM)
    draw.text((80, 175), "월스트리트",    font=fh, fill=WHITE)
    draw.text((80, 335), "오늘의 시황",   font=fl, fill=GREEN)
    draw.text((80, 430), "한국어 브리핑", font=fm, fill=WHITE_DIM)
    draw.text((80, 530), "글로벌 경제 · 금융 · 비즈니스 핵심 뉴스",
              font=fr, fill=(90, 100, 130))

    # ── Right side: LIVE market data ──────────────────────────────────────
    panel_x = int(W * 0.565)
    panel_y = 80

    KST = timezone(timedelta(hours=9))
    now_kst = datetime.now(KST)
    draw.text((panel_x, panel_y),
              f"시장 데이터  ·  {now_kst.strftime('%Y.%m.%d')}",
              font=fs, fill=(60, 75, 110))

    if market_data:
        row_y = panel_y + 40
        for label, (price, chg) in market_data.items():
            up    = chg >= 0
            color = GREEN if up else RED_PRICE
            arrow = "▲" if up else "▼"
            price_str = format_price(label, price)
            chg_str   = f"{arrow} {abs(chg):.2f}%"

            # Label
            draw.text((panel_x, row_y), label, font=fs, fill=WHITE_DIM)
            # Price
            draw.text((panel_x + 200, row_y), price_str, font=fs, fill=WHITE)
            # Change
            draw.text((panel_x + 400, row_y), chg_str, font=fs, fill=color)

            row_y += 52

            # Divider
            if row_y < cy0 - ch//2 - 10:
                draw.line([(panel_x, row_y-12),
                           (panel_x + 550, row_y-12)],
                          fill=(25, 35, 58))
    else:
        draw.text((panel_x, panel_y+50),
                  "시장 데이터 로딩 중...", font=fs, fill=GRAY)

    draw.text((cx0+10, cy0+ch//2+18),
              "미국 증시 동향 (장식)", font=fs, fill=(40, 50, 70))

    # Bottom strip
    draw.rectangle([(0, H-80),(W, H)], fill=(10, 16, 30))
    draw.text((80, H-55),
              "매일 오전 한국어로 전해드리는 글로벌 경제 뉴스",
              font=fs, fill=(50, 60, 80))
    draw.text((W-300, H-55), "ECONOMY BRIEFING", font=fs, fill=GREEN_DIM)

    os.makedirs("assets", exist_ok=True)
    img.save(OUTPUT, "JPEG", quality=95)
    print(f"✅ Background saved → {OUTPUT}", flush=True)


# ── Main ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("[Background] Fetching market data...", flush=True)
    data = fetch_market_data()
    print("[Background] Generating background...", flush=True)
    generate_background(data)
