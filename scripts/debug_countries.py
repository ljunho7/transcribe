"""
Debug: test all single-country ETFs, use t.info["totalAssets"] for AUM.
Filter by AUM > $100M.
"""
import yfinance as yf

ALL_ETFS = [
    # Americas
    ("SPY",  "미국",       "USA",          "USA", "SPDR",     "DM"),
    ("EWC",  "캐나다",     "Canada",       "CAN", "iShares",  "DM"),
    ("EWW",  "멕시코",     "Mexico",       "MEX", "iShares",  "EM"),
    ("ARGT", "아르헨티나", "Argentina",    "ARG", "GlobalX",  "EM"),
    ("EWZ",  "브라질",     "Brazil",       "BRA", "iShares",  "EM"),
    ("ECH",  "칠레",       "Chile",        "CHL", "iShares",  "EM"),
    ("EPU",  "페루",       "Peru",         "PER", "iShares",  "EM"),
    ("GXG",  "콜롬비아",   "Colombia",     "COL", "GlobalX",  "EM"),
    # Europe DM
    ("EWU",  "영국",       "UK",           "GBR", "iShares",  "DM"),
    ("EWG",  "독일",       "Germany",      "DEU", "iShares",  "DM"),
    ("EWQ",  "프랑스",     "France",       "FRA", "iShares",  "DM"),
    ("EWL",  "스위스",     "Switzerland",  "CHE", "iShares",  "DM"),
    ("EWN",  "네덜란드",   "Netherlands",  "NLD", "iShares",  "DM"),
    ("EWI",  "이탈리아",   "Italy",        "ITA", "iShares",  "DM"),
    ("EWP",  "스페인",     "Spain",        "ESP", "iShares",  "DM"),
    ("EWD",  "스웨덴",     "Sweden",       "SWE", "iShares",  "DM"),
    ("ENOR", "노르웨이",   "Norway",       "NOR", "iShares",  "DM"),
    ("EDEN", "덴마크",     "Denmark",      "DNK", "iShares",  "DM"),
    ("EWK",  "벨기에",     "Belgium",      "BEL", "iShares",  "DM"),
    ("EWO",  "오스트리아", "Austria",      "AUT", "iShares",  "DM"),
    ("EFNL", "핀란드",     "Finland",      "FIN", "iShares",  "DM"),
    ("EPOL", "폴란드",     "Poland",       "POL", "iShares",  "EM"),
    ("GREK", "그리스",     "Greece",       "GRC", "GlobalX",  "EM"),
    ("TUR",  "터키",       "Turkey",       "TUR", "iShares",  "EM"),
    # Middle East
    ("EIS",  "이스라엘",   "Israel",       "ISR", "iShares",  "DM"),
    ("KSA",  "사우디",     "Saudi Arabia", "SAU", "iShares",  "EM"),
    ("UAE",  "UAE",        "UAE",          "ARE", "iShares",  "EM"),
    ("QAT",  "카타르",     "Qatar",        "QAT", "iShares",  "EM"),
    ("KWT",  "쿠웨이트",   "Kuwait",       "KWT", "iShares",  "EM"),
    # Africa
    ("EZA",  "남아공",     "S.Africa",     "ZAF", "iShares",  "EM"),
    ("EGPT", "이집트",     "Egypt",        "EGY", "VanEck",   "EM"),
    # Asia Pacific DM
    ("EWJ",  "일본",       "Japan",        "JPN", "iShares",  "DM"),
    ("EWA",  "호주",       "Australia",    "AUS", "iShares",  "DM"),
    ("EWS",  "싱가포르",   "Singapore",    "SGP", "iShares",  "DM"),
    ("EWH",  "홍콩",       "Hong Kong",    "HKG", "iShares",  "DM"),
    ("ENZL", "뉴질랜드",   "New Zealand",  "NZL", "iShares",  "DM"),
    # Asia EM
    ("MCHI", "중국",       "China",        "CHN", "iShares",  "EM"),
    ("FXI",  "중국(대형)", "China Large",  "CHN", "iShares",  "EM"),
    ("INDA", "인도",       "India",        "IND", "iShares",  "EM"),
    ("EWT",  "대만",       "Taiwan",       "TWN", "iShares",  "EM"),
    ("EWY",  "한국",       "S.Korea",      "KOR", "iShares",  "EM"),
    ("EWM",  "말레이시아", "Malaysia",     "MYS", "iShares",  "EM"),
    ("THD",  "태국",       "Thailand",     "THA", "iShares",  "EM"),
    ("EPHE", "필리핀",     "Philippines",  "PHL", "iShares",  "EM"),
    ("EIDO", "인도네시아", "Indonesia",    "IDN", "iShares",  "EM"),
    ("VNM",  "베트남",     "Vietnam",      "VNM", "VanEck",   "EM"),
    # Franklin FTSE
    ("FLKR", "한국(FR)",   "Korea(FR)",    "KOR", "Franklin", "EM"),
    ("FLIN", "인도(FR)",   "India(FR)",    "IND", "Franklin", "EM"),
    ("FLTW", "대만(FR)",   "Taiwan(FR)",   "TWN", "Franklin", "EM"),
    ("FLGB", "영국(FR)",   "UK(FR)",       "GBR", "Franklin", "DM"),
    ("FLGR", "독일(FR)",   "Germany(FR)",  "DEU", "Franklin", "DM"),
    ("FLCA", "캐나다(FR)", "Canada(FR)",   "CAN", "Franklin", "DM"),
    ("FLAU", "호주(FR)",   "Australia(FR)","AUS", "Franklin", "DM"),
    ("FLCH", "중국(FR)",   "China(FR)",    "CHN", "Franklin", "EM"),
    ("FLJP", "일본(FR)",   "Japan(FR)",    "JPN", "Franklin", "DM"),
    ("FLBR", "브라질(FR)", "Brazil(FR)",   "BRA", "Franklin", "EM"),
    ("FLMX", "멕시코(FR)", "Mexico(FR)",   "MEX", "Franklin", "EM"),
    ("FLSW", "스위스(FR)", "Switz(FR)",    "CHE", "Franklin", "DM"),
    ("FLSG", "싱가포르(FR)","Singapore(FR)","SGP","Franklin", "DM"),
]

