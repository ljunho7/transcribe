"""
Debug: fetch S&P 500 tickers from GitHub (reliable, no auth),
then get top movers via yfinance batch download.
"""
import requests
import yfinance as yf

print("=" * 60)
print("FETCHING S&P 500 TICKERS FROM GITHUB")
print("=" * 60)

# datahub.io hosts a clean S&P 500 CSV updated regularly
url = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"
r = requests.get(url, timeout=10)
print(f"Status: {r.status_code}")
lines = r.text.strip().split("\n")[1:]  # skip header
tickers = [l.split(",")[0].replace(".", "-") for l in lines]
print(f"Tickers: {len(tickers)} found")
print(f"Sample: {tickers[:10]}")

print("\n" + "=" * 60)
print("FETCHING TOP MOVERS VIA YFINANCE BATCH")
print("=" * 60)

# Download all S&P 500 in one batch call - much faster than one by one
import pandas as pd
data = yf.download(tickers, period="2d", auto_adjust=True, progress=False, group_by="ticker")

# Calculate % change for each ticker
changes = {}
for sym in tickers:
    try:
        if sym in data.columns.get_level_values(0):
            closes = data[sym]["Close"].dropna()
            if len(closes) >= 2:
                chg = (closes.iloc[-1] - closes.iloc[-2]) / closes.iloc[-2] * 100
                name = sym
                changes[sym] = (closes.iloc[-1], chg)
    except Exception:
        pass

print(f"Got data for {len(changes)} tickers")

sorted_chg = sorted(changes.items(), key=lambda x: x[1][1])

print("\nTop 10 Losers:")
for sym, (price, chg) in sorted_chg[:10]:
    print(f"  {sym:8} {chg:+.2f}%  ${price:.2f}")

print("\nTop 10 Gainers:")
for sym, (price, chg) in sorted_chg[-10:][::-1]:
    print(f"  {sym:8} {chg:+.2f}%  ${price:.2f}")

print("\n✅ Done")
