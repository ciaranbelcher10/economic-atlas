#!/usr/bin/env python3
"""
generate_indicator_pages.py

Generates, from the live data-*.json files:
    /indicators/{country}-{metric}.html   one landing page per country x metric
                                          (every metric the site serves that has
                                          a source citation on file)
    /embed/{country}-{metric}.html        matching embeddable widget
    /rankings/{metric}-by-country.html    one cross-country ranking per
                                          comparable metric
    sitemap.xml                           the /indicators/ and /rankings/ entries
                                          are rewritten in place; every other
                                          entry is left exactly as it was

Runs hourly in update-data.yml after the fetch step, so baked figures never
drift far from the data; the indicator pages also refresh themselves from the
data file in the browser.

Every number these pages print goes through ONE formatter: fmt_num() here
(for baked HTML) and fmtNum() in /indicator-kit.js (in the browser). They are
line-for-line ports of each other; tools/test_indicator_fmt.js checks that
they agree for every country x metric pair. Rules match the country pages'
curFmt(): % at 1dp (policy rates and bond yields 2dp), index at 1dp, currency
folded to tn/bn/m with its real symbol (ISO code where the unit has no glyph,
A$/R$/C$/MX$/R on GDP for the five non-US dollar-glyph currencies).

A country/metric pair is skipped, never padded, when the series is missing,
has fewer than two readings, or has no source citation in
data-metric-sources.json.
"""
import json, os, re, html as htmllib
from decimal import Decimal, ROUND_HALF_UP
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.abspath(__file__))
SITE_URL = "https://theeconomicatlas.com"
KIT_VERSION = "4"

# country display name -> (data-file code, page slug, alpha-2, region)
COUNTRIES = {
    "UK":            ("uk", "uk", "GB", "Europe"),
    "US":            ("us", "us", "US", "North America"),
    "Argentina":     ("ar", "argentina", "AR", "South America"),
    "Australia":     ("au", "australia", "AU", "Oceania"),
    "Austria":       ("at", "austria", "AT", "Europe"),
    "Brazil":        ("br", "brazil", "BR", "South America"),
    "Canada":        ("ca", "canada", "CA", "North America"),
    "Chile":         ("cl", "chile", "CL", "South America"),
    "Colombia":      ("co", "colombia", "CO", "South America"),
    "Denmark":       ("dk", "denmark", "DK", "Scandinavia"),
    "Eurozone":      ("ez", "eurozone", "EU", "Europe"),
    "France":        ("fr", "france", "FR", "Europe"),
    "Germany":       ("de", "germany", "DE", "Europe"),
    "India":         ("in", "india", "IN", "Asia"),
    "Indonesia":     ("id", "indonesia", "ID", "Asia"),
    "Ireland":       ("ie", "ireland", "IE", "Europe"),
    "Israel":        ("il", "israel", "IL", "Middle East"),
    "Italy":         ("it", "italy", "IT", "Europe"),
    "Japan":         ("jp", "japan", "JP", "Asia"),
    "Mexico":        ("mx", "mexico", "MX", "North America"),
    "Morocco":       ("ma", "morocco", "MA", "Africa"),
    "Netherlands":   ("nl", "netherlands", "NL", "Europe"),
    "Norway":        ("no", "norway", "NO", "Scandinavia"),
    "Poland":        ("pl", "poland", "PL", "Europe"),
    "Singapore":     ("sg", "singapore", "SG", "Asia"),
    "South Africa":  ("za", "southafrica", "ZA", "Africa"),
    "South Korea":   ("kr", "southkorea", "KR", "Asia"),
    "Spain":         ("es", "spain", "ES", "Europe"),
    "Sweden":        ("se", "sweden", "SE", "Scandinavia"),
    "Switzerland":   ("ch", "switzerland", "CH", "Europe"),
    "Thailand":      ("th", "thailand", "TH", "Asia"),
    "Turkey":        ("tr", "turkey", "TR", "Europe"),
}

CATEGORIES = ["GDP & growth", "Prices", "Labour market", "Interest rates", "Trade", "Public finances", "Business"]

# One entry per indicator PAGE. "keys" lists the data keys that can feed it, in
# priority order (e.g. five differently-named central bank rates all feed
# "interest-rate"); the first key a country serves wins.
#   up:    True when a rise is favourable (colours the delta, as statTile does)
#   chart: "line" or "bar" (bar for changes and flows that swing through zero)
#   ann:   trailing four-quarter sum, as the country pages' annualGDP()
METRICS = [
    dict(slug="gdp", keys=["gdp_level"], title="GDP", cat="GDP & growth", up=True, chart="line", ann=True),
    dict(slug="real-gdp", keys=["gdp_real"], title="Real GDP", cat="GDP & growth", up=True, chart="line", ann=True),
    dict(slug="gdp-growth-rate", keys=["gdp_growth"], title="GDP Growth Rate", cat="GDP & growth", up=True, chart="bar"),
    dict(slug="gdp-annual-growth-rate", keys=["gdp_growth_yoy"], title="GDP Annual Growth Rate", cat="GDP & growth", up=True, chart="bar"),
    dict(slug="productivity", keys=["productivity"], title="Productivity", cat="GDP & growth", up=True, chart="line"),
    dict(slug="inflation-rate", keys=["cpi"], title="Inflation Rate", cat="Prices", up=False, chart="line"),
    dict(slug="inflation-rate-mom", keys=["cpi_mom"], title="Inflation Rate, Month on Month", cat="Prices", up=False, chart="bar"),
    dict(slug="inflation-rate-mom-seasonally-adjusted", keys=["cpi_mom_sa"], title="Inflation Rate, Month on Month (Seasonally Adjusted)", cat="Prices", up=False, chart="bar"),
    dict(slug="inflation-rate-qoq", keys=["cpi_qoq"], title="Inflation Rate, Quarter on Quarter", cat="Prices", up=False, chart="bar"),
    dict(slug="inflation-rate-national-definition", keys=["cpi_national"], title="Inflation Rate (National Definition)", cat="Prices", up=False, chart="line"),
    dict(slug="core-inflation-rate", keys=["core_cpi"], title="Core Inflation Rate", cat="Prices", up=False, chart="line"),
    dict(slug="cpih-inflation-rate", keys=["cpih"], title="CPIH Inflation Rate", cat="Prices", up=False, chart="line"),
    dict(slug="cpih-inflation-rate-mom", keys=["cpih_mom"], title="CPIH Inflation Rate, Month on Month", cat="Prices", up=False, chart="bar"),
    dict(slug="pce-inflation-rate", keys=["pce"], title="PCE Inflation Rate", cat="Prices", up=False, chart="line"),
    dict(slug="producer-price-inflation", keys=["ppi"], title="Producer Price Inflation", cat="Prices", up=False, chart="line"),
    dict(slug="unemployment-rate", keys=["unemployment"], title="Unemployment Rate", cat="Labour market", up=False, chart="line"),
    dict(slug="youth-unemployment-rate", keys=["unemployment_1624"], title="Youth Unemployment Rate", cat="Labour market", up=False, chart="line"),
    dict(slug="employment-rate", keys=["employment_rate", "employment"], title="Employment Rate", cat="Labour market", up=True, chart="line"),
    dict(slug="labour-force-participation-rate", keys=["participation_rate", "participation"], title="Labour Force Participation Rate", cat="Labour market", up=True, chart="line"),
    dict(slug="economic-inactivity-rate", keys=["inactivity"], title="Economic Inactivity Rate", cat="Labour market", up=False, chart="line"),
    dict(slug="interest-rate", keys=["boe_rate", "fed_funds", "ecb_rate", "boj_rate", "overnight_rate"], title="Interest Rate", cat="Interest rates", up=False, chart="line"),
    dict(slug="10-year-government-bond-yield", keys=["bond_yield_10y"], title="10-Year Government Bond Yield", cat="Interest rates", up=False, chart="line"),
    dict(slug="balance-of-trade", keys=["trade_balance"], title="Balance of Trade", cat="Trade", up=True, chart="bar"),
    dict(slug="exports", keys=["exports"], title="Exports", cat="Trade", up=True, chart="line"),
    dict(slug="imports", keys=["imports"], title="Imports", cat="Trade", up=False, chart="line"),
    dict(slug="current-account-to-gdp", keys=["current_account"], title="Current Account (% of GDP)", cat="Trade", up=True, chart="bar"),
    dict(slug="foreign-direct-investment", keys=["fdi"], title="Foreign Direct Investment (% of GDP)", cat="Trade", up=True, chart="line"),
    dict(slug="government-debt", keys=["debt_gdp"], title="Government Debt (% of GDP)", cat="Public finances", up=False, chart="line"),
    dict(slug="government-net-debt", keys=["net_debt"], title="Government Net Debt", cat="Public finances", up=False, chart="line"),
    dict(slug="government-budget", keys=["deficit"], title="Government Budget Balance", cat="Public finances", up=True, chart="bar"),
    dict(slug="government-debt-interest", keys=["debt_interest"], title="Government Debt Interest", cat="Public finances", up=False, chart="bar"),
    dict(slug="business-confidence", keys=["business_confidence"], title="Business Confidence", cat="Business", up=True, chart="line"),
]
METRIC_BY_SLUG = {m["slug"]: m for m in METRICS}

# The site's budget series come on two sign conventions: a balance (% of GDP,
# negative = deficit, and the US federal series) and the UK's net borrowing
# (positive = borrowing). The title and the favourable direction follow the
# series actually served, never one assumed for all.
def metric_title(m, country, key, unit):
    if m["slug"] == "government-budget":
        if "%" in unit:
            return "Government Budget Balance (% of GDP)"
        if country == "UK":
            return "Government Borrowing"
        return "Federal Budget Balance" if country == "US" else "Government Budget Balance"
    return m["title"]

def metric_up(m, country, unit):
    if m["slug"] == "government-budget" and country == "UK" and "%" not in unit:
        return False
    return m["up"]

# Kept for generate_og_images.py and anything else importing the old name.
CORE_METRICS = {m["keys"][0]: (m["slug"], m["title"]) for m in METRICS}

