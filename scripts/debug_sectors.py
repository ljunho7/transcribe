"""
Debug: test fetching S&P 500 sector data with GICS sector + daily returns
"""
import requests
import yfinance as yf

print("=" * 60)
print("FETCHING S&P 500 WITH GICS SECTORS FROM GITHUB")
print("=" * 60)

url = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"
r = requests.get(url, timeout=10)
lines = r.text.strip().splitlines()
headers = lines[0].split(",")
print(f"CSV columns: {headers}")

rows = []
for l in lines[1:]:
    parts = l.split(",")
    if len(parts) >= 3:
        rows.append({
            "symbol": parts[0].replace(".", "-"),
            "name":   parts[1],
            "sector": parts[2] if len(parts) > 2 else "Unknown"
        })

# Show unique sectors
sectors = sorted(set(r["sector"] for r in rows))
print(f"\nFound {len(rows)} stocks across {len(sectors)} sectors:")
for s in sectors:
    count = sum(1 for r in rows if r["sector"] == s)
    print(f"  {s}: {count} stocks")

print("\n" + "=" * 60)
print("FETCHING SECTOR ETF RETURNS (FAST PROXY)")
print("=" * 60)

# SPDR sector ETFs are a fast proxy for GICS sector returns
sector_etfs = {
    "XLB":  "소재 (Materials)",
    "XLC":  "통신 (Comm. Services)",
    "XLE":  "에너지 (Energy)",
    "XLF":  "금융 (Financials)",
    "XLI":  "산업재 (Industrials)",
    "XLK":  "IT (Technology)",
    "XLP":  "필수소비재 (Cons. Staples)",
    "XLRE": "부동산 (Real Estate)",
    "XLU":  "유틸리티 (Utilities)",
    "XLV":  "헬스케어 (Health Care)",
    "XLY":  "임의소비재 (Cons. Discret.)",
}

import pandas as pd
tickers = list(sector_etfs.keys())
data = yf.download(tickers, period="2d", auto_adjust=True, progress=False, group_by="ticker")

print(f"\nSector ETF daily returns:")
results = {}
for etf, label in sector_etfs.items():
    try:
        closes = data[etf]["Close"].dropna()
        if len(closes) >= 2:
            chg = (closes.iloc[-1] - closes.iloc[-2]) / closes.iloc[-2] * 100
            results[label] = (etf, closes.iloc[-1], chg)
            print(f"  {etf} {label}: {chg:+.2f}%  ${closes.iloc[-1]:.2f}")
    except Exception as e:
        print(f"  {etf}: FAILED — {e}")

print("\n✅ Done")
