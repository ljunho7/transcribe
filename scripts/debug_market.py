"""
Debug: test investing.com scraping for US 10yr treasury
"""
import requests
from bs4 import BeautifulSoup

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.google.com/",
    "Connection": "keep-alive",
}

url = "https://www.investing.com/rates-bonds/u.s.-10-year-bond-yield"
print(f"Fetching: {url}")

r = requests.get(url, headers=headers, timeout=15)
print(f"Status: {r.status_code}")
print(f"Content-Length: {len(r.text)}")
print(f"First 200 chars: {r.text[:200]}")

soup = BeautifulSoup(r.text, "html.parser")

print("\n--- Trying data-test attributes ---")
for attr in ["instrument-price-last", "instrument-price-change", "instrument-price-change-percent"]:
    el = soup.find(attrs={"data-test": attr})
    print(f"  {attr}: {el.text.strip() if el else 'NOT FOUND'}")

print("\n--- Trying common class names ---")
for cls in ["last-price-value", "text-2xl", "price"]:
    els = soup.find_all(class_=lambda c: c and cls in c)
    for el in els[:3]:
        print(f"  class~={cls}: '{el.text.strip()}'")

print("\n--- All text around '4.3' or '4.4' (likely yield) ---")
text = soup.get_text()
import re
matches = re.findall(r'.{30}4\.[23]\d{1,2}.{30}', text)
for m in matches[:5]:
    print(f"  {m.strip()}")

print("\n--- Raw title/meta for confirmation ---")
title = soup.find("title")
print(f"  Page title: {title.text.strip() if title else 'N/A'}")

print("\nDone.")