# Cross-country rankings. Only metrics measured the same way everywhere they
# appear: shares of GDP, rates, the OECD confidence index, and GDP itself once
# converted to US dollars. "freqs" restricts the ranking to one basis where
# countries publish on different ones (a quarter-on-quarter growth rate is
# not comparable with an annual one); rows on another basis are listed below
# the table as not ranked, with the reason, rather than silently dropped.
RANKINGS = [
    dict(slug="gdp-by-country", metric="gdp", title="GDP by Country", col="GDP (US$)", usd=True, flow=True,
         lede="The size of every economy we track over the last completed year, converted to US dollars at that year's average exchange rate."),
    dict(slug="gdp-growth-rate-by-country", metric="gdp-growth-rate", title="GDP Growth Rate by Country", col="Growth, quarter on quarter", freqs=["quarters"], flow=True,
         lede="How fast each economy grew or shrank in the final quarter of the last completed year, compared with the quarter before."),
    dict(slug="inflation-rate-by-country", metric="inflation-rate", title="Inflation Rate by Country", col="Inflation, year on year",
         lede="How fast consumer prices are rising in each economy, compared with a year earlier, on each country's headline measure."),
    dict(slug="unemployment-rate-by-country", metric="unemployment-rate", title="Unemployment Rate by Country", col="Unemployment rate",
         lede="The share of people who want a job but can't find one, in each economy's latest release."),
    dict(slug="interest-rate-by-country", metric="interest-rate", title="Interest Rate by Country", col="Policy rate",
         lede="Central bank policy rates, the anchor for borrowing costs, for every economy where we carry the series. Euro area members share the ECB's rate."),
    dict(slug="10-year-government-bond-yield-by-country", metric="10-year-government-bond-yield", title="10-Year Government Bond Yield by Country", col="10-year yield",
         lede="What each government pays to borrow for ten years, the market's gauge of inflation and interest rate expectations."),
    dict(slug="government-debt-by-country", metric="government-debt", title="Government Debt to GDP by Country", col="Debt, % of GDP",
         lede="Everything each government owes, compared with the size of its economy."),
    dict(slug="government-budget-by-country", metric="government-budget", title="Government Budget Balance by Country", col="Balance, % of GDP", units=["%"], freqs=["years"], flow=True,
         lede="Each government's budget surplus or deficit for its latest full year, as a share of GDP. Below zero is a deficit."),
    dict(slug="current-account-by-country", metric="current-account-to-gdp", title="Current Account to GDP by Country", col="Current account, % of GDP", freqs=["years"], flow=True,
         lede="Each economy's overall balance with the rest of the world, trade plus investment income, as a share of GDP."),
    dict(slug="foreign-direct-investment-by-country", metric="foreign-direct-investment", title="Foreign Direct Investment by Country", col="FDI inflows, % of GDP", freqs=["years"], flow=True,
         lede="Money invested into each economy's businesses from abroad, as a share of GDP."),
    dict(slug="business-confidence-by-country", metric="business-confidence", title="Business Confidence by Country", col="Index (average = 100)",
         lede="The OECD's survey measure of how optimistic firms are. 100 is each country's long-run average."),
]
RANKING_BY_METRIC = {r["metric"]: r for r in RANKINGS}
# Flow rankings (flow=True) show the last completed calendar year only,
# the same rule Compare applies: a flow for a year that has not ended is a
# part-year total and is never shown. Every figure is a published
# observation for that year (or, for GDP, the year's published quarters
# added together, the way an annual GDP figure is itself built). Stock and
# rate rankings show each country's latest published reading.
def flow_year():
    return date.today().year - 1

def short_source(text):
    """(publisher, series) for the ranking table's Source column, taken from
    the same citation string shown under each country's chart."""
    head = re.sub(r"^Calculated from\s+", "", (text or "").split(" \u00b7 ")[0]).strip()
    rest = text or ""
    m = re.match(r"^FRED series\s+(\S+)", head)
    if m:
        for agency in ("IMF", "Eurostat", "OECD", "BLS", "BEA", "Cabinet Office", "ECB", "BIS", "World Bank"):
            if agency in rest:
                return f"{agency} via FRED", m.group(1)
        return "FRED", m.group(1)
    m = re.match(r"^(World Bank|Eurostat|OECD|ONS|IMF)\s+(?:series\s+)?(\S+)", head)
    if m:
        return m.group(1), m.group(2)
    return head, ""

# Old standalone pages that used to rank here; they now forward to the new ones.
LEGACY_RANKING_REDIRECTS = {
    "gdp-by-country": "gdp-by-country",
    "inflation-by-country": "inflation-rate-by-country",
    "unemployment-by-country": "unemployment-rate-by-country",
}

GDP_RAW_COUNTRIES = {"US", "Japan"}          # already published at an annual rate
GDP_ALREADY_USD = {"US", "Switzerland"}      # no Dollarise; no FX conversion
RATE_KEYS = {"boe_rate", "fed_funds", "ecb_rate", "boj_rate", "overnight_rate", "policy_rate", "bond_yield_10y"}
NATIVE_DOLLAR = {"Australia": "A$", "Brazil": "R$", "Canada": "C$", "Mexico": "MX$", "South Africa": "R"}
NATIVE_KEYS = {"gdp_level", "gdp_real"}
STALE_DAYS = {"months": 75, "quarters": 150, "years": 660}
MONTH_NAMES = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
MINUS = "\u2212"

# ---------------------------------------------------------------------------
# Formatting: Python port of fmtNum() in indicator-kit.js. Keep in step.
# ---------------------------------------------------------------------------
def _clean_unit(u):
    return re.sub(r"\s*\([^)]*\)\s*$", "", str(u or "")).strip()

def unit_kind(u):
    c = _clean_unit(u)
    if "%" in c:
        return "pct"
    if c in ("index", ""):
        return "index"
    return "cur"

def scale_of(u):
    c = _clean_unit(u)
    for suf, m in (("tn", 1e12), ("bn", 1e9), ("m", 1e6), ("k", 1e3)):
        if c.endswith(suf):
            return m
    return 1

def symbol_of(u, key, country, dollarised=False):
    c = _clean_unit(u)
    m = re.match(r"^[^a-zA-Z0-9]+", c)
    if m:
        sym = m.group(0)
    else:
        code = re.match(r"^([A-Z]{3})(tn|bn|m|k)?$", c)
        sym = code.group(1) if code else ""
    if sym == "$" and not dollarised and key in NATIVE_KEYS and country in NATIVE_DOLLAR:
        sym = NATIVE_DOLLAR[country]
    return sym

def _trim(s):
    return re.sub(r"(\.\d*[1-9])0+(?!\d)|\.0+(?!\d)", lambda m: m.group(1) or "", s, count=1)

def _fixed(x, d):
    """JavaScript's Number.prototype.toFixed: round the exact binary value
    half away from zero. Python's format() rounds half to even, which prints
    0.25 as 0.2 where the browser prints 0.3; this keeps the two identical."""
    q = Decimal(1).scaleb(-d)
    return str(Decimal(x).quantize(q, rounding=ROUND_HALF_UP))

def fmt_num(v, unit, key="", country="", mode="value", dollarised=False):
    if v is None:
        return "n/a"
    kind = unit_kind(unit)
    neg = v < 0
    sign = MINUS if neg else ("+" if mode == "delta" and v > 0 else "")
    a = abs(v)
    if kind == "pct":
        dp = 2 if key in RATE_KEYS else 1
        if mode == "axis":
            return (MINUS if neg else "") + _trim(_fixed(a, 2)) + "%"
        if mode == "delta":
            return sign + _fixed(a, dp) + "pp"
        return (MINUS if neg else "") + _fixed(a, dp) + "%"
    if kind == "index":
        if mode == "axis":
            return (MINUS if neg else "") + _trim(_fixed(a, 1))
        if mode == "delta":
            return sign + _fixed(a, 1) + " pts"
        return (MINUS if neg else "") + _fixed(a, 1)
    sym = symbol_of(unit, key, country, dollarised)
    ab = a * scale_of(unit)
    d = 1 if mode in ("axis", "delta") else 2
    if ab >= 1e12:
        out = _fixed(ab / 1e12, d) + "tn"
    elif ab >= 1e9:
        out = _fixed(ab / 1e9, d) + "bn"
    elif ab >= 1e6:
        out = _fixed(ab / 1e6, 0 if ab >= 1e8 else 1) + "m"
    elif ab >= 1e3:
        out = _fixed(ab / 1e3, 0 if ab >= 1e5 else 1) + "k"
    else:
        out = _fixed(ab, 0)
    out = out if mode == "cell" else _trim(out)
    # Economies measured in trillions of a small-unit currency (COP, IDR,
    # KRW, ARS) run past 1,000tn; group the digits so they stay readable.
    out = re.sub(r"^(\d+)", lambda m: f"{int(m.group(1)):,}", out)
    return sign + sym + out

def delta_dp(unit, key):
    k = unit_kind(unit)
    if k == "pct":
        return 2 if key in RATE_KEYS else 1
    if k == "index":
        return 1
    return None

def rounded_delta(d, unit, key):
    dp = delta_dp(unit, key)
    return round(d, dp) if dp is not None else d

def usd_unit(u):
    s = scale_of(u)
    return {1e12: "$tn", 1e9: "$bn", 1e6: "$m", 1e3: "$k"}.get(s, "$")

# Old name, still imported by generate_og_images.py.
def fmt_value(v, unit, key="", country=""):
    return fmt_num(v, unit, key, country, "value")

def fmt_period_label(period):
    period = str(period or "")
    m = re.match(r"^(\d{4})-(\d{2})$", period)
    if m:
        return f"{MONTH_NAMES[int(m.group(2))-1]} {m.group(1)}"
    m = re.match(r"^(\d{4})-Q(\d)$", period)
    if m:
        return f"Q{m.group(2)} {m.group(1)}"
    return period

def iso_period(label):
    """schema.org temporalCoverage wants ISO 8601, which has no quarters."""
    m = re.fullmatch(r"(\d{4})-Q([1-4])", str(label or "").strip())
    if m:
        return "{}-{:02d}".format(m.group(1), (int(m.group(2)) - 1) * 3 + 1)
    return str(label or "").strip()

def period_end_date(period):
    m = re.match(r"^(\d{4})-(\d{2})$", period)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        ny, nmo = (y + 1, 1) if mo == 12 else (y, mo + 1)
        return date(ny, nmo, 1) - timedelta(days=1)
    m = re.match(r"^(\d{4})-Q(\d)$", period)
    if m:
        y, q = int(m.group(1)), int(m.group(2))
        mo = q * 3
        ny, nmo = (y + 1, 1) if mo == 12 else (y, mo + 1)
        return date(ny, nmo, 1) - timedelta(days=1)
    m = re.match(r"^(\d{4})$", period)
    if m:
        return date(int(m.group(1)), 12, 31)
    return date.today()

def is_fresh(period, freq):
    return (date.today() - period_end_date(period)).days <= STALE_DAYS.get(freq, 90)

