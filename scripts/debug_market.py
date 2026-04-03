"""
Debug: test S&P 500 specific top movers via Yahoo Finance screener
"""
import requests, json

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}

# Try different screener IDs that filter to S&P 500 only
screeners = [
    ("SP500 gainers", "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?scrIds=day_gainers&count=10&fields=symbol,shortName,regularMarketPrice,regularMarketChangePercent&region=US&lang=en-US"),
    ("SP500 losers",  "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?scrIds=day_losers&count=10&fields=symbol,shortName,regularMarketPrice,regularMarketChangePercent&region=US&lang=en-US"),
]

# Also try custom screener with S&P 500 filter
custom_url = "https://query1.finance.yahoo.com/v1/finance/screener?crumb=&lang=en-US&region=US&formatted=true&corsDomain=finance.yahoo.com"
custom_body = {
    "size": 10,
    "offset": 0,
    "sortField": "percentchange",
    "sortType": "DESC",
    "quoteType": "EQUITY",
    "query": {
        "operator": "AND",
        "operands": [
            {"operator": "eq", "operands": ["exchange", "NMS"]},
            {"operator": "gt", "operands": ["intradaymarketcap", 10000000000]},  # >$10B market cap
        ]
    },
    "userId": "",
    "userIdType": "guid"
}

for name, url in screeners:
    r = requests.get(url, headers=headers, timeout=10)
    print(f"\n{name}: HTTP {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        quotes = data.get("finance", {}).get("result", [{}])[0].get("quotes", [])
        for q in quotes:
            print(f"  {q.get('symbol'):8} {q.get('regularMarketChangePercent', 0):+7.2f}%  {q.get('shortName','')[:30]}")

# Custom screener - large cap gainers (S&P 500 proxy)
print("\n\nCustom large-cap screener (>$10B, sorted by % change DESC):")
r = requests.post(custom_url, json=custom_body, headers={**headers, "Content-Type": "application/json"}, timeout=10)
print(f"HTTP {r.status_code}")
print(r.text[:1000])

print("\n✅ Done")