tickers = [e[0] for e in ALL_ETFS]
print(f"Testing {len(tickers)} ETFs...")

# Batch download prices
data = yf.download(tickers, period="5d", auto_adjust=True,
                   progress=False, group_by="ticker")

print(f"\n{'Ticker':8} {'Country':16} {'Provider':10} {'Reg':3} {'Price':>8} {'Chg%':>7} {'AUM $M':>10}  Status")
print("-" * 80)

results = {}
for ticker, ko, en, iso, provider, region in ALL_ETFS:
    try:
        closes = data[ticker]["Close"].dropna()
        if len(closes) < 2:
            print(f"{ticker:8} {en:16} {provider:10} {region:3} {'—':>8} {'—':>7} {'no data':>10}")
            continue
        price = float(closes.iloc[-1])
        chg   = float((closes.iloc[-1] - closes.iloc[-2]) / closes.iloc[-2] * 100)

        # Use totalAssets for ETF AUM
        try:
            info = yf.Ticker(ticker).info
            aum  = info.get("totalAssets", 0) or 0
        except Exception:
            aum = 0
        aum_m = aum / 1e6

        ok = aum_m >= 100
        status = "✅" if ok else f"❌ ${aum_m:,.0f}M"
        print(f"{ticker:8} {en:16} {provider:10} {region:3} ${price:>7.2f} {chg:>+6.2f}% ${aum_m:>8,.0f}M  {status}")
        if ok:
            results[ticker] = {"ko":ko,"en":en,"iso":iso,"region":region,
                               "provider":provider,"price":price,"chg":chg,"aum_m":aum_m}
    except Exception as e:
        print(f"{ticker:8} {en:16} ERROR: {e}")

print(f"\n{'='*80}")
print(f"✅ {len(results)} ETFs with AUM ≥ $100M:")
for t, v in sorted(results.items(), key=lambda x: -x[1]["aum_m"]):
    print(f"  {t:8} {v['en']:20} {v['region']:4} AUM=${v['aum_m']:,.0f}M  chg={v['chg']:+.2f}%")
