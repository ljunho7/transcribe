"""
Debug: test fetching S&P 500 top movers (gainers + losers) by daily % change.
No try/except so all errors visible.
"""
import requests

print("=" * 60)
print("METHOD 1: Yahoo Finance Screener API")
print("=" * 60)

# Yahoo Finance has screener endpoints used by their website
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}

# Top gainers in S&P 500
url = "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?scrIds=day_gainers&count=10&fields=symbol,shortName,regularMarketPrice,regularMarketChangePercent"
r = requests.get(url, headers=headers, timeout=10)
print(f"Gainers status: {r.status_code}")
if r.status_code == 200:
    data = r.json()
    quotes = data.get("finance", {}).get("result", [{}])[0].get("quotes", [])
    print(f"Found {len(quotes)} gainers:")
    for q in quotes[:5]:
        print(f"  {q.get('symbol')}: {q.get('regularMarketChangePercent', 0):+.2f}% — {q.get('shortName', '')}")
else:
    print(r.text[:500])

print()

# Top losers
url2 = "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?scrIds=day_losers&count=10&fields=symbol,shortName,regularMarketPrice,regularMarketChangePercent"
r2 = requests.get(url2, headers=headers, timeout=10)
print(f"Losers status: {r2.status_code}")
if r2.status_code == 200:
    data2 = r2.json()
    quotes2 = data2.get("finance", {}).get("result", [{}])[0].get("quotes", [])
    print(f"Found {len(quotes2)} losers:")
    for q in quotes2[:5]:
        print(f"  {q.get('symbol')}: {q.get('regularMarketChangePercent', 0):+.2f}% — {q.get('shortName', '')}")
else:
    print(r2.text[:500])

print()
print("=" * 60)
print("METHOD 2: yfinance download all S&P 500 tickers")
print("=" * 60)

import yfinance as yf
import pandas as pd

# Get S&P 500 tickers from Wikipedia
table = pd.read_html("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")
tickers = table[0]["Symbol"].tolist()[:50]  # Test with first 50 only
print(f"Fetched {len(tickers)} tickers from Wikipedia")

data = yf.download(tickers, period="2d", auto_adjust=True, progress=False)
closes = data["Close"]
changes = closes.pct_change().iloc[-1] * 100
changes = changes.dropna().sort_values()

print("\nTop 5 losers:")
for sym, chg in changes.head(5).items():
    print(f"  {sym}: {chg:+.2f}%")

print("\nTop 5 gainers:")
for sym, chg in changes.tail(5).iloc[::-1].items():
    print(f"  {sym}: {chg:+.2f}%")

print("\n✅ Done")
