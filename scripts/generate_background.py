"""
Step 0: Fetch live market data and generate assets/background.jpg
        Grouped into: 주식 (Equity), 외환 (FX), 암호화폐 (Crypto), 금리 (Rates)
        Rates shown as bp change vs previous day, not % return.
"""

import os, random
from datetime import datetime, timezone, timedelta
from PIL import Image, ImageDraw, ImageFont

FONTS   = "/usr/share/fonts/opentype/noto"
KO_BOLD = f"{FONTS}/NotoSansCJK-Bold.ttc"
KO_REG  = f"{FONTS}/NotoSansCJK-Regular.ttc"
W, H    = 1920, 1080

DARK       = (8,  12,  22)
DARK2      = (14, 20,  38)
PANEL      = (18, 26,  50)
GREEN      = (0,  200, 110)
GREEN_DIM  = (0,   90,  50)
WHITE      = (255, 255, 255)
WHITE_DIM  = (190, 200, 220)
GRAY       = ( 55,  65,  85)
KO_RED     = (210,  40,  40)   # Korean convention: red = up
KO_BLUE    = ( 70, 130, 210)   # Korean convention: blue = down
GOLD_DIM   = (130, 100,  40)


# ── 1. Fetch market data ──────────────────────────────────────────────────

def fetch_equity():
    """S&P500, NASDAQ, DOW, SOX — returns (price, pct_change)"""
    import yfinance as yf
    result = {}
    for label, sym in [("S&P 500","^GSPC"),("NASDAQ","^IXIC"),("DOW","^DJI"),("반도체(SOX)","^SOX")]:
        try:
            h = yf.Ticker(sym).history(period="5d")
            print(f"  {label}: {len(h)} rows", flush=True)
            if len(h) >= 2:
                prev, curr = h["Close"].iloc[-2], h["Close"].iloc[-1]
                result[label] = (curr, (curr-prev)/prev*100)
                print(f"    ✅ {curr:.2f}  {(curr-prev)/prev*100:+.2f}%", flush=True)
        except Exception as e:
            print(f"  ⚠️  {label}: {e}", flush=True)
    return result


def fetch_fx():
    """USD/KRW, EUR/USD, DXY — returns (price, pct_change)"""
    import yfinance as yf
    result = {}
    for label, sym in [("USD/KRW","KRW=X"),("EUR/USD","EURUSD=X"),("DXY","DX-Y.NYB")]:
        try:
            h = yf.Ticker(sym).history(period="5d")
            print(f"  {label}: {len(h)} rows", flush=True)
            if len(h) >= 2:
                prev, curr = h["Close"].iloc[-2], h["Close"].iloc[-1]
                result[label] = (curr, (curr-prev)/prev*100)
                print(f"    ✅ {curr:.4f}  {(curr-prev)/prev*100:+.2f}%", flush=True)
        except Exception as e:
            print(f"  ⚠️  {label}: {e}", flush=True)
    return result


def fetch_crypto():
    """Bitcoin — returns (price, pct_change)"""
    import yfinance as yf
    result = {}
    try:
        h = yf.Ticker("BTC-USD").history(period="2d")
        print(f"  BTC: {len(h)} rows", flush=True)
        if len(h) >= 2:
            prev, curr = h["Close"].iloc[-2], h["Close"].iloc[-1]
            result["비트코인"] = (curr, (curr-prev)/prev*100)
            print(f"    ✅ ${curr:,.0f}  {(curr-prev)/prev*100:+.2f}%", flush=True)
    except Exception as e:
        print(f"  ⚠️  BTC: {e}", flush=True)
    return result


def fetch_rates():
    """2yr, 5yr, 10yr, 30yr + Fed Funds via FRED. Published EOD ~4-5PM ET."""
    import requests
    result = {}
    for label, series in [
        ("미국 2년물",   "DGS2"),
        ("미국 5년물",   "DGS5"),
        ("미국 10년물",  "DGS10"),
        ("미국 30년물",  "DGS30"),
        ("연방기금금리", "DFEDTARU"),
    ]:
        try:
            r = requests.get(
                f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}",
                timeout=10
            )
            valid = [l for l in r.text.strip().split("\n")
                     if "," in l and l.split(",")[1].strip() not in ("", ".")]
            curr_val = float(valid[-1].split(",")[1])
            prev_val = float(valid[-2].split(",")[1])
            bp = (curr_val - prev_val) * 100
            result[label] = (curr_val, bp)
            print(f"  ✅ {label}: {curr_val:.2f}%  {bp:+.1f}bp", flush=True)
        except Exception as e:
            print(f"  ⚠️  {label} ({series}) failed: {e}", flush=True)
    return result


