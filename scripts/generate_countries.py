"""
Geographic grid treemap — live ETF data via yfinance.
On Sunday UTC: uses Friday-to-Friday weekly returns.
"""
import os, json, datetime
import requests
from PIL import Image, ImageDraw, ImageFont
from zoneinfo import ZoneInfo

OUTPUT = "assets/countries.jpg"
FONTS  = "/usr/share/fonts/opentype/noto"
KO_BOLD= f"{FONTS}/NotoSansCJK-Bold.ttc"
KO_REG = f"{FONTS}/NotoSansCJK-Regular.ttc"
W, H   = 1920, 1080
DARK   = (8, 12, 22)
WHITE  = (255,255,255)
GRAY   = (55, 65, 85)
GREEN  = (0, 200, 110)

# Korean name mapping for each ticker
NAMES = {
    "SPY":  "미국",    "EWC":  "캐나다",    "EWW":  "멕시코",   "EWZ":  "브라질",
    "ARGT": "아르헨티나","ECH": "칠레",     "EPU":  "페루",     "GXG":  "콜롬비아",
    "EWU":  "영국",    "EWG":  "독일",      "EWP":  "스페인",   "EWL":  "스위스",
    "EWI":  "이탈리아","EWQ":  "프랑스",   "EWD":  "스웨덴",   "GREK": "그리스",
    "TUR":  "터키",    "EWN":  "네덜란드",  "EPOL": "폴란드",   "EDEN": "덴마크",
    "EWO":  "오스트리아","ENOR":"노르웨이", "EFNL": "핀란드",   "EWK":  "벨기에",
    "EIS":  "이스라엘","KSA":  "사우디",    "UAE":  "UAE",      "KWT":  "쿠웨이트",
    "QAT":  "카타르",  "EZA":  "남아공",    "EWJ":  "일본",     "EWY":  "한국",
    "INDA": "인도",    "EWT":  "대만",      "MCHI": "중국",     "EWS":  "싱가포르",
    "EWH":  "홍콩",    "EWA":  "호주",      "VNM":  "베트남",   "EWM":  "말레이시아",
    "THD":  "태국",    "EIDO": "인도네시아","EPHE": "필리핀",   "ENZL": "뉴질랜드",
}

def is_weekly_mode():
    is_sunday = datetime.datetime.utcnow().weekday() == 6
    if is_sunday:
        print("📅 Sunday UTC — using weekly (Fri-to-Fri) returns", flush=True)
    return is_sunday

def fetch_live_data():
    """Fetch live ETF returns from yfinance. Weekly on Sunday, daily otherwise."""
    import yfinance as yf
    weekly = is_weekly_mode()
    tickers = list(NAMES.keys())
    period = "10d" if weekly else "5d"
    print(f"  Downloading {len(tickers)} ETFs (period={period})...", flush=True)
    data = yf.download(tickers, period=period, auto_adjust=True,
                       progress=False, group_by="ticker")
    result = {}
    for ticker, ko in NAMES.items():
        try:
            closes = data[ticker]["Close"].dropna()
            if len(closes) < 2:
                continue
            if weekly:
                fridays = closes[closes.index.dayofweek == 4]
                if len(fridays) >= 2:
                    prev, curr = fridays.iloc[-2], fridays.iloc[-1]
                else:
                    prev, curr = closes.iloc[0], closes.iloc[-1]
            else:
                prev, curr = closes.iloc[-2], closes.iloc[-1]
            chg = (curr - prev) / prev * 100
            result[ticker] = (ko, round(chg, 2))
        except Exception as e:
            print(f"  ⚠️  {ticker}: {e}", flush=True)
    print(f"  ✅ Got data for {len(result)} ETFs", flush=True)
    return result

# Will be populated at runtime
DATA = {}

# Tighter grids — no wasted columns
LAYOUTS = {
    "AM": [                                    # 3 cols
        [None,   "EWC",  None  ],               # Canada (center)
        [None,   "SPY",  None  ],               # USA (center)
        [("EWW",  1),("GXG",  1),("EWZ",  1)], # Mexico, Colombia, Brazil
        [("EPU",  1),("ECH",  1),("ARGT", 1)], # Peru, Chile, Argentina
    ],
    "EU": [                                    # 4 cols
        ["ENOR", "EWD",  "EDEN", "EFNL"],     # Scandinavia
        ["EWU",  "EWK",  "EWN",  "EPOL"],     # UK, Benelux, Poland
        ["EWQ",  "EWG",  "EWO",  None  ],     # France, Germany, Austria
        ["EWP",  "EWL",  "EWI",  "GREK"],     # Spain, Swiss, Italy, Greece
        [None,   None,   None,   "TUR" ],      # Turkey (SE)
    ],
    "MENA": [                                  # 4 cols
        ["EIS",  "KWT",  "QAT",  "UAE" ],     # Israel → Gulf
        ["EZA",  "KSA",  None,   None  ],     # S.Africa + Saudi same row
    ],
    "AS": [                                    # 3 cols
        [None,   "EWJ",  "EWY" ],             # Japan, Korea (NE)
        ["MCHI", "EWH",  "EWT" ],             # China, HK, Taiwan
        ["INDA", "VNM",  None  ],             # India (W), Vietnam
        ["EWS",  "THD",  "EPHE"],             # Singapore, Thailand, Philippines
        [None,   "EWM",  "EIDO"],             # Malaysia, Indonesia
        [None,   "EWA",  "ENZL"],             # Australia, NZ (S)
    ],
}

