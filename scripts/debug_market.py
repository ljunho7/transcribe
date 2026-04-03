"""
Debug: test FRED rates fetch only, no try/except
"""
import requests

print("=" * 60)
print("TESTING FRED RATES")
print("=" * 60)

for label, series in [
    ("미국 2년물",   "DGS2"),
    ("미국 5년물",   "DGS5"),
    ("미국 10년물",  "DGS10"),
    ("미국 30년물",  "DGS30"),
    ("연방기금금리", "DFEDTARU"),
]:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"
    print(f"\n{label} ({series})")
    print(f"  URL: {url}")
    r = requests.get(url, timeout=10)
    print(f"  HTTP: {r.status_code}")
    lines = r.text.strip().split("\n")
    print(f"  Total rows: {len(lines)}")
    print(f"  Last 3 rows: {lines[-3:]}")
    valid = [l for l in lines if "," in l and l.split(",")[1].strip() not in ("", ".")]
    print(f"  Valid rows: {len(valid)}")
    if len(valid) >= 2:
        curr = float(valid[-1].split(",")[1])
        prev = float(valid[-2].split(",")[1])
        bp   = (curr - prev) * 100
        print(f"  curr={curr}, prev={prev}, bp={bp:+.1f}")
    else:
        print("  NOT ENOUGH VALID ROWS")

print("\n✅ Done")