def fetch_all():
    try:
        import yfinance  # noqa
    except ImportError:
        print("  ⚠️  yfinance not installed — skipping market data", flush=True)
        return {}, {}, {}, {}
    print("  📈 Fetching equity...",  flush=True); eq  = fetch_equity()
    print("  💱 Fetching FX...",      flush=True); fx  = fetch_fx()
    print("  ₿  Fetching crypto...",  flush=True); cr  = fetch_crypto()
    print("  📊 Fetching rates...",   flush=True); rt  = fetch_rates()
    return eq, fx, cr, rt


# ── 2. Draw helpers ───────────────────────────────────────────────────────

def pct_color(chg):
    if abs(chg) < 0.001: return WHITE_DIM
    return KO_RED if chg > 0 else KO_BLUE

def pct_arrow(chg):
    if abs(chg) < 0.001: return " "
    return "▲" if chg > 0 else "▼"

def fmt_price(label, price):
    if "KRW" in label:          return f"{price:,.1f}"
    elif "비트코인" in label:    return f"${price:,.0f}"
    elif price > 10000:          return f"{price:,.0f}"
    elif price > 100:            return f"{price:,.2f}"
    else:                        return f"{price:.4f}"

def draw_group(draw, title, rows, x, y, font_title, font_row, font_sm,
               is_rates=False):
    """Draw a labeled group of market rows. Returns next y position."""
    # Group title
    draw.text((x, y), title, font=font_title, fill=(100, 120, 160))
    y += 30
    draw.line([(x, y), (x+530, y)], fill=(28, 38, 65), width=1)
    y += 8

    for label, (val, chg) in rows.items():
        col   = pct_color(chg)
        arrow = pct_arrow(chg)

        draw.text((x,       y), label,          font=font_row, fill=WHITE_DIM)
        draw.text((x+220,   y), fmt_price(label, val), font=font_row, fill=WHITE)

        if is_rates:
            chg_str = f"{arrow} {abs(chg):.1f}bp"
        else:
            chg_str = f"{arrow} {abs(chg):.2f}%"

        draw.text((x+390, y), chg_str, font=font_row, fill=col)
        y += 38

    return y + 10


# ── 3. Generate image ─────────────────────────────────────────────────────

