"""
Test: generate country map treemap using iShares ETFs.
All USD-denominated, US-listed. Box size = ETF market cap (price * shares outstanding).
Color = Korean convention (red=up, blue=down).
"""

import math, random, yfinance as yf
from PIL import Image, ImageDraw, ImageFont

OUTPUT  = "/mnt/user-data/outputs/country_map_test.jpg"
FONTS   = "/usr/share/fonts/opentype/noto"
KO_BOLD = f"{FONTS}/NotoSansCJK-Bold.ttc"
KO_REG  = f"{FONTS}/NotoSansCJK-Regular.ttc"
W, H    = 1920, 1080

DARK  = (8,  12,  22)
DARK2 = (14, 20,  38)
WHITE = (255, 255, 255)
DIM   = (190, 200, 220)
GRAY  = ( 55,  65,  85)
GREEN_DIM = (0, 80, 45)

# All country ETFs — US listed, USD returns
# (etf, korean_name, english_name, region)
COUNTRIES = [
    # North America
    ("SPY",  "미국",      "USA",         "DM"),
    ("EWC",  "캐나다",    "Canada",      "DM"),
    ("EWW",  "멕시코",    "Mexico",      "EM"),
    # Europe DM
    ("EWU",  "영국",      "UK",          "DM"),
    ("EWG",  "독일",      "Germany",     "DM"),
    ("EWQ",  "프랑스",    "France",      "DM"),
    ("EWL",  "스위스",    "Switzerland", "DM"),
    ("EWN",  "네덜란드",  "Netherlands", "DM"),
    ("EWI",  "이탈리아",  "Italy",       "DM"),
    ("EWP",  "스페인",    "Spain",       "DM"),
    ("EWD",  "스웨덴",    "Sweden",      "DM"),
    ("EWK",  "벨기에",    "Belgium",     "DM"),
    ("EDEN", "덴마크",    "Denmark",     "DM"),
    ("EWO",  "오스트리아","Austria",     "DM"),
    # Asia Pacific DM
    ("EWJ",  "일본",      "Japan",       "DM"),
    ("EWA",  "호주",      "Australia",   "DM"),
    ("EWS",  "싱가포르",  "Singapore",   "DM"),
    ("EWH",  "홍콩",      "Hong Kong",   "DM"),
    ("EWY",  "한국",      "Korea",       "EM"),
    ("EIS",  "이스라엘",  "Israel",      "DM"),
    # EM Asia
    ("MCHI", "중국",      "China",       "EM"),
    ("INDA", "인도",      "India",       "EM"),
    ("EWT",  "대만",      "Taiwan",      "EM"),
    ("EWM",  "말레이시아","Malaysia",    "EM"),
    ("THD",  "태국",      "Thailand",    "EM"),
    ("EPHE", "필리핀",    "Philippines", "EM"),
    ("EIDO", "인도네시아","Indonesia",   "EM"),
    ("VNM",  "베트남",    "Vietnam",     "EM"),
    # EM EMEA
    ("EZA",  "남아공",    "S.Africa",    "EM"),
    ("TUR",  "터키",      "Turkey",      "EM"),
    ("KSA",  "사우디",    "Saudi Arabia","EM"),
    ("UAE",  "UAE",       "UAE",         "EM"),
    ("QAT",  "카타르",    "Qatar",       "EM"),
    ("EPOL", "폴란드",    "Poland",      "EM"),
    ("GREK", "그리스",    "Greece",      "EM"),
    # EM Americas
    ("EWZ",  "브라질",    "Brazil",      "EM"),
    ("ECH",  "칠레",      "Chile",       "EM"),
    ("EPU",  "페루",      "Peru",        "EM"),
]


def chg_color(chg):
    """Korean convention: red=up, blue=down. Intensity scales with magnitude."""
    if abs(chg) < 0.05:
        return (28, 36, 58)
    intensity = min(abs(chg) / 3.0, 1.0)
    if chg > 0:
        return (int(60+150*intensity), int(10+10*(1-intensity)), int(10+10*(1-intensity)))
    else:
        return (int(10+10*(1-intensity)), int(15+20*(1-intensity)), int(60+150*intensity))


def fetch_country_data():
    tickers = [c[0] for c in COUNTRIES]
    print(f"Downloading {len(tickers)} ETFs...", flush=True)
    data = yf.download(tickers, period="5d", auto_adjust=True,
                       progress=False, group_by="ticker")

    # Also get shares outstanding for market cap sizing
    results = {}
    for etf, ko, en, region in COUNTRIES:
        try:
            closes = data[etf]["Close"].dropna()
            if len(closes) < 2:
                print(f"  ⚠️  {etf} ({en}): only {len(closes)} rows", flush=True)
                continue
            price = closes.iloc[-1]
            chg   = (closes.iloc[-1] - closes.iloc[-2]) / closes.iloc[-2] * 100

            # Use ETF info for shares outstanding → market cap
            t = yf.Ticker(etf)
            info = t.fast_info
            mcap = getattr(info, "market_cap", None) or (price * 1e6)

            results[etf] = {
                "ko": ko, "en": en, "region": region,
                "price": price, "chg": chg, "mcap": mcap
            }
            print(f"  ✅ {etf:6} {en:15} ${price:.2f}  {chg:+.2f}%  mcap=${mcap/1e9:.1f}B", flush=True)
        except Exception as e:
            print(f"  ❌ {etf:6} {en}: {e}", flush=True)
    return results