def annualize_gdp_points(points, freq, country_name):
    if country_name in GDP_RAW_COUNTRIES or freq == "years":
        return points
    out = []
    for i in range(3, len(points)):
        w = points[i-3:i+1]
        if any(p[1] is None for p in w):
            continue
        out.append([points[i][0], sum(p[1] for p in w)])
    return out

def _month_key(p):
    m = re.match(r"^(\d{4})", p)
    if not m:
        return None
    y = int(m.group(1))
    q = re.match(r"^\d{4}-Q([1-4])$", p)
    if q:
        return y * 12 + (int(q.group(1)) - 1) * 3
    mm = re.match(r"^\d{4}-(\d{2})$", p)
    if mm:
        return y * 12 + int(mm.group(1)) - 1
    return y * 12

def rate_for_period(p, hist):
    """Port of the country pages' rateForPeriod()."""
    if not hist:
        return None
    if re.match(r"^\d{4}$", p):
        matches = [h for h in hist if h[0].startswith(p + "-")]
    elif re.match(r"^\d{4}-Q[1-4]$", p):
        y, q = p[:4], int(p[6])
        s = (q - 1) * 3 + 1
        want = {f"{y}-{n:02d}" for n in (s, s + 1, s + 2)}
        matches = [h for h in hist if h[0] in want]
    else:
        matches = [h for h in hist if h[0] == p]
    if matches:
        return sum(h[1] for h in matches) / len(matches)
    k = _month_key(p)
    return min(hist, key=lambda h: abs(_month_key(h[0]) - k))[1]

def to_usd_value(v, period, fx):
    r = rate_for_period(period, fx.get("history")) if fx.get("history") else fx.get("rate")
    if not r:
        return None
    return v * r if fx.get("direction") == "multiply" else v / r

