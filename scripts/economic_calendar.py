#!/usr/bin/env python3
"""
Fetch this week's earnings calendar from Finnhub (free tier) and generate:
  1. temp/calendar.json — structured earnings data
  2. assets/calendar.jpg — visual card for video (last section)
  3. Append [경제일정] section to korean_script.txt

Usage:
    python economic_calendar.py
"""

import json, os, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("Missing: pip install requests")

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    sys.exit("Missing: pip install pillow")


FINNHUB_KEY   = os.environ.get("FINNHUB_API_KEY", "")
CALENDAR_JSON = "temp/calendar.json"
CALENDAR_IMG  = "assets/calendar.jpg"
SCRIPT_FILE   = "temp/korean_script.txt"

W, H = 1920, 1080
FONTS = "/usr/share/fonts/opentype/noto"
KO_BOLD = f"{FONTS}/NotoSansCJK-Bold.ttc"
KO_REG  = f"{FONTS}/NotoSansCJK-Regular.ttc"

DARK      = (8, 12, 22)
DARK2     = (14, 20, 38)
WHITE     = (255, 255, 255)
WHITE_DIM = (190, 200, 220)
GREEN     = (0, 200, 110)
GREEN_DIM = (0, 80, 45)
AMBER     = (255, 167, 38)
KO_RED    = (210, 40, 40)
KO_BLUE   = (70, 130, 210)
GRAY      = (55, 65, 85)


def fetch_earnings():
    """Fetch this week's earnings from Finnhub."""
    if not FINNHUB_KEY:
        print("⚠️  FINNHUB_API_KEY not set", flush=True)
        return []

    today = datetime.now(timezone.utc).date()
    monday = today - timedelta(days=today.weekday())
    friday = monday + timedelta(days=4)

    try:
        r = requests.get("https://finnhub.io/api/v1/calendar/earnings", params={
            "from": monday.isoformat(),
            "to": friday.isoformat(),
            "token": FINNHUB_KEY,
        }, timeout=15)
        data = r.json()
        earnings = data.get("earningsCalendar", [])
        print(f"📅 Fetched {len(earnings)} earnings events for {monday} ~ {friday}", flush=True)
        return earnings
    except Exception as e:
        print(f"⚠️  Finnhub API error: {e}", flush=True)
        return []


def filter_top_earnings(earnings, max_count=20):
    """Filter to the most notable earnings. Prioritize by estimated revenue/EPS."""
    # Sort: companies with EPS estimates first (more notable), then alphabetically
    with_est = [e for e in earnings if e.get("epsEstimate") is not None]
    without_est = [e for e in earnings if e.get("epsEstimate") is None]

    # Among those with estimates, sort by absolute EPS estimate (larger = more notable)
    with_est.sort(key=lambda x: abs(x.get("epsEstimate", 0) or 0), reverse=True)

    combined = with_est + without_est
    return combined[:max_count]


