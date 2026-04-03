"""
Debug script — run manually on GitHub Actions to test market data fetch.
No try/except so errors are fully visible.
Run with: python -u scripts/debug_market.py
"""

import requests
import yfinance as yf

print("=" * 60)
print("TESTING FRED")
print("=" * 60)

for name, series in [("10yr", "DGS10"), ("30yr", "DGS30"), ("Fed Funds", "DFEDTARU")]:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"
    r = requests.get(url, timeout=10)
    print(f"\n{name} ({series}): HTTP {r.status_code}")
    lines = [l for l in r.text.strip().split("\n") if "." in l.split(",")[-1]]
    print(f"  Last 2 rows: {lines[-2:]}")
    prev = float(lines[-2].split(",")[1])
    curr = float(lines[-1].split(",")[1])
    bp   = (curr - prev) * 100
    print(f"  curr={curr}, prev={prev}, change={bp:.1f}bp")

print("\n" + "=" * 60)
print("TESTING YFINANCE")
print("=" * 60)

for name, sym in [
    ("S&P 500",    "^GSPC"),
    ("NASDAQ",     "^IXIC"),
    ("DOW",        "^DJI"),
    ("SOX",        "^SOX"),
    ("USD/KRW",    "KRW=X"),
    ("EUR/USD",    "EURUSD=X"),
    ("DXY",        "DX-Y.NYB"),
    ("BTC",        "BTC-USD"),
    ("10yr ^TNX",  "^TNX"),
    ("30yr ^TYX",  "^TYX"),
]:
    h = yf.Ticker(sym).history(period="2d")
    print(f"\n{name} ({sym}): {len(h)} rows")
    if len(h) >= 2:
        prev = h["Close"].iloc[-2]
        curr = h["Close"].iloc[-1]
        pct  = (curr - prev) / prev * 100
        print(f"  prev={prev:.4f}, curr={curr:.4f}, chg={pct:+.2f}%")
    elif len(h) == 1:
        print(f"  Only 1 row: {h['Close'].iloc[-1]:.4f}")
    else:
        print("  NO DATA RETURNED")

print("\n✅ Debug complete")