def load_json(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return json.load(f)

def data_file_for(iso2):
    return "data.json" if iso2 == "uk" else f"data-{iso2}.json"

def clean_points(series):
    return [p for p in (series or {}).get("points", []) if p and p[1] is not None]

def resolve(country, series, sources, m):
    """The series behind metric m for one country, or None. Returns
    (key, series, points) with GDP annualised exactly as on the country page."""
    for k in m["keys"]:
        if k in series and k in sources:
            s = series[k]
            pts = clean_points(s)
            if m.get("ann"):
                pts = annualize_gdp_points(pts, s.get("freq", ""), country)
            if len(pts) >= 2:
                return k, s, pts
    return None


HEADER_HTML_BASE = """<script>(function(){
  try{
    var saved = localStorage.getItem("eatlas_theme");
    if(saved === "dark" || (!saved && window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches)){
      document.documentElement.setAttribute("data-theme", "dark");
    }
  }catch(e){}
})();</script>
<nav class="top"><div class="wrap">
 <a class="brand" href="../index"><img src="../logo-64.png" alt="" width="26" height="26" style="display:block;border-radius:50%;background:#fff;padding:1px;">The Economic Atlas</a>
 <button type="button" class="navtoggle" id="navToggle" aria-label="Menu" aria-expanded="false" aria-controls="navLinks">
 <span></span><span></span><span></span>
 </button>
 <div class="navlinks" id="navLinks">
 <div class="dropdown">
 <button type="button" class="dropbtn" id="aboutBtn" aria-haspopup="true" aria-expanded="false">About <span class="caret">&#9662;</span></button>
 <div class="dropdown-panel" id="aboutPanel">
 <div class="dcol">
 <a href="../contact">Contact</a>
 <a href="../methodology">Methodology</a>
 </div>
 </div>
 </div>
 <button type="button" class="authbtn" id="authBtn">Log in</button>
 <button type="button" class="theme-toggle" id="themeToggle" aria-label="Switch to dark mode" title="Switch to dark mode">&#127769;</button>
 </div>
</div></nav>
<nav class="sub"><div class="wrap">
 <div class="dropdown">
 <button type="button" class="dropbtn" id="macroBtn" aria-haspopup="true" aria-expanded="false">Country Breakdowns <span class="caret">&#9662;</span></button>
 <div class="dropdown-panel" id="macroPanel">
 <div class="doverview">
 <a href="../index">Overview</a>
 </div>
 <div class="dcol">
 <p class="dhead">Europe</p>
 <a href="../austria">Austria</a>
 <a href="../eurozone">Eurozone</a>
 <a href="../france">France</a>
 <a href="../germany">Germany</a>
 <a href="../ireland">Ireland</a>
 <a href="../italy">Italy</a>
 <a href="../netherlands">Netherlands</a>
 <a href="../poland">Poland</a>
 <a href="../spain">Spain</a>
 <a href="../switzerland">Switzerland</a>
 <a href="../turkey">Turkey</a>
 <a href="../uk">UK</a>
 </div>
 <div class="dcol">
 <p class="dhead">North America</p>
 <a href="../canada">Canada</a>
 <a href="../mexico">Mexico</a>
 <a href="../us">U.S.</a>
 </div>
 <div class="dcol">
 <p class="dhead">Asia</p>
 <a href="../india">India</a>
 <a href="../indonesia">Indonesia</a>
 <a href="../japan">Japan</a>
 <a href="../singapore">Singapore</a>
 <a href="../southkorea">South Korea</a>
 <a href="../thailand">Thailand</a>
 </div>
 <div class="dcol">
 <p class="dhead">Oceania</p>
 <a href="../australia">Australia</a>
 </div>
 <div class="dcol">
 <p class="dhead">Middle East</p>
 <a href="../israel">Israel</a>
 </div>
 <div class="dcol">
 <p class="dhead">South America</p>
 <a href="../argentina">Argentina</a>
 <a href="../brazil">Brazil</a>
 <a href="../chile">Chile</a>
 <a href="../colombia">Colombia</a>
 </div>
 <div class="dcol">
 <p class="dhead">Africa</p>
 <a href="../morocco">Morocco</a>
 <a href="../southafrica">South Africa</a>
 </div>
 <div class="dcol">
 <p class="dhead">Scandinavia</p>
 <a href="../denmark">Denmark</a>
 <a href="../norway">Norway</a>
 <a href="../sweden">Sweden</a>
 </div>
 </div>
 </div>
 <a class="item" href="../compare">Compare</a>
 <a class="item" href="../rankings">Rankings</a>
 <a class="item" href="../dashboard">My Dashboard</a>
 <a class="item" href="../chartmaker" id="navChartmakerLink">Chartmaker</a>
 <a class="item" href="../calendar" id="navCalendarLink">Calendar</a>
</div></nav>
<script>
(function(){
  // Shared toggle behaviour for any nav dropdown -- originally written
  // just for Country Breakdowns, now reused for About too rather than
  // duplicating the same open/close/outside-click/Escape logic twice.
  function wireDropdown(btnId, panelId){
    var btn = document.getElementById(btnId);
    var panel = document.getElementById(panelId);
    if(!btn || !panel) return;
    function close(){
      panel.classList.remove("open"); btn.classList.remove("open");
      btn.setAttribute("aria-expanded","false");
    }
    btn.addEventListener("click", function(e){
      e.stopPropagation();
      var isOpen = panel.classList.toggle("open");
      btn.classList.toggle("open", isOpen);
      btn.setAttribute("aria-expanded", isOpen ? "true" : "false");
    });
    document.addEventListener("click", function(e){
      if(!panel.contains(e.target) && e.target !== btn) close();
    });
    document.addEventListener("keydown", function(e){ if(e.key === "Escape") close(); });
  }
  wireDropdown("macroBtn", "macroPanel");
  wireDropdown("aboutBtn", "aboutPanel");
  // Mobile hamburger menu -- independent of the country-breakdown
  // dropdown above (which still works exactly the same way, just
  // nested inside this menu once it's open on narrow screens).
  var navToggle = document.getElementById("navToggle");
  var navLinks = document.getElementById("navLinks");
  function closeNavMenu(){
    navLinks.classList.remove("open");
    navToggle.classList.remove("open");
    navToggle.setAttribute("aria-expanded", "false");
  }
  navToggle.addEventListener("click", function(e){
    e.stopPropagation();
    var isOpen = navLinks.classList.toggle("open");
    navToggle.classList.toggle("open", isOpen);
    navToggle.setAttribute("aria-expanded", isOpen ? "true" : "false");
  });
  document.addEventListener("click", function(e){
    if(!navLinks.contains(e.target) && e.target !== navToggle) closeNavMenu();
  });
  document.addEventListener("keydown", function(e){ if(e.key === "Escape") closeNavMenu(); });
  var themeBtn = document.getElementById("themeToggle");
  function updateThemeIcon(){
    var isDark = document.documentElement.getAttribute("data-theme") === "dark";
    themeBtn.innerHTML = isDark ? "&#9728;&#65039;" : "&#127769;";
    themeBtn.setAttribute("aria-label", isDark ? "Switch to light mode" : "Switch to dark mode");
    themeBtn.setAttribute("title", isDark ? "Switch to light mode" : "Switch to dark mode");
  }
  if(themeBtn){
    updateThemeIcon();
    themeBtn.addEventListener("click", function(){
      var isDark = document.documentElement.getAttribute("data-theme") === "dark";
      if(isDark){
        document.documentElement.removeAttribute("data-theme");
        try{ localStorage.setItem("eatlas_theme", "light"); }catch(e){}
      } else {
        document.documentElement.setAttribute("data-theme", "dark");
        try{ localStorage.setItem("eatlas_theme", "dark"); }catch(e){}
      }
      updateThemeIcon();
    });
  }
})();
</script>
<div class="auth-modal" id="authModal" hidden>
 <div class="auth-modal-backdrop" id="authModalBackdrop"></div>
 <div class="auth-modal-content">
 <button type="button" class="auth-modal-close" id="authModalClose" aria-label="Close">&times;</button>
 <div id="authFormView">
 <h2 id="authModalTitle">Log in</h2>
 <p class="auth-modal-sub" id="authModalSub">Welcome back.</p>
 <form id="authForm">
 <div class="auth-field">
 <label for="authEmail">Email</label>
 <input type="email" id="authEmail" required autocomplete="email">
 </div>
 <div class="auth-field">
 <label for="authPassword">Password</label>
 <input type="password" id="authPassword" required autocomplete="current-password" minlength="6">
 </div>
 <button type="submit" class="btn auth-submit" id="authSubmitBtn">Log in</button>
 </form>
 <p class="auth-toggle" id="authForgotRow"><button type="button" id="authForgotBtn">Forgot password?</button></p>
 <p class="auth-toggle" id="authToggleRow">Don't have an account? <button type="button" id="authToggleBtn">Sign up</button></p>
 <p class="auth-msg" id="authMsg"></p>
 </div>
 <div id="authForgotView" hidden>
 <h2>Reset password</h2>
 <p class="auth-modal-sub">Enter your email and we'll send a reset link.</p>
 <form id="authForgotForm">
 <div class="auth-field">
 <label for="authForgotEmail">Email</label>
 <input type="email" id="authForgotEmail" required autocomplete="email">
 </div>
 <button type="submit" class="btn auth-submit" id="authForgotSubmitBtn">Send reset link</button>
 </form>
 <p class="auth-toggle"><button type="button" id="authBackToLoginBtn">Back to log in</button></p>
 <p class="auth-msg" id="authForgotMsg"></p>
 </div>
 <div id="authResetView" hidden>
 <h2>Set a new password</h2>
 <p class="auth-modal-sub">Choose a new password for your account.</p>
 <form id="authResetForm">
 <div class="auth-field">
 <label for="authNewPassword">New password</label>
 <input type="password" id="authNewPassword" required autocomplete="new-password" minlength="6">
 </div>
 <button type="submit" class="btn auth-submit" id="authResetSubmitBtn">Set new password</button>
 </form>
 <p class="auth-msg" id="authResetMsg"></p>
 </div>
 <div id="authSignedInView" hidden class="auth-signedin-box">
 <h2>Account</h2>
 <p>Signed in as</p>
 <p><strong id="authUserEmail"></strong></p>
 <div id="acctPlanBox" class="acct-plan-box"></div>
 <button type="button" class="btn ghost" id="authChangePasswordBtn" style="margin-bottom:10px;">Change password</button>
 <button type="button" class="btn ghost" id="authSignOutBtn">Log out</button>
 <p class="auth-msg" id="authSignOutMsg"></p>
 </div>
 </div>
</div>
<script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.116.0"></script>
<script>
// The real, complete auth system extracted verbatim from the country
// pages (sign in, sign up, forgot/reset password, sign out, session
// sync) -- not a second, separately-written copy. Only the unrelated
// download-gating code that happened to share the same enclosing
// function on the source page is left out, since nothing on this page
// needs it.
(function(){
  var SUPABASE_URL = "https://skluvrxnuibkordzgtmu.supabase.co";
  var SUPABASE_KEY = "sb_publishable_p6_GqrC8qcNC6KwPE46hkw_qdWQTuyT";
  var sb = supabase.createClient(SUPABASE_URL, SUPABASE_KEY);
  // Exposed globally so the Save & Share code in the later <script>
  // block (a separate IIFE, not sharing this function's local `sb`) can
  // reach the same client rather than creating a second connection.
  window.sb = sb;
  var authBtn = document.getElementById("authBtn");
  var authModal = document.getElementById("authModal");
  var authModalBackdrop = document.getElementById("authModalBackdrop");
  var authModalClose = document.getElementById("authModalClose");
  var authForm = document.getElementById("authForm");
  var authEmail = document.getElementById("authEmail");
  var authPassword = document.getElementById("authPassword");
  var authSubmitBtn = document.getElementById("authSubmitBtn");
  var authMsg = document.getElementById("authMsg");
  var authToggleRow = document.getElementById("authToggleRow");
  var authModalTitle = document.getElementById("authModalTitle");
  var authModalSub = document.getElementById("authModalSub");
  var authFormView = document.getElementById("authFormView");
  var authSignedInView = document.getElementById("authSignedInView");
  var authUserEmail = document.getElementById("authUserEmail");
  var authSignOutBtn = document.getElementById("authSignOutBtn");
  var authSignOutMsg = document.getElementById("authSignOutMsg");
  var authForgotBtn = document.getElementById("authForgotBtn");
  var authForgotView = document.getElementById("authForgotView");
  var authForgotForm = document.getElementById("authForgotForm");
  var authForgotEmail = document.getElementById("authForgotEmail");
  var authForgotSubmitBtn = document.getElementById("authForgotSubmitBtn");
  var authForgotMsg = document.getElementById("authForgotMsg");
  var authBackToLoginBtn = document.getElementById("authBackToLoginBtn");
  var authResetView = document.getElementById("authResetView");
  var authResetForm = document.getElementById("authResetForm");
  var authNewPassword = document.getElementById("authNewPassword");
  var authResetSubmitBtn = document.getElementById("authResetSubmitBtn");
  var authResetMsg = document.getElementById("authResetMsg");
  var authChangePasswordBtn = document.getElementById("authChangePasswordBtn");
  var mode = "login";
  function showMsg(el, text, kind){
    el.textContent = text;
    el.className = "auth-msg show " + kind;
  }
  // Every auth call runs through authCall so the button always comes back,
  // whether the request succeeds, returns an error, rejects, or never
  // answers. Connection problems get one plain message instead of the
  // library's own wording.
  var AUTH_NETWORK_MSG = "We couldn't reach the server. Check your connection and try again.";
  var AUTH_TIMEOUT_MS = 15000;
  function isConnectionError(err){
    return !!err && (err.name === "AuthRetryableFetchError" || err.status === 0 || err.status >= 500);
  }
  function authCall(btn, msgEl, run, onResult){
    var settled = false, timedOut = false;
    btn.disabled = true;
    clearMsg(msgEl);
    function finish(){ settled = true; clearTimeout(timer); btn.disabled = false; }
    var timer = setTimeout(function(){
      if(settled) return;
      timedOut = true;
      btn.disabled = false;
      showMsg(msgEl, AUTH_NETWORK_MSG, "error");
    }, AUTH_TIMEOUT_MS);
    var p;
    try { p = Promise.resolve(run()); } catch(err) { p = Promise.reject(err); }
    p.then(function(res){
      if(settled) return;
      res = res || {};
      if(timedOut && res.error) { finish(); return; }
      finish();
      if(res.error && isConnectionError(res.error)){ showMsg(msgEl, AUTH_NETWORK_MSG, "error"); return; }
      if(timedOut) clearMsg(msgEl);
      onResult(res);
    }, function(){
      if(settled) return;
      finish();
      showMsg(msgEl, AUTH_NETWORK_MSG, "error");
    });
  }
  function clearMsg(el){
    el.className = "auth-msg";
    el.textContent = "";
  }
  function hideAllViews(){
    authFormView.hidden = true;
    authForgotView.hidden = true;
    authResetView.hidden = true;
    authSignedInView.hidden = true;
  }
  function wireToggleBtn(label, nextMode){
    var btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = label;
    btn.addEventListener("click", function(){ setMode(nextMode); });
    return btn;
  }
  function setMode(newMode){
    mode = newMode;
    clearMsg(authMsg);
    authForm.reset();
    if(mode === "login"){
      authModalTitle.textContent = "Log in";
      authModalSub.textContent = "Welcome back.";
      authSubmitBtn.textContent = "Log in";
      authToggleRow.textContent = "Don't have an account? ";
      authToggleRow.appendChild(wireToggleBtn("Sign up", "signup"));
    } else {
      authModalTitle.textContent = "Sign up";
      authModalSub.textContent = "Free, for now, this may change in future.";
      authSubmitBtn.textContent = "Sign up";
      authToggleRow.textContent = "Already have an account? ";
      authToggleRow.appendChild(wireToggleBtn("Log in", "login"));
    }
  }
  function showLoginView(){
    hideAllViews();
    authFormView.hidden = false;
    setMode("login");
  }
  function showForgotView(){
    hideAllViews();
    authForgotView.hidden = false;
    clearMsg(authForgotMsg);
    authForgotForm.reset();
  }
  function showResetView(){
    hideAllViews();
    authResetView.hidden = false;
    clearMsg(authResetMsg);
    authResetForm.reset();
  }
  function showSignedInView(session){
    hideAllViews();
    authSignedInView.hidden = false;
    authUserEmail.textContent = session.user.email;
  }
  function openAuthModal(){
    authModal.hidden = false;
    document.body.style.overflow = "hidden";
    // Was unconditionally showing the login form, even for an
    // already-logged-in account -- every "locked, click to unlock"
    // button (buy credits, upgrade to Pro) calls this, and for someone
    // already signed in that meant clicking "buy credits" appeared to
    // demand a login instead of showing the account panel where credits
    // actually get bought. Check the real session first, same as the
    // top-right account button's own handler already correctly does.
    sb.auth.getSession().then(function(res){
      var session = res.data.session;
      if(session){
        showSignedInView(session);
      } else {
        showLoginView();
      }
    });
  }
  function closeAuthModal(){
    authModal.hidden = true;
    document.body.style.overflow = "";
  }
  function updateAuthUI(session){
    if(session && session.user){
      authBtn.textContent = session.user.email;
      authBtn.classList.add("signed-in");
    } else {
      authBtn.textContent = "Log in";
      authBtn.classList.remove("signed-in");
    }
    if(window.EATLAS_DOWNLOAD) window.EATLAS_DOWNLOAD.setAuthState(!!(session && session.user));
    if(window.EATLAS_PREFS) window.EATLAS_PREFS.setAuthState(!!(session && session.user), session && session.user ? session.user.id : null);
  }
  authBtn.addEventListener("click", function(){
    sb.auth.getSession().then(function(res){
      var session = res.data.session;
      authModal.hidden = false;
      document.body.style.overflow = "hidden";
      if(session){
        showSignedInView(session);
      } else {
        showLoginView();
      }
    });
  });
  authModalClose.addEventListener("click", closeAuthModal);
  authModalBackdrop.addEventListener("click", closeAuthModal);
  document.addEventListener("keydown", function(e){ if(e.key === "Escape" && !authModal.hidden) closeAuthModal(); });
  authForm.addEventListener("submit", function(e){
    e.preventDefault();
    var email = authEmail.value.trim();
    var password = authPassword.value;
    if(mode === "signup"){
      authCall(authSubmitBtn, authMsg, function(){ return sb.auth.signUp({ email: email, password: password }); }, function(res){
        if(res.error){
          showMsg(authMsg, res.error.message, "error");
        } else if(res.data.user && !res.data.session){
          showMsg(authMsg, "Check your email to confirm your account before logging in.", "success");
          authForm.reset();
        } else {
          showMsg(authMsg, "Account created.", "success");
        }
      });
    } else {
      authCall(authSubmitBtn, authMsg, function(){ return sb.auth.signInWithPassword({ email: email, password: password }); }, function(res){
        if(res.error){
          showMsg(authMsg, res.error.message, "error");
        } else {
          closeAuthModal();
        }
      });
    }
  });
  // --- Forgot password ---
  authForgotBtn.addEventListener("click", showForgotView);
  authBackToLoginBtn.addEventListener("click", showLoginView);
  authForgotForm.addEventListener("submit", function(e){
    e.preventDefault();
    var email = authForgotEmail.value.trim();
    authCall(authForgotSubmitBtn, authForgotMsg, function(){ return sb.auth.resetPasswordForEmail(email); }, function(res){
      if(res.error){
        showMsg(authForgotMsg, res.error.message, "error");
      } else {
        showMsg(authForgotMsg, "Check your email for a password reset link.", "success");
        authForgotForm.reset();
      }
    });
  });
  // --- Set / change password ---
  // The same form and handler serve two different entry points: someone
  // who clicked a "forgot password" reset link (Supabase creates a
  // temporary session just for this) and someone who's already properly
  // logged in and wants to change their password from the account view.
  // Either way, updateUser() is exactly the same call.
  authResetForm.addEventListener("submit", function(e){
    e.preventDefault();
    var password = authNewPassword.value;
    authCall(authResetSubmitBtn, authResetMsg, function(){ return sb.auth.updateUser({ password: password }); }, function(res){
      if(res.error){
        showMsg(authResetMsg, res.error.message, "error");
      } else {
        showMsg(authResetMsg, "Password updated.", "success");
        authResetForm.reset();
      }
    });
  });
  authChangePasswordBtn.addEventListener("click", showResetView);
  authSignOutBtn.addEventListener("click", function(){
    authCall(authSignOutBtn, authSignOutMsg, function(){ return sb.auth.signOut(); }, function(res){
      if(res.error){
        showMsg(authSignOutMsg, res.error.message, "error");
      } else {
        closeAuthModal();
      }
    });
  });
  sb.auth.onAuthStateChange(function(event, session){
    updateAuthUI(session);
    if(event === "PASSWORD_RECOVERY"){
      // Someone landed here via a password-reset email link -- open
      // straight into the "set a new password" view rather than
      // leaving them to notice they're now (temporarily) signed in
      // and have to hunt for how to actually finish resetting it.
      authModal.hidden = false;
      document.body.style.overflow = "hidden";
      showResetView();
    }
  });
  sb.auth.getSession().then(function(res){
    updateAuthUI(res.data.session);
  });
})();
</script>
"""

FOOTER_HTML = """<footer>
 Data from official national and international statistics sources. Series codes are shown with each metric;
 figures are the latest published observations and are subject to revision.
 Ideas or corrections: <a href="../contact">get in touch</a>. <a href="../privacy">Privacy</a> &middot; <a href="../terms">Terms</a>.
</footer>
"""

def flag_emoji(alpha2):
    return "".join(chr(0x1F1E6 + ord(c) - 65) for c in alpha2.upper())

def header_for(slug):
    """Marks the current country's own link active in the real nav's
    country mega-menu, matching how every real country page marks
    itself, without needing 32 separate copies of the nav markup."""
    return HEADER_HTML_BASE.replace(f'href="../{slug}"', f'href="../{slug}" class="active"', 1)

def esc(s):
    return htmllib.escape(str(s), quote=True)



# ---------------------------------------------------------------------------
# Page building
# ---------------------------------------------------------------------------
ARROW_SVG = ('<svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M4 10h11m-4.5-4.5L15 10l-4.5 4.5" '
             'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>')

_BLOCK_CACHE = {}
def country_blocks(cslug):
    """Download data + Customise & export, taken verbatim from the country's
    own page at build time, so the indicator page runs exactly the code the
    country page runs (and follows any change to it on the next build).
    Returns (auth_script, customise_modal_html, customise_script)."""
    if cslug in _BLOCK_CACHE:
        return _BLOCK_CACHE[cslug]
    src = open(os.path.join(ROOT, f"{cslug}.html"), encoding="utf-8").read()
    auth = re.search(r"<script>\s*\(function\(\)\{\s*var SUPABASE_URL.*?</script>", src, re.S)
    modal = re.search(r'<div class="chart-modal" id="customizeModal" hidden>.*?(?=<script>\s*\(function\(\)\{\s*"use strict";\s*var G = \{ W:820)', src, re.S)
    cz = re.search(r'<script>\s*\(function\(\)\{\s*"use strict";\s*var G = \{ W:820.*?</script>', src, re.S)
    if not (auth and modal and cz):
        raise SystemExit(f"{cslug}.html: could not find the download/customise blocks to reuse")
    fix = lambda t: t.replace('href="contact"', 'href="../contact"').replace("href=\\\"contact\\\"", "href=\\\"../contact\\\"")
    out = (fix(auth.group(0)), fix(modal.group(0)), fix(cz.group(0)))
    _BLOCK_CACHE[cslug] = out
    return out

TRIMMED_AUTH_RE = re.compile(r"<script>\s*// The real, complete auth system extracted verbatim.*?</script>", re.S)

def ordinal(n):
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"

def head_html(title, desc, canonical, og_image, jsonld, extra_css=""):
    og = f'<meta property="og:image" content="{og_image}">\n<meta name="twitter:image" content="{og_image}">\n' if og_image else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{canonical}">
<meta property="og:type" content="website">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{canonical}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{esc(title)}">
<meta name="twitter:description" content="{esc(desc)}">
{og}<link rel="icon" type="image/png" sizes="32x32" href="../favicon-32.png">
<link rel="apple-touch-icon" href="../apple-touch-icon.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Nunito+Sans:wght@400;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="../style.css?v=52">
<link rel="stylesheet" href="../mobile.css?v=14">
<link rel="stylesheet" href="../indicator.css?v={KIT_VERSION}">
<script type="application/ld+json">
{jsonld}
</script>
</head>
<body>
"""

def page_tail(extra_js="", extra_html=""):
    return f"""<div class="ind-footwrap">{FOOTER_HTML}</div>
{extra_html}
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<script src="../indicator-kit.js?v={KIT_VERSION}"></script>
{extra_js}
<script src="../mobile.js?v=15"></script>
</body>
</html>
"""

LIGHTS_KEY = ('<p class="lightskey"><span><span class="led green" aria-hidden="true"></span>'
              'Matches the latest release</span><span><span class="led orange" aria-hidden="true"></span>'
              'Not refreshed recently, awaiting the next release</span></p>')

def glow_cta(href, title, sub, compact=False):
    return (f'<a class="glow-cta{" compact" if compact else ""}" href="{href}">'
            f'<span class="glow-inner"><span class="glow-text"><span class="glow-title">{esc(title)}</span>'
            f'<span class="glow-sub">{esc(sub)}</span></span>'
            f'<span class="glow-go">{ARROW_SVG}</span></span></a>')

def rank_grid(meta, current_slug=None, country=None, rank_info=None, prefix="../rankings/"):
    items = []
    for rm in meta:
        cur = rm["slug"] == current_slug
        pos = (rank_info or {}).get(rm["slug"], {}).get(country) if country else None
        sub = f"{esc(country)} is {ordinal(pos)} of {rm['count']}" if (cur and pos) else f"{rm['count']} countries"
        item = (f'<a class="{"current" if cur else ""}" href="{prefix}{rm["slug"]}"{' aria-current="page"' if cur and not country else ""}>'
                f'<span>{esc(rm["title"])}<span class="n">{sub}</span></span>{ARROW_SVG}</a>')
        (items.insert(0, item) if cur and country else items.append(item))
    return '<div class="cmp-rankgrid">' + "".join(items) + "</div>"

def first_sentence(text):
    m = re.match(r"(.+?[.!?])(\s|$)", text or "")
    return m.group(1) if m else (text or "")

def sparkline_svg(pts):
    vals = [p[1] for p in pts]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1
    W, H, pad = 96, 28, 3
    step = (W - 2 * pad) / (len(vals) - 1)
    xy = [(pad + i * step, pad + (H - 2 * pad) * (1 - (v - lo) / span)) for i, v in enumerate(vals)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in xy)
    lx, ly = xy[-1]
    return (f'<svg viewBox="0 0 {W} {H}" aria-hidden="true"><polyline class="rk-spark" points="{line}"/>'
            f'<circle class="rk-spark-dot" cx="{lx:.1f}" cy="{ly:.1f}" r="2.4"/></svg>')

def trailing_years(pts, years=5):
    end = period_end_date(pts[-1][0])
    cut = date(end.year - years, end.month, min(end.day, 28))
    f = [p for p in pts if period_end_date(p[0]) > cut]
    return f if len(f) >= 2 else pts[-2:]

FREQ_WORD = {"months": "Monthly", "quarters": "Quarterly", "years": "Annual"}


def quarter_window_label(period, freq, raw):
    """'Q3 2025 to Q2 2026' for a rolling four-quarter figure, so a GDP
    total is never mistaken for a calendar year that hasn't ended."""
    m = re.match(r"^(\d{4})-Q([1-4])$", period)
    if raw or freq != "quarters" or not m:
        return None
    y, q = int(m.group(1)), int(m.group(2))
    sy, sq = (y - 1, q + 1) if q < 4 else (y, 1)
    return f"{fmt_period_label(f'{sy}-Q{sq}')} to {fmt_period_label(period)}"


def build_country_catalogue(country, data, sources):
    """Every indicator page this country gets, in registry order."""
    series = data.get("series", {})
    out = []
    for m in METRICS:
        r = resolve(country, series, sources, m)
        if not r:
            continue
        key, s, pts = r
        unit = s.get("unit", "")
        out.append(dict(m=m, key=key, s=s, pts=pts, unit=unit,
                        title=metric_title(m, country, key, unit),
                        up=metric_up(m, country, unit)))
    return out


def _year_total_gdp(series, country, year):
    """A year's GDP from its published observations: the annual figure, the
    sum of its four quarters, or (US, Japan, published at an annual rate)
    their average. None unless every period of the year is published."""
    freq = series.get("freq", "")
    pts = {p[0]: p[1] for p in clean_points(series)}
    if freq == "years":
        return pts.get(str(year))
    qs = [pts.get(f"{year}-Q{q}") for q in (1, 2, 3, 4)]
    if any(v is None for v in qs):
        return None
    return sum(qs) / 4 if country in GDP_RAW_COUNTRIES else sum(qs)


def rank_rows(ranking, catalogue_by_country):
    """Rows for one ranking: (ranked rows sorted high to low, unranked notes)."""
    m = METRIC_BY_SLUG[ranking["metric"]]
    rows, unranked = [], []
    Y = flow_year()
    for country, info in catalogue_by_country.items():
        entry = info["by_slug"].get(m["slug"])
        if not entry:
            continue
        s, pts, unit, key = entry["s"], entry["pts"], entry["unit"], entry["key"]
        freq = s.get("freq", "")
        src_pub, src_series = short_source(info["sources"].get(key, {}).get("source", ""))
        # Freshness follows the series' newest release, not the (fixed)
        # reference year a flow ranking shows.
        base = dict(country=country, freq=freq, key=key, unit=unit, src_pub=src_pub, src_series=src_series,
                    latest_period=pts[-1][0])
        if ranking.get("freqs") and freq not in ranking["freqs"]:
            want = FREQ_WORD.get(ranking["freqs"][0], "").lower()
            unranked.append((country, f"published {FREQ_WORD.get(freq, freq).lower()}, not {want}"))
            continue
        if ranking.get("units") and not any(u in unit for u in ranking["units"]):
            unranked.append((country, "published in currency, not as a share of GDP"))
            continue

        if ranking.get("usd"):
            val = _year_total_gdp(s, country, Y)
            prior = _year_total_gdp(s, country, Y - 1)
            if val is None:
                unranked.append((country, f"{Y} not yet complete"))
                continue
            fx = info["data"].get("fx_to_usd")
            if country in GDP_ALREADY_USD:
                usd = val
            elif fx:
                usd = to_usd_value(val, str(Y), fx)
            else:
                usd = None
            if usd is None:
                unranked.append((country, "no exchange rate to convert to US dollars"))
                continue
            chg = (val / prior - 1) * 100 if prior else None
            yearly = [(str(y), _year_total_gdp(s, country, y)) for y in range(Y - 5, Y + 1)]
            spark = [p for p in yearly if p[1] is not None]
            rows.append(dict(base, value=usd * scale_of(unit) / 1e9,
                             value_str=fmt_num(usd, usd_unit(unit), key, country, "cell", True),
                             change=chg, change_str=(fmt_num(chg, "%", "", "", "delta").replace("pp", "%") if chg is not None else "n/a"),
                             period=str(Y), spark=spark))
            continue

        if ranking.get("flow"):
            target = f"{Y}-Q4" if freq == "quarters" else str(Y)
            idx = next((i for i, p in enumerate(pts) if p[0] == target), None)
            if idx is None or idx == 0:
                latest = fmt_period_label(pts[-1][0])
                unranked.append((country, f"no {fmt_period_label(target)} figure yet, latest is {latest}"))
                continue
            period, val = pts[idx]
            prev_p, prev = pts[idx - 1]
            spark = trailing_years(pts[:idx + 1], 5)
        else:
            period, val = pts[-1]
            prev_p, prev = pts[-2]
            spark = trailing_years(pts, 5)
        d = rounded_delta(val - prev, unit, key)
        rows.append(dict(base, value=val, value_str=fmt_num(val, unit, key, country, "cell"),
                         change=d, change_str=fmt_num(d, unit, key, country, "delta") if abs(d) > 1e-9 else "No change",
                         period=period, spark=spark, prev_period=prev_p))
    rows.sort(key=lambda r: -r["value"])
    return rows, unranked


def render_indicator(country, info, entry, rank_info, all_rankings_meta, n_indicators):
    iso2, cslug, alpha2, region = COUNTRIES[country]
    m, key, s, pts, unit = entry["m"], entry["key"], entry["s"], entry["pts"], entry["unit"]
    title = entry["title"]
    sources = info["sources"]
    meta = sources.get(key, {})
    description = meta.get("description", "")
    source_text = meta.get("source", "")
    data_file = data_file_for(iso2)
    page_slug = f"{cslug}-{m['slug']}"
    canonical = f"{SITE_URL}/indicators/{page_slug}"
    freq = s.get("freq", "")

    latest_p, latest_v = pts[-1]
    prev_p, prev_v = pts[-2]
    latest_str = fmt_num(latest_v, unit, key, country)
    d = rounded_delta(latest_v - prev_v, unit, key)
    flat = abs(d) < 1e-9
    ddir = "flat" if flat else ("good" if (d > 0) == entry["up"] else "bad")
    arrow = "\u25AC" if flat else ("\u25B2" if d > 0 else "\u25BC")
    dstr = "No change" if flat else fmt_num(d, unit, key, country, "delta")
    fresh = is_fresh(latest_p, freq)
    led_title = f"Latest release: {fmt_period_label(latest_p)}" if fresh else f"Awaiting next release. Last data: {fmt_period_label(latest_p)}"
    updated = (info["data"].get("updated") or "")[:10]

    # Dollarise / Make it real: GDP only, as on the country pages.
    toggles_html, real_pts, real_unit, fx = "", None, None, None
    if m["slug"] == "gdp":
        rr = resolve(country, info["data"]["series"], sources, METRIC_BY_SLUG["real-gdp"])
        if rr:
            real_pts, real_unit = rr[2], rr[1].get("unit", "")
        if country not in GDP_ALREADY_USD:
            fx = info["data"].get("fx_to_usd")
        btns = []
        if real_pts:
            btns.append('<button type="button" class="mtoggle" id="indToggleReal" aria-pressed="false"><span class="mtoggle-switch" aria-hidden="true"></span>Make it real</button>')
        if fx:
            btns.append('<button type="button" class="mtoggle" id="indToggleDollar" aria-pressed="false"><span class="mtoggle-switch" aria-hidden="true"></span>Dollarise</button>')
        if btns:
            toggles_html = '<div class="ind-toggles" aria-label="Display options">' + "".join(btns) + "</div>"

    cfg = dict(key=key, country=country, unit=unit, freq=freq, upIsGood=entry["up"], chart=m["chart"],
               annualise=bool(m.get("ann")), gdpRaw=country in GDP_RAW_COUNTRIES, dataUrl=f"../{data_file}",
               points=pts, realPoints=real_pts, realUnit=real_unit, realKey=("gdp_real" if real_pts else None), fx=fx)

    # related tiles, grouped by category
    tiles, last_cat = [], None
    for e in info["catalogue"]:
        if e is entry:
            continue
        if e["m"]["cat"] != last_cat:
            last_cat = e["m"]["cat"]
            tiles.append(f'<div class="ind-cat">{esc(last_cat)}</div>')
        lp, lv = e["pts"][-1]
        tiles.append(f'<a href="{cslug}-{e["m"]["slug"]}"><span class="r-name">{esc(e["title"])}</span>'
                     f'<span class="r-val">{esc(fmt_num(lv, e["unit"], e["key"], country))}</span>'
                     f'<span class="r-per">{esc(fmt_period_label(lp))}</span></a>')
    related_html = "\n".join(tiles)

    this_rk = RANKING_BY_METRIC.get(m["slug"])
    rk_grid = rank_grid(all_rankings_meta, this_rk["slug"] if this_rk else None, country, rank_info)
    n_label = f"{n_indicators} live indicators" if n_indicators > 1 else "Live indicators"
    cta = glow_cta(f"../{cslug}", f"Explore the full {country} economy",
                   f"{n_label} on one dashboard, from growth and prices to jobs, trade and public finances. Updated hourly from official sources.")

    meta_label = re.sub(r"\s*\([^)]*\)", "", title).strip().lower()
    page_title = f"{country} {title}: {latest_str} ({fmt_period_label(latest_p)}) | The Economic Atlas"
    meta_desc = f"{country} {meta_label} was {latest_str} in {fmt_period_label(latest_p)}. {first_sentence(description)} Live chart and full history from {fmt_period_label(pts[0][0])}."
    if len(meta_desc) > 300:
        meta_desc = meta_desc[:297] + "..."
    jsonld = json.dumps({
        "@context": "https://schema.org", "@type": "Dataset",
        "name": f"{country} {title}", "description": description or f"{country} {title}", "url": canonical,
        "temporalCoverage": f"{iso_period(pts[0][0])}/{iso_period(latest_p)}",
        "spatialCoverage": country,
        "creator": {"@type": "Organization", "name": "The Economic Atlas", "url": SITE_URL},
        "distribution": {"@type": "DataDownload", "encodingFormat": "application/json", "contentUrl": f"{SITE_URL}/{data_file}"},
        "variableMeasured": title,
    }, ensure_ascii=False, indent=2)
    og_image = f"{SITE_URL}/og/{page_slug}.png"

    auth_full, cz_modal, cz_script = country_blocks(cslug)
    # A rolling four-quarter GDP total is four published quarters added up,
    # not a forecast of an unfinished year; say which four.
    win = quarter_window_label(latest_p, freq, country in GDP_RAW_COUNTRIES) if m.get("ann") else None
    window_html = f'<p class="ind-when">Latest four quarters: <strong>{esc(win)}</strong></p>' if win else ""
    rest = description[len(first_sentence(description)):].strip()
    about_p = f"<p>{esc(rest)}</p>" if rest else ""
    html_out = head_html(page_title, meta_desc, canonical, og_image, jsonld)
    hdr = header_for(cslug)
    hdr, n_auth = TRIMMED_AUTH_RE.subn(lambda _m: auth_full, hdr)
    if n_auth != 1:
        raise SystemExit("header auth block not found for replacement")
    html_out += hdr
    html_out += f"""<main class="ind-wrap">
  <header class="ind-head">
    <h1>{esc(country)} {esc(title)}</h1>
    <p class="ind-lede">{esc(first_sentence(description))}</p>
  </header>
  <div class="ind-stat">
    <p class="ind-figure"><span class="led {'green' if fresh else 'orange'}" id="indLed" title="{esc(led_title)}" role="img" aria-label="{esc(led_title)}"></span><span id="indFigure">{esc(latest_str)}</span></p>
    <div class="ind-meta">
      <p class="ind-delta {ddir}" id="indDelta"><span aria-hidden="true">{arrow}</span> {esc(dstr)} <span class="ind-delta-vs">vs {esc(fmt_period_label(prev_p))}</span></p>
      <p class="ind-when"><strong id="indPeriod">{esc(fmt_period_label(latest_p))}</strong> &middot; {esc(FREQ_WORD.get(freq, ''))} data</p>
      {window_html}
    </div>
  </div>
  {LIGHTS_KEY}
  {cta}
  {toggles_html}
  <section class="panel ind-panel" aria-labelledby="chartTitle">
    <div class="ind-panelhead">
      <h2 id="chartTitle">{esc(title)}</h2>
      <div class="ind-ranges" role="group" aria-label="Time range">
        <button type="button" data-range="max" class="active" aria-pressed="true">Max</button><button type="button" data-range="10" aria-pressed="false">10Y</button><button type="button" data-range="5" aria-pressed="false">5Y</button><button type="button" data-range="1" aria-pressed="false">1Y</button>
      </div>
    </div>
    <p class="range" id="indRange">{esc(fmt_period_label(pts[0][0]))} to {esc(fmt_period_label(latest_p))}</p>
    <div class="ind-chart"><canvas id="indChart" role="img" aria-label="{esc(country)} {esc(title)}, {esc(fmt_period_label(pts[0][0]))} to {esc(fmt_period_label(latest_p))}"></canvas></div>
    <div class="lockedactions" id="indActions"></div>
    <p class="src">Source: {esc(source_text)}</p>
  </section>
  <div class="ind-about">
    {about_p}
    <p class="ind-src">Data refreshed {esc(updated)}. Figures are the latest published observations and can be revised.</p>
  </div>
  <section class="ind-section" aria-labelledby="relHead">
    <h2 id="relHead">More {esc(country)} indicators</h2>
    <p class="ind-section-sub">Latest readings. Open any one for its full history.</p>
    <div class="ind-related">
{related_html}
    </div>
  </section>
  <section class="ind-section" aria-labelledby="rkHead">
    <h2 id="rkHead">Rankings</h2>
    <p class="ind-section-sub">See every country we track, side by side.</p>
    {rk_grid}
    <div class="ind-secondary">
      <a class="rk-btn" href="../compare">Compare countries over time</a>
      <a class="rk-btn" href="../embed/{page_slug}">Embed this chart</a>
    </div>
  </section>
</main>
"""
    cfg["title"] = f"{country} {title}"
    cfg["srcNote"] = source_text
    boot = f"<script>EATLAS_IND.initIndicator({json.dumps(cfg, ensure_ascii=False)});</script>"
    html_out += page_tail(boot + "\n" + cz_script, cz_modal)
    return page_slug, html_out


def render_ranking(ranking, rows, unranked, all_rankings_meta, catalogue_by_country):
    m = METRIC_BY_SLUG[ranking["metric"]]
    canonical = f"{SITE_URL}/rankings/{ranking['slug']}"
    usd = ranking.get("usd")
    vals = [r["value"] for r in rows]
    hi, lo = (max(vals), min(vals)) if len(vals) > 1 else (None, None)
    bar_max = max(abs(v) for v in vals) if vals else 1

    body = []
    for i, r in enumerate(rows, 1):
        c = r["country"]
        cslug = COUNTRIES[c][1]
        cls = ""
        fresh = is_fresh(r["latest_period"], r["freq"])
        led = f'<span class="led {"green" if fresh else "orange"}" aria-hidden="true" style="width:7px;height:7px;margin-right:5px;vertical-align:1px"></span>'
        tag = FREQ_WORD.get(r["freq"], "")
        width = abs(r["value"]) / bar_max * 100 if bar_max else 0
        chg_title = f' title="Nominal change on a year earlier, in {esc(c)}\'s own currency"' if usd else (f' title="Change on {esc(fmt_period_label(r.get("prev_period", "")))}"' if r.get("prev_period") else "")
        chg_attr = "" if r["change"] is None else f"{r['change']:.6g}"
        body.append(
            f'<tr data-rank="{i}" data-country="{esc(c)}" data-value="{r["value"]:.6g}" data-change="{chg_attr}" data-period="{period_end_date(r["period"]).isoformat()}" data-source="{esc(r["src_pub"])}">'
            f'<td class="rank">{i}</td>'
            f'<td class="country"><a href="../indicators/{cslug}-{m["slug"]}">{esc(c)}</a><span class="rk-region">{esc(COUNTRIES[c][3])}</span></td>'
            f'<td class="num val{cls}">{esc(r["value_str"])}<span class="rk-bar"><span class="{"neg" if r["value"] < 0 else ""}" style="width:{width:.1f}%"></span></span></td>'
            f'<td class="num chg"{chg_title}>{esc(r["change_str"])}</td>'
            f'<td class="num">{led}{esc(fmt_period_label(r["period"]))}<span class="measuretag">{esc(tag)}</span></td>'
            f'<td class="trend">{sparkline_svg(r["spark"])}</td>'
            f'<td class="src">{esc(r["src_pub"])}<span class="src-series">{esc(r["src_series"])}</span></td>'
            f'</tr>')
    table = "\n".join(body)

    summary = ""
    if len(rows) >= 3:
        med = rows[len(rows) // 2]
        summary = (f'<div class="rk-summary">'
                   f'<div><span class="s-lab">Highest</span><span class="s-val">{esc(rows[0]["value_str"])}</span><span class="s-who">{esc(rows[0]["country"])}, {esc(fmt_period_label(rows[0]["period"]))}</span></div>'
                   f'<div><span class="s-lab">Middle of the {len(rows)}</span><span class="s-val">{esc(med["value_str"])}</span><span class="s-who">{esc(med["country"])}, {esc(fmt_period_label(med["period"]))}</span></div>'
                   f'<div><span class="s-lab">Lowest</span><span class="s-val">{esc(rows[-1]["value_str"])}</span><span class="s-who">{esc(rows[-1]["country"])}, {esc(fmt_period_label(rows[-1]["period"]))}</span></div>'
                   f'</div>')

    unranked_html = ""
    if unranked:
        parts = "; ".join(f"{esc(c)} ({esc(why)})" for c, why in sorted(unranked))
        unranked_html = f'<p class="rk-unranked">Not ranked here: {parts}. Each still has its own page.</p>'

    metric_word = re.sub(r"\s*\([^)]*\)", "", m["title"]).lower()
    if m["slug"] == "gdp":
        metric_word = "GDP"
    cta = glow_cta("../compare", f"Compare {metric_word} over time in Compare",
                   "Pick any countries and any years, then chart, map and rank them side by side, same period for every country.")
    chg_head = "1-year change (nominal)" if usd else "Change"
    Y = flow_year()
    if ranking.get("flow"):
        head_txt = f"{len(rows)} countries, {Y}"
        note_txt = (f"Every figure is for {Y}, the last completed year. A year still in progress is never shown for a flow, "
                    "because a part-year total isn't comparable. Click any column to sort.")
    else:
        head_txt = f"{len(rows)} countries, latest reading"
        note_txt = "Each country's latest published reading, with the period it refers to. Periods can differ between countries. Click any column to sort."

    latest_all = max((r["period"] for r in rows), key=lambda p: period_end_date(p)) if rows else ""
    top = rows[0] if rows else None
    page_title = f"{ranking['title']} ({len(rows)} Countries, Latest Data) | The Economic Atlas"
    meta_desc = (f"{ranking['title']}: {top['country']} is highest at {top['value_str']}. " if top else "") + ranking["lede"]
    if len(meta_desc) > 300:
        meta_desc = meta_desc[:297] + "..."
    jsonld = json.dumps({
        "@context": "https://schema.org", "@type": "Dataset",
        "name": ranking["title"], "description": ranking["lede"], "url": canonical,
        "spatialCoverage": [r["country"] for r in rows],
        "creator": {"@type": "Organization", "name": "The Economic Atlas", "url": SITE_URL},
        "variableMeasured": m["title"],
    }, ensure_ascii=False, indent=2)

    html_out = head_html(page_title, meta_desc, canonical, f"{SITE_URL}/og/rankings-{ranking['slug']}.png", jsonld)
    html_out += HEADER_HTML_BASE
    html_out += f"""<main class="ind-wrap rk-wrap">
  <header class="ind-head">
    <h1>{esc(ranking['title'])}</h1>
    <p class="ind-lede">{esc(ranking['lede'])}</p>
  </header>
  <div style="height:24px"></div>
  {summary}
  {cta}
  {LIGHTS_KEY}
  <section class="rk-card" aria-labelledby="rkTableHead">
    <div class="rk-cardhead">
      <h2 id="rkTableHead">{head_txt}</h2>
      <p class="rk-note">{note_txt}</p>
    </div>
    <div class="rk-scroll">
      <table class="rk-table" id="rkTable">
        <thead><tr>
          <th scope="col" data-sort="rank" class="sorted asc" aria-sort="ascending">#</th>
          <th scope="col" data-sort="country" data-type="text">Country</th>
          <th scope="col" class="num" data-sort="value" aria-sort="none">{esc(ranking['col'])}</th>
          <th scope="col" class="num" data-sort="change" aria-sort="none">{chg_head}</th>
          <th scope="col" class="num" data-sort="period" aria-sort="none">Period</th>
          <th scope="col">5-year trend</th>
          <th scope="col" data-sort="source" data-type="text">Source</th>
        </tr></thead>
        <tbody>
{table}
        </tbody>
      </table>
    </div>
    {unranked_html}
  </section>
  <p class="rk-unranked">Figures come from national statistics offices, central banks, Eurostat, the OECD, the IMF and the World Bank, the same sources cited on each country's page, and refresh every hour. For the same year across every country, use Compare.</p>
  <section class="ind-section" aria-labelledby="moreRk">
    <h2 id="moreRk">More rankings</h2>
    <p class="ind-section-sub">Every comparable indicator we carry, ranked across countries.</p>
    {rank_grid(all_rankings_meta, ranking["slug"], prefix="")}
  </section>
</main>
"""
    html_out += page_tail("<script>EATLAS_IND.initRanking();</script>")
    return html_out


EMBED_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{country_name} {metric_title} - Live | The Economic Atlas</title>
<link rel="icon" type="image/png" sizes="32x32" href="../favicon-32.png">
<meta name="robots" content="noindex">
<style>
  *{{box-sizing:border-box}}
  html,body{{margin:0;padding:0;font-family:"Avenir Next","Avenir","Nunito Sans",system-ui,sans-serif;color:#171B1E;background:transparent}}
  body.standalone{{background:#F5F6F3;min-height:100vh;display:flex;align-items:flex-start;justify-content:center;padding:40px 20px;}}
  .w{{padding:18px 20px 14px;border:1px solid #E4E6E1;border-radius:12px;max-width:100%;background:#fff;box-shadow:0 1px 2px rgba(0,0,0,.04);}}
  body.standalone .w{{width:380px;box-shadow:0 2px 12px rgba(0,0,0,.06);}}
  .w-title{{font-size:.82rem;font-weight:700;opacity:.7;letter-spacing:.01em;margin-bottom:8px}}
  .w-value{{font-size:1.9rem;font-weight:800;margin:2px 0;color:#1E4566;font-variant-numeric:tabular-nums}}
  .w-period{{font-size:.72rem;opacity:.6;margin-bottom:10px}}
  .w-chart-outer{{width:100%;aspect-ratio:1.618/1;position:relative;}}
  .w-badge{{display:flex;align-items:center;gap:5px;font-size:.72rem;opacity:.65;text-decoration:none;color:#171B1E;margin-top:10px}}
  .w-badge:hover{{opacity:1}}
  #chart svg{{display:block;width:100%;height:100%}}
</style>
</head>
<body>
<div class="w">
  <div class="w-title">{country_name} &middot; {metric_title}</div>
  <div class="w-value" id="val">{latest_str}</div>
  <div class="w-period" id="per">Latest: {latest_period}</div>
  <div class="w-chart-outer" id="chart"></div>
  <a class="w-badge" href="{indicator_url}" target="_blank" rel="noopener">Powered by The Economic Atlas &#8599;</a>
</div>
<script>if(window.self === window.top){{ document.body.classList.add("standalone"); }}</script>
<script src="../indicator-kit.js?v={kit_version}"></script>
<script>
(function(){{
  var CFG = {cfg};
  var F = window.EATLAS_FMT;
  fetch(CFG.dataUrl).then(function(r){{ return r.json(); }}).then(function(d){{
    var s = d.series && d.series[CFG.key];
    if(!s || !s.points) return;
    var pts = s.points.filter(function(p){{ return p && p[1] != null; }});
    if(CFG.annualise) pts = F.annualise(pts, s.freq, CFG.gdpRaw);
    if(pts.length < 2) return;
    pts = pts.slice(-24);
    var last = pts[pts.length-1];
    document.getElementById("val").textContent = F.fmtNum(last[1], {{unit: CFG.unit, key: CFG.key, country: CFG.country}});
    document.getElementById("per").textContent = "Latest: " + F.fmtPeriod(last[0]);
    var vals = pts.map(function(p){{ return p[1]; }});
    var lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals), span = (hi-lo) || 1;
    var W=340, H=210, pad=6, step=(W-2*pad)/(pts.length-1);
    var xy = pts.map(function(p,i){{ return [pad+i*step, pad+(H-2*pad)*(1-(p[1]-lo)/span)]; }});
    var line = xy.map(function(c){{ return c[0].toFixed(1)+","+c[1].toFixed(1); }}).join(" ");
    var area = line + " " + (W-pad).toFixed(1)+","+(H-pad) + " " + pad+","+(H-pad);
    var l = xy[xy.length-1];
    document.getElementById("chart").innerHTML = '<svg viewBox="0 0 '+W+' '+H+'" preserveAspectRatio="none">'
      + '<polygon points="'+area+'" fill="#37659E" fill-opacity="0.08"/>'
      + '<polyline points="'+line+'" fill="none" stroke="#37659E" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>'
      + '<circle cx="'+l[0].toFixed(1)+'" cy="'+l[1].toFixed(1)+'" r="3.5" fill="#1E4566"/></svg>';
  }}).catch(function(){{}});
}})();
</script>
</body>
</html>
"""


def render_rankings_index(ranking_pages, rankings_meta):
    """/rankings: the way in from the ribbon. Every ranking, each with who
    currently leads it, so the page answers something on its own rather than
    being a menu."""
    canonical = f"{SITE_URL}/rankings"
    cards = []
    for rk, rows, _unranked in ranking_pages:
        top = rows[0]
        cards.append(
            f'<a class="rkx-card" href="{rk["slug"]}">'
            f'<span class="rkx-name">{esc(rk["title"].replace(" by Country", ""))}</span>'
            f'<span class="rkx-lead"><span class="rkx-val">{esc(top["value_str"])}</span>'
            f'<span class="rkx-who">{esc(top["country"])}, {esc(fmt_period_label(top["period"]))}</span></span>'
            f'<span class="rkx-meta">{len(rows)} countries &middot; {esc(rk["col"])}</span>'
            f'{ARROW_SVG}</a>')
    page_title = "Economic Rankings by Country: GDP, Inflation, Debt and More | The Economic Atlas"
    meta_desc = ("Every country we track, ranked on the indicators that can be compared like for like: GDP, growth, "
                 "inflation, unemployment, interest rates, bond yields, government debt, budget balance, the current "
                 "account, FDI and business confidence.")
    jsonld = json.dumps({
        "@context": "https://schema.org", "@type": "CollectionPage",
        "name": "Economic Rankings by Country", "description": meta_desc, "url": canonical,
        "hasPart": [{"@type": "Dataset", "name": rk["title"], "url": f"{SITE_URL}/rankings/{rk['slug']}"}
                    for rk, _r, _u in ranking_pages],
    }, ensure_ascii=False, indent=2)
    html_out = head_html(page_title, meta_desc, canonical, f"{SITE_URL}/og/rankings-{ranking_pages[0][0]['slug']}.png", jsonld)
    # No ribbon item is marked active anywhere else on the site (Compare
    # doesn't highlight itself either), so these pages don't either.
    html_out += HEADER_HTML_BASE
    html_out += f"""<main class="ind-wrap rk-wrap">
  <header class="ind-head">
    <h1>Economic Rankings by Country</h1>
    <p class="ind-lede">Every country we track, ranked side by side on the measures that can be compared like for like. Rates and stocks show each country's latest reading; flows such as GDP show the last completed year. Updated hourly from official sources.</p>
  </header>
  <div style="height:26px"></div>
  <div class="rkx-grid">{''.join(cards)}</div>
  {glow_cta("../compare", "Build your own comparison in Compare",
            "Pick any countries, any indicators and any years, then chart, map and rank them side by side.")}
  <p class="rk-unranked">Figures come from national statistics offices, central banks, Eurostat, the OECD, the IMF and the World Bank, the same sources cited on each country's own page. Each ranking names the source behind every country's figure.</p>
</main>
"""
    html_out += page_tail("<script>EATLAS_IND.initRanking();</script>")
    return html_out


def legacy_redirect_html(target_slug):
    url = f"{SITE_URL}/rankings/{target_slug}"
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<title>Moved | The Economic Atlas</title>
<link rel="canonical" href="{url}">
<meta http-equiv="refresh" content="0; url=/rankings/{target_slug}">
<meta name="robots" content="noindex">
</head><body><p>This ranking has moved to <a href="/rankings/{target_slug}">{url}</a>.</p>
<script>location.replace("/rankings/{target_slug}");</script></body></html>
"""


def rewrite_sitemap(urls, today):
    path = os.path.join(ROOT, "sitemap.xml")
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    kept = [l for l in lines if "/indicators/" not in l and "/rankings/" not in l and "</urlset>" not in l]
    new = [f"  <url><loc>{u}</loc><lastmod>{today}</lastmod><changefreq>daily</changefreq></url>" for u in urls]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(kept + new + ["</urlset>"]) + "\n")


def build_all(sources_all):
    catalogue_by_country = {}
    for country, (iso2, cslug, alpha2, region) in COUNTRIES.items():
        path = os.path.join(ROOT, data_file_for(iso2))
        if not os.path.exists(path):
            print(f"  {country}: missing data file, skipped")
            continue
        data = load_json(data_file_for(iso2))
        sources = sources_all.get(country, {})
        cat = build_country_catalogue(country, data, sources)
        catalogue_by_country[country] = dict(data=data, sources=sources, catalogue=cat,
                                             by_slug={e["m"]["slug"]: e for e in cat})

    # rankings first, so indicator pages can say where each country sits
    rank_info, rankings_meta, ranking_pages = {}, [], []
    for rk in RANKINGS:
        rows, unranked = rank_rows(rk, catalogue_by_country)
        if len(rows) < 3:
            print(f"  ranking {rk['slug']}: only {len(rows)} rows, skipped")
            continue
        rank_info[rk["slug"]] = {r["country"]: i for i, r in enumerate(rows, 1)}
        rankings_meta.append(dict(slug=rk["slug"], title=rk["title"], metric=rk["metric"], count=len(rows)))
        ranking_pages.append((rk, rows, unranked))

    return catalogue_by_country, rank_info, rankings_meta, ranking_pages


def main():
    sources_all = load_json("data-metric-sources.json")
    for d in ("indicators", "embed", "og", "rankings"):
        os.makedirs(os.path.join(ROOT, d), exist_ok=True)

    catalogue_by_country, rank_info, rankings_meta, ranking_pages = build_all(sources_all)

    urls, generated = [], 0
    for country, info in catalogue_by_country.items():
        iso2, cslug = COUNTRIES[country][0], COUNTRIES[country][1]
        n = len(info["catalogue"])
        for entry in info["catalogue"]:
            page_slug, html_out = render_indicator(country, info, entry, rank_info, rankings_meta, n)
            with open(os.path.join(ROOT, "indicators", f"{page_slug}.html"), "w", encoding="utf-8") as f:
                f.write(html_out)
            lp = entry["pts"][-1]
            embed = EMBED_TEMPLATE.format(
                country_name=esc(country), metric_title=esc(entry["title"]),
                latest_str=esc(fmt_num(lp[1], entry["unit"], entry["key"], country)),
                latest_period=esc(fmt_period_label(lp[0])), indicator_url=f"{SITE_URL}/indicators/{page_slug}",
                kit_version=KIT_VERSION,
                cfg=json.dumps(dict(dataUrl=f"../{data_file_for(iso2)}", key=entry["key"], unit=entry["unit"], country=country,
                                    annualise=bool(entry["m"].get("ann")), gdpRaw=country in GDP_RAW_COUNTRIES), ensure_ascii=False))
            with open(os.path.join(ROOT, "embed", f"{page_slug}.html"), "w", encoding="utf-8") as f:
                f.write(embed)
            urls.append(f"{SITE_URL}/indicators/{page_slug}")
            generated += 1

    for rk, rows, unranked in ranking_pages:
        with open(os.path.join(ROOT, "rankings", f"{rk['slug']}.html"), "w", encoding="utf-8") as f:
            f.write(render_ranking(rk, rows, unranked, rankings_meta, catalogue_by_country))
        urls.append(f"{SITE_URL}/rankings/{rk['slug']}")

    with open(os.path.join(ROOT, "rankings", "index.html"), "w", encoding="utf-8") as f:
        f.write(render_rankings_index(ranking_pages, rankings_meta))
    urls.append(f"{SITE_URL}/rankings")

    for old, new in LEGACY_RANKING_REDIRECTS.items():
        with open(os.path.join(ROOT, f"{old}.html"), "w", encoding="utf-8") as f:
            f.write(legacy_redirect_html(new))

    # the index other scripts read (country pages' tile links, Compare's buttons)
    manifest = {
        "rankings": rankings_meta,
        "indicators": {c: [e["m"]["slug"] for e in info["catalogue"]] for c, info in catalogue_by_country.items()},
        "keys": {c: {e["key"]: e["m"]["slug"] for e in info["catalogue"]} for c, info in catalogue_by_country.items()},
    }
    with open(os.path.join(ROOT, "indicators", "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)

    rewrite_sitemap(urls, date.today().isoformat())
    print(f"Generated {generated} indicator pages, {generated} embeds and {len(ranking_pages)} rankings.")

if __name__ == "__main__":
    main()