def generate_calendar_image(earnings):
    """Generate a visual earnings calendar card."""
    img = Image.new("RGB", (W, H), DARK)
    draw = ImageDraw.Draw(img)

    # Gradient background
    for y in range(H):
        t = y / H
        r = int(DARK[0] + (DARK2[0] - DARK[0]) * t)
        g = int(DARK[1] + (DARK2[1] - DARK[1]) * t)
        b = int(DARK[2] + (DARK2[2] - DARK[2]) * t)
        draw.line([(0, y), (W, y)], fill=(r, g, b))

    # Left accent
    draw.rectangle([(0, 0), (6, H)], fill=GREEN)

    try:
        fh = ImageFont.truetype(KO_BOLD, 48)
        fm = ImageFont.truetype(KO_BOLD, 28)
        fr = ImageFont.truetype(KO_REG, 24)
        fs = ImageFont.truetype(KO_REG, 20)
    except Exception:
        fh = fm = fr = fs = ImageFont.load_default()

    today = datetime.now(timezone.utc).date()
    monday = today - timedelta(days=today.weekday())
    friday = monday + timedelta(days=4)

    # Header
    draw.text((80, 25), "이번 주 실적 발표 일정", font=fh, fill=WHITE)
    draw.text((80, 85),
              f"{monday.strftime('%Y.%m.%d')} ~ {friday.strftime('%Y.%m.%d')}  |  주요 기업 실적 발표",
              font=fs, fill=(70, 85, 120))
    draw.line([(80, 120), (W - 80, 120)], fill=GREEN, width=2)

    if not earnings:
        draw.text((W // 2 - 250, H // 2 - 20),
                  "이번 주 주요 실적 발표 일정이 없습니다.",
                  font=fm, fill=WHITE_DIM)
    else:
        # Group by date
        by_date = {}
        for e in earnings:
            date = e.get("date", "TBD")
            if date not in by_date:
                by_date[date] = []
            by_date[date].append(e)

        y = 140

        for date_str, day_earnings in sorted(by_date.items()):
            # Date header
            try:
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                DAY_KO = {0: "월", 1: "화", 2: "수", 3: "목", 4: "금", 5: "토", 6: "일"}
                date_label = f"{dt.strftime('%m/%d')} ({DAY_KO.get(dt.weekday(), '')})"
            except Exception:
                date_label = date_str

            draw.rectangle([(70, y), (W - 70, y + 34)], fill=(12, 18, 34))
            draw.text((80, y + 4), date_label, font=fm, fill=AMBER)
            y += 42

            # Column headers
            draw.text((80, y), "티커", font=fs, fill=GRAY)
            draw.text((220, y), "발표 시점", font=fs, fill=GRAY)
            draw.text((400, y), "EPS 예상", font=fs, fill=GRAY)
            draw.text((580, y), "EPS 실적", font=fs, fill=GRAY)
            draw.text((760, y), "매출 예상", font=fs, fill=GRAY)
            y += 28

            for i, e in enumerate(day_earnings):
                if y > H - 90:
                    break

                bg = (14, 20, 38) if i % 2 == 0 else (18, 26, 46)
                draw.rectangle([(70, y), (W - 70, y + 36)], fill=bg)

                symbol = e.get("symbol", "?")
                hour = e.get("hour", "")
                hour_ko = {"bmo": "장전", "amc": "장후", "dmh": "장중"}.get(hour, hour)

                eps_est = e.get("epsEstimate")
                eps_act = e.get("epsActual")
                rev_est = e.get("revenueEstimate")

                # EPS color: green if beat, red if miss
                if eps_act is not None and eps_est is not None:
                    try:
                        eps_color = GREEN if float(eps_act) >= float(eps_est) else KO_RED
                    except (ValueError, TypeError):
                        eps_color = WHITE_DIM
                else:
                    eps_color = WHITE_DIM

                def fmt_val(v, prefix="$"):
                    if v is None:
                        return "-"
                    try:
                        val = float(v)
                        if abs(val) >= 1e9:
                            return f"{prefix}{val/1e9:.1f}B"
                        elif abs(val) >= 1e6:
                            return f"{prefix}{val/1e6:.0f}M"
                        else:
                            return f"{prefix}{val:.2f}"
                    except (ValueError, TypeError):
                        return str(v)

                draw.text((80, y + 6), symbol, font=fm, fill=WHITE)
                draw.text((220, y + 8), hour_ko, font=fs, fill=WHITE_DIM)
                draw.text((400, y + 8), fmt_val(eps_est), font=fs, fill=WHITE_DIM)
                draw.text((580, y + 8), fmt_val(eps_act), font=fs, fill=eps_color)
                draw.text((760, y + 8), fmt_val(rev_est), font=fs, fill=WHITE_DIM)

                y += 38

            y += 8  # gap between dates

    # Bottom
    draw.rectangle([(0, H - 55), (W, H)], fill=(10, 16, 30))
    draw.text((80, H - 38),
              "Finnhub 실적 캘린더 기준  |  주요 기업 실적 발표 일정",
              font=fs, fill=(45, 55, 75))
    draw.text((W - 290, H - 38), "ECONOMY BRIEFING", font=fs, fill=GREEN_DIM)

    os.makedirs("assets", exist_ok=True)
    img.save(CALENDAR_IMG, "JPEG", quality=95)
    print(f"✅ Calendar image saved → {CALENDAR_IMG}", flush=True)


def generate_script_section(earnings):
    """Generate [경제일정] section text for the broadcast script."""
    if not earnings:
        return ""

    today = datetime.now(timezone.utc).date()
    monday = today - timedelta(days=today.weekday())
    friday = monday + timedelta(days=4)

    lines = ["[경제일정]"]
    lines.append(f"이번 주 주요 기업 실적 발표 일정입니다.")

    # Group by date
    by_date = {}
    for e in earnings:
        date = e.get("date", "TBD")
        if date not in by_date:
            by_date[date] = []
        by_date[date].append(e)

    for date_str, day_earnings in sorted(by_date.items()):
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            DAY_KO = {0: "월요일", 1: "화요일", 2: "수요일", 3: "목요일", 4: "금요일"}
            date_label = f"{dt.strftime('%m월 %d일')} {DAY_KO.get(dt.weekday(), '')}"
        except Exception:
            date_label = date_str

        symbols = [e.get("symbol", "?") for e in day_earnings[:8]]
        lines.append(f"{date_label}에는 {', '.join(symbols)} 등의 실적 발표가 예정되어 있습니다.")

    lines.append("투자자 여러분의 일정 관리에 참고하시기 바랍니다.")
    return "\n".join(lines)


def append_to_script(calendar_text):
    """Insert [경제일정] before the closing sentence."""
    if not calendar_text or not os.path.exists(SCRIPT_FILE):
        return

    with open(SCRIPT_FILE, "r", encoding="utf-8") as f:
        script = f.read()

    # Insert before "지금까지" closing
    if "지금까지" in script:
        parts = script.rsplit("지금까지", 1)
        script = parts[0].rstrip() + "\n\n" + calendar_text + "\n\n지금까지" + parts[1]
    else:
        script += "\n\n" + calendar_text

    with open(SCRIPT_FILE, "w", encoding="utf-8") as f:
        f.write(script)

    print(f"✅ [경제일정] appended to {SCRIPT_FILE}", flush=True)


def main():
    print("[Calendar] Fetching earnings calendar...", flush=True)

    all_earnings = fetch_earnings()
    top_earnings = filter_top_earnings(all_earnings)

    # Save data
    os.makedirs("temp", exist_ok=True)
    with open(CALENDAR_JSON, "w", encoding="utf-8") as f:
        json.dump(top_earnings, f, ensure_ascii=False, indent=2)
    print(f"✅ Calendar data saved → {CALENDAR_JSON} ({len(top_earnings)} events)", flush=True)

    # Generate image
    generate_calendar_image(top_earnings)

    # Generate and append script section
    calendar_text = generate_script_section(top_earnings)
    if calendar_text:
        append_to_script(calendar_text)
        print(f"\n{calendar_text}", flush=True)
    else:
        print("⚠️  No earnings to add to script", flush=True)


if __name__ == "__main__":
    main()