def generate_background(equity, fx, crypto, rates):
    img  = Image.new("RGB", (W, H), DARK)
    draw = ImageDraw.Draw(img)

    # Background gradient
    for y in range(H):
        t = y/H
        r = int(DARK[0]+(DARK2[0]-DARK[0])*t)
        g = int(DARK[1]+(DARK2[1]-DARK[1])*t)
        b = int(DARK[2]+(DARK2[2]-DARK[2])*t)
        draw.line([(0,y),(W,y)], fill=(r,g,b))

    # Right panel
    for x in range(int(W*0.50), W):
        t  = (x-W*0.50)/(W*0.50)
        r  = int(DARK[0]+(PANEL[0]-DARK[0])*t)
        gc = int(DARK[1]+(PANEL[1]-DARK[1])*t)
        b  = int(DARK[2]+(PANEL[2]-DARK[2])*t)
        draw.line([(x,0),(x,H)], fill=(r,gc,b))

    # Grid
    for y in range(0, H, 44):
        draw.line([(0,y),(W,y)], fill=(18,26,44))
    for x in range(0, W, 88):
        draw.line([(x,0),(x,H)], fill=(18,26,44))

    # Abstract chart (bottom right)
    random.seed(42)
    val = 200
    pts = []
    cx0, cy0, cw, ch = int(W*0.54), H-200, int(W*0.42), 160
    for i in range(90):
        val += random.randint(-5, 12)
        x = cx0 + int(i/89*cw)
        y = cy0 + ch//2 - int((val-200)*0.4)
        pts.append((x, max(cy0-ch//2, min(cy0+ch//2, y))))

    overlay = Image.new("RGBA",(W,H),(0,0,0,0))
    ov = ImageDraw.Draw(overlay)
    ov.polygon([(pts[0][0],cy0+ch//2)]+pts+[(pts[-1][0],cy0+ch//2)],
               fill=(0,200,110,18))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    for i in range(len(pts)-1):
        draw.line([pts[i],pts[i+1]], fill=GREEN, width=2)

    ex, ey = pts[-1]
    for rs,a in [(18,8),(11,22),(6,65),(3,200)]:
        ov2 = Image.new("RGBA",(W,H),(0,0,0,0))
        ImageDraw.Draw(ov2).ellipse([(ex-rs,ey-rs),(ex+rs,ey+rs)],fill=(0,200,110,a))
        img = Image.alpha_composite(img.convert("RGBA"),ov2).convert("RGB")
        draw = ImageDraw.Draw(img)
    draw.ellipse([(ex-4,ey-4),(ex+4,ey+4)], fill=WHITE)

    # Decorative candlesticks
    random.seed(7)
    cx = int(W*0.54) - 100
    for _ in range(7):
        bh  = random.randint(12,40)
        by  = cy0 - 60 + random.randint(-30,30)
        up  = random.random() > 0.35
        col = KO_RED if up else KO_BLUE
        draw.rectangle([(cx-7,by),(cx+7,by+bh)], fill=col)
        draw.line([(cx,by-8),(cx,by)], fill=col, width=2)
        draw.line([(cx,by+bh),(cx,by+bh+8)], fill=col, width=2)
        cx += 24

    # Left accent
    draw.rectangle([(0,0),(6,H)], fill=GREEN)
    draw.line([(80,155),(int(W*0.47),155)], fill=GREEN, width=2)
    draw.line([(80,H-100),(int(W*0.47),H-100)], fill=GRAY, width=1)

    # ── Fonts ─────────────────────────────────────────────────────────────
    fh  = ImageFont.truetype(KO_BOLD, 130)
    fl  = ImageFont.truetype(KO_BOLD,  72)
    fm  = ImageFont.truetype(KO_BOLD,  44)
    fr  = ImageFont.truetype(KO_REG,   26)
    fs  = ImageFont.truetype(KO_REG,   20)
    fgt = ImageFont.truetype(KO_REG,   18)  # group title

    # ── Left panel ────────────────────────────────────────────────────────
    from zoneinfo import ZoneInfo
    KST    = ZoneInfo("Asia/Seoul")
    NY     = ZoneInfo("America/New_York")
    now_kst = datetime.now(KST)
    now_ny  = datetime.now(NY)

    draw.ellipse([(80,118),(96,134)], fill=GREEN)
    draw.text((110,112), "미국 증시 마감 후 브리핑", font=fr, fill=WHITE_DIM)
    draw.text((80,175),  "월스트리트",   font=fh, fill=WHITE)
    draw.text((80,328),  "오늘의 시황",  font=fl, fill=GREEN)
    draw.text((80,420),  now_kst.strftime("%Y년 %m월 %d일"), font=fm, fill=GREEN)
    draw.text((80,490),  "글로벌 경제 · 금융 · 비즈니스 핵심 뉴스",
              font=fr, fill=(90,100,130))

    # ── Right panel: grouped market data ──────────────────────────────────
    px, py = int(W*0.525), 55

    # Header
    draw.text((px, py),
              f"시장 데이터  ·  {now_ny.strftime('%m/%d %H:%M')} NY시간",
              font=fs, fill=(55,70,105))
    py += 32
    draw.line([(px, py),(px+560, py)], fill=(28,38,65), width=1)
    py += 14

    if equity:
        py = draw_group(draw,"주식 (Equity)", equity,  px, py, fgt, fs, fgt)
    if fx:
        py = draw_group(draw,"외환 (FX)",     fx,      px, py, fgt, fs, fgt)
    if crypto:
        py = draw_group(draw,"암호화폐",      crypto,  px, py, fgt, fs, fgt)

    print(f"  [Draw] equity={len(equity)} fx={len(fx)} crypto={len(crypto)} rates={len(rates)} py_before_rates={py}", flush=True)

    if rates:
        py = draw_group(draw,"금리 (bp 변화)", rates,  px, py, fgt, fs, fgt,
                        is_rates=True)
        print(f"  [Draw] rates drawn, py_after={py}", flush=True)
    else:
        print(f"  [Draw] rates dict is EMPTY — skipping", flush=True)

    # Bottom
    draw.rectangle([(0,H-72),(W,H)], fill=(10,16,30))
    draw.text((80,H-50),
              "매일 오전 한국어로 전해드리는 글로벌 경제 뉴스",
              font=fs, fill=(45,55,75))
    draw.text((W-290,H-50), "ECONOMY BRIEFING", font=fs, fill=GREEN_DIM)

    os.makedirs("assets", exist_ok=True)
    img.save("assets/background.jpg", "JPEG", quality=95)
    print("✅ Background saved → assets/background.jpg", flush=True)


# ── Main ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("[Background] Fetching market data...", flush=True)
    eq, fx, cr, rt = fetch_all()
    print("[Background] Generating image...", flush=True)
    generate_background(eq, fx, cr, rt)
