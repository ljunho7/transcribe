"""
Debug script — run manually on GitHub Actions to test market data.
No try/except so all errors are fully visible.
"""
import yfinance as yf

print("=" * 60)
print("TESTING EQUITY + FX + CRYPTO  (period=2d)")
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
]:
    h = yf.Ticker(sym).history(period="2d")
    print(f"\n{name} ({sym}): {len(h)} rows")
    if len(h) >= 2:
        prev, curr = h["Close"].iloc[-2], h["Close"].iloc[-1]
        print(f"  prev={prev:.4f}, curr={curr:.4f}, chg={((curr-prev)/prev*100):+.2f}%")
    elif len(h) == 1:
        print(f"  Only 1 row: {h['Close'].iloc[-1]:.4f}")
    else:
        print("  NO DATA")

print("\n" + "=" * 60)
print("TESTING RATES  (period=5d)")
print("=" * 60)

for name, sym in [
    ("10yr ^TNX",       "^TNX"),
    ("30yr ^TYX",       "^TYX"),
    ("13-week ^IRX",    "^IRX"),
]:
    h = yf.Ticker(sym).history(period="5d")
    print(f"\n{name} ({sym}): {len(h)} rows")
    print(f"  All closes: {list(h['Close'].round(4))}")
    if len(h) >= 2:
        prev, curr = h["Close"].iloc[-2], h["Close"].iloc[-1]
        bp = (curr - prev) * 100
        print(f"  prev={prev:.4f}, curr={curr:.4f}, bp_chg={bp:+.1f}bp")
    else:
        print("  NOT ENOUGH ROWS FOR BP CALC")

print("\n✅ Debug complete")