def chg_color(chg):
    if abs(chg) < 0.05:
        return (28, 36, 58)
    intensity = min(abs(chg) / 3.5, 1.0)
    if chg > 0:
        return (int(55+165*intensity), int(10+8*(1-intensity)), int(10+8*(1-intensity)))
    else:
        return (int(10+8*(1-intensity)), int(15+15*(1-intensity)), int(55+165*intensity))

def fit_label(draw, cx, cy, bw, bh, ko, chg, fonts):
    arrow   = "▲" if chg > 0.05 else ("▼" if chg < -0.05 else "")
    chg_col = (255,160,160) if chg>0.05 else ((150,190,255) if chg<-0.05 else (155,165,185))
    chg_str = f"{arrow}{abs(chg):.2f}%" if abs(chg) >= 0.05 else f"{chg:.2f}%"
    for fko, fch in fonts:
        nh  = fko.size + 2
        ch2 = fch.size + 2
        bk  = draw.textbbox((0,0), ko,      font=fko)
        bc  = draw.textbbox((0,0), chg_str, font=fch)
        tw  = bk[2]-bk[0]
        tcw = bc[2]-bc[0]
        # Stacked
        if tw < bw-4 and tcw < bw-4 and nh+ch2 < bh-4:
            sy = cy-(nh+ch2)//2
            draw.text((cx-tw//2,  sy),    ko,      font=fko, fill=WHITE)
            draw.text((cx-tcw//2, sy+nh), chg_str, font=fch, fill=chg_col)
            return
        # Side by side
        if tw+4+tcw < bw-4 and max(nh,ch2) < bh-4:
            sx = cx-(tw+4+tcw)//2
            my = cy-max(nh,ch2)//2
            draw.text((sx,      my), ko,      font=fko, fill=WHITE)
            draw.text((sx+tw+4, my), chg_str, font=fch, fill=chg_col)
            return
        # Only %
        if tcw < bw-4 and ch2 < bh-4:
            draw.text((cx-tcw//2, cy-ch2//2), chg_str, font=fch, fill=chg_col)
            return

def draw_region(draw, fonts, label, layout, rx, ry, rw, rh, lbl_col):
    LBAR = 40
    flabel = fonts[2][0]  # KO_BOLD 18px
    draw.rectangle([(rx,ry),(rx+rw,ry+LBAR)], fill=(12,18,34))
    draw.text((rx+10, ry+8), label, font=flabel, fill=lbl_col)

    tx, ty = rx, ry+LBAR
    tw, th = rw, rh-LBAR
    if tw<=0 or th<=0 or not layout: return

    # Normalize layout: support both plain strings and (ticker, span) tuples
    def parse_row(row):
        parsed = []
        for cell in row:
            if cell is None:
                parsed.append((None, 1))
            elif isinstance(cell, tuple):
                parsed.append(cell)  # (ticker, span)
            else:
                parsed.append((cell, 1))
        return parsed

    nrows = len(layout)
    # ncols = max total span in any row
    ncols = max(sum(span for _, span in parse_row(row)) for row in layout)
    unit_w = tw / ncols
    cell_h = th // nrows
    PAD = 3

    for r, row in enumerate(layout):
        parsed = parse_row(row)
        col_pos = 0
        for ticker, span in parsed:
            cell_w = int(unit_w * span)
            if ticker and ticker in DATA:
                ko, chg = DATA[ticker]
                bx = tx + int(col_pos * unit_w) + PAD
                by = ty + r*cell_h + PAD
                bw = cell_w - PAD*2
                bh = cell_h - PAD*2
                draw.rectangle([(bx,by),(bx+bw,by+bh)], fill=chg_color(chg))
                draw.rectangle([(bx,by),(bx+bw,by+bh)], outline=(5,8,18), width=1)
                fit_label(draw, bx+bw//2, by+bh//2, bw, bh, ko, chg, fonts)
            col_pos += span

def generate():
    global DATA
    print("[Countries] Fetching live ETF data...", flush=True)
    DATA = fetch_live_data()
    if not DATA:
        print("  ⚠️  No live data — aborting", flush=True)
        return

    img  = Image.new("RGB",(W,H),DARK)
    draw = ImageDraw.Draw(img)
    for y in range(H):
        t = y/H
        draw.line([(0,y),(W,y)],fill=(int(8+6*t),int(12+8*t),int(22+16*t)))

    # Extended font ladder down to 9px
    fonts = [
        (ImageFont.truetype(KO_BOLD,30), ImageFont.truetype(KO_REG,22)),
        (ImageFont.truetype(KO_BOLD,24), ImageFont.truetype(KO_REG,18)),
        (ImageFont.truetype(KO_BOLD,18), ImageFont.truetype(KO_REG,15)),
        (ImageFont.truetype(KO_BOLD,14), ImageFont.truetype(KO_REG,13)),
        (ImageFont.truetype(KO_REG,12),  ImageFont.truetype(KO_REG,11)),
        (ImageFont.truetype(KO_REG,11),  ImageFont.truetype(KO_REG,10)),
        (ImageFont.truetype(KO_REG,10),  ImageFont.truetype(KO_REG, 9)),
        (ImageFont.truetype(KO_REG, 9),  ImageFont.truetype(KO_REG, 9)),
    ]
    fh    = ImageFont.truetype(KO_BOLD, 48)
    fs    = ImageFont.truetype(KO_REG,  20)
    fmono = ImageFont.truetype(KO_REG,  14)

    NY  = ZoneInfo("America/New_York"); now = datetime.now(NY)
    draw.rectangle([(0,0),(6,H)], fill=GREEN)
    draw.text((80,22), "글로벌 증시 국가별 수익률", font=fh, fill=WHITE)
    draw.text((760,34),
              f"iShares · VanEck · GlobalX ETF  ·  {now.strftime('%m/%d %H:%M')} NY시간",
              font=fs, fill=(70,85,120))
    draw.line([(80,82),(W-80,82)], fill=GREEN, width=2)

    PAD=5; MX,MY=80,90; MW=W-160; MH=H-135

    # Column widths based on max columns in each region
    am_cols   = max(len(r) for r in LAYOUTS["AM"])
    eu_cols   = max(len(r) for r in LAYOUTS["EU"])   # same as MENA cols for shared width
    as_cols   = max(len(r) for r in LAYOUTS["AS"])
    total_col = am_cols + eu_cols + as_cols

    cw0 = int(MW * am_cols / total_col)
    cw1 = int(MW * eu_cols / total_col)
    cw2 = MW - cw0 - cw1 - PAD*2
    cx0 = MX; cx1 = MX+cw0+PAD; cx2 = cx1+cw1+PAD

    # Col 1: Americas
    draw_region(draw, fonts, "아메리카", LAYOUTS["AM"],
                cx0, MY, cw0, MH, (100,200,150))

    # Col 2: Europe (top) / MENA (bottom) split by row count
    eu_rows   = len(LAYOUTS["EU"])
    mena_rows = len(LAYOUTS["MENA"])
    eu_h   = int(MH * eu_rows   / (eu_rows+mena_rows)) - PAD
    mena_h = MH - eu_h - PAD

    draw_region(draw, fonts, "유럽", LAYOUTS["EU"],
                cx1, MY, cw1, eu_h, (100,150,220))
    draw_region(draw, fonts, "중동 · 아프리카", LAYOUTS["MENA"],
                cx1, MY+eu_h+PAD, cw1, mena_h, (200,160,70))

    # Col 3: Asia + Oceania
    draw_region(draw, fonts, "아시아 · 오세아니아", LAYOUTS["AS"],
                cx2, MY, cw2, MH, (210,110,110))

    for cx in [cx1-PAD//2, cx2-PAD//2]:
        draw.line([(cx,MY),(cx,MY+MH)], fill=(20,30,50), width=1)

    lx, ly = 80, H-42
    draw.text((lx,    ly), "■ 상승", font=fmono, fill=(200,60,60))
    draw.text((lx+75, ly), "■ 보합", font=fmono, fill=(50,65,100))
    draw.text((lx+150,ly), "■ 하락", font=fmono, fill=(60,100,210))
    draw.text((lx+225,ly), "  (적=상승  청=하락)  ·  지리적 위치 기반 배치",
              font=fmono, fill=GRAY)
    draw.text((1480,  ly), "iShares / VanEck / GlobalX ETF  ·  USD",
              font=fmono, fill=GRAY)

    os.makedirs("assets", exist_ok=True)
    img.save(OUTPUT, "JPEG", quality=95)
    print(f"✅ Saved → {OUTPUT}")

    # Append countries data to market_data.json
    try:
        with open("assets/market_data.json") as f:
            data = json.load(f)
    except Exception:
        data = {}
    data["countries"] = {
        ticker: {"ko": ko, "chg_pct": round(chg, 2)}
        for ticker, (ko, chg) in DATA.items()
    }
    with open("assets/market_data.json", "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("✅ Countries saved → assets/market_data.json", flush=True)

generate()