def squarify(items, x, y, w, h):
    """Simple row-based treemap layout. items = list of (key, weight)."""
    if not items:
        return []
    total = sum(v for _, v in items)
    if total == 0:
        return []

    rects = []
    remaining = list(items)
    rx, ry, rw, rh = x, y, w, h

    while remaining:
        # Decide whether to lay out a row horizontally or vertically
        use_width = rw >= rh

        # Greedily pick items for this row while aspect ratio improves
        row = []
        row_weight = 0
        best_ar = float("inf")

        for item in remaining:
            row.append(item)
            row_weight += item[1]
            frac = row_weight / total

            if use_width:
                row_h = rh * frac if frac > 0 else rh
                cell_w = (rw * item[1] / row_weight) if row_weight > 0 else rw
                ar = max(row_h / cell_w, cell_w / row_h) if cell_w > 0 else float("inf")
            else:
                row_w = rw * frac if frac > 0 else rw
                cell_h = (rh * item[1] / row_weight) if row_weight > 0 else rh
                ar = max(row_w / cell_h, cell_h / row_w) if cell_h > 0 else float("inf")

            if ar > best_ar and len(row) > 1:
                row.pop()
                row_weight -= item[1]
                break
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
            ry += strip_h
            rh -= strip_h
        else:
            strip_w = int(rw * row_frac)
            cy = ry
            for key, wt in row:
                ch2 = int(rh * wt / row_weight)
                rects.append((key, rx, cy, strip_w, ch2))
                cy += ch2
            rx += strip_w
            rw -= strip_w

    return rects


def generate_map(countries):
    img  = Image.new("RGB", (W, H), DARK)
    draw = ImageDraw.Draw(img)

    for y in range(H):
        t = y/H
        draw.line([(0,y),(W,y)], fill=(int(8+6*t),int(12+8*t),int(22+16*t)))

    draw.rectangle([(0,0),(6,H)], fill=(0,200,110))

    fh    = ImageFont.truetype(KO_BOLD, 48)
    fm    = ImageFont.truetype(KO_BOLD, 28)
    fr    = ImageFont.truetype(KO_REG,  22)
    fs    = ImageFont.truetype(KO_REG,  17)
    fmono = ImageFont.truetype(KO_REG,  16)

    from zoneinfo import ZoneInfo
    from datetime import datetime
    NY  = ZoneInfo("America/New_York")
    now = datetime.now(NY)

    draw.text((80, 28), "글로벌 증시 국가별 수익률", font=fh, fill=WHITE)
    draw.text((760, 40), f"iShares ETF 기준  ·  {now.strftime('%m/%d %H:%M')} NY시간", font=fs, fill=(70,85,120))
    draw.line([(80, 88),(W-80, 88)], fill=(0,200,110), width=2)

    # Sort by mcap descending for treemap
    items = [(etf, math.sqrt(v["mcap"])) for etf, v in countries.items()]
    items.sort(key=lambda x: -x[1])

    PAD  = 5
    MX, MY, MW, MH = 80, 100, W-160, H-150

    rects = squarify(items, MX, MY, MW, MH)

    for (etf, rx, ry, rw, rh) in rects:
        if etf not in countries:
            continue
        v = countries[etf]
        color = chg_color(v["chg"])

        draw.rectangle([(rx+PAD,ry+PAD),(rx+rw-PAD,ry+rh-PAD)], fill=color)
        draw.rectangle([(rx+PAD,ry+PAD),(rx+rw-PAD,ry+rh-PAD)], outline=(0,0,0), width=1)

        cx = rx + rw//2
        cy = ry + rh//2
        area = rw * rh

        # DM/EM badge
        badge_col = (40,80,140) if v["region"]=="DM" else (80,40,100)
        draw.rectangle([(rx+PAD+4,ry+PAD+4),(rx+PAD+30,ry+PAD+18)], fill=badge_col)
        draw.text((rx+PAD+6,ry+PAD+4), v["region"], font=fmono, fill=(180,200,230))

        # Korean name
        if area > 150000:
            fko = fm
        elif area > 40000:
            fko = fr
        else:
            fko = fmono

        ko_text = v["ko"]
        bk = draw.textbbox((0,0), ko_text, font=fko)
        tw = bk[2]-bk[0]
        draw.text((cx-tw//2, cy-22), ko_text, font=fko, fill=WHITE)

        # % change
        arrow  = "▲" if v["chg"] >= 0 else "▼"
        chg_col= (255,180,180) if v["chg"] >= 0 else (180,200,255)
        if abs(v["chg"]) >= 0.05:
            chg_str = f"{arrow}{abs(v['chg']):.2f}%"
        else:
            chg_str = f"{v['chg']:.2f}%"

        if area > 40000:
            bch = draw.textbbox((0,0), chg_str, font=fr)
            tcw = bch[2]-bch[0]
            draw.text((cx-tcw//2, cy+4), chg_str, font=fr, fill=chg_col)

    # Legend
    lx, ly = W-420, H-42
    draw.text((lx,     ly), "■ 상승", font=fmono, fill=(200,80,80))
    draw.text((lx+80,  ly), "■ 보합", font=fmono, fill=(60,70,100))
    draw.text((lx+160, ly), "■ 하락", font=fmono, fill=(80,100,200))
    draw.text((lx+240, ly), "  (적=상승  청=하락)", font=fmono, fill=GRAY)

    draw.text((80, H-40), "iShares MSCI ETF 기준  ·  USD 수익률  ·  박스크기 = ETF 시가총액", font=fmono, fill=(45,55,75))

    img.save(OUTPUT, "JPEG", quality=95)
    print(f"✅ Saved → {OUTPUT}", flush=True)


if __name__ == "__main__":
    print("Fetching country ETF data...", flush=True)
    countries = fetch_country_data()
    print(f"\nGenerating map with {len(countries)} countries...", flush=True)
    generate_map(countries)
