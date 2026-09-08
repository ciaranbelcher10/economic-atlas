#!/usr/bin/env python3
"""
generate_indicator_pages.py

Generates programmatic per-country-per-indicator SEO landing pages
(/indicators/{country}-{metric}.html) and matching embeddable widget
pages (/embed/{country}-{metric}.html) for The Economic Atlas.

Run this from the repo root, after the hourly fetch scripts have
refreshed data-*.json, so generated pages reflect current data:

    python3 generate_indicator_pages.py

Outputs:
    /indicators/*.html   - one SEO landing page per country x metric
    /embed/*.html        - one embeddable widget page per country x metric
    /og/*.svg            - one social-share card per country x metric
    /indicators/sitemap-fragment.xml   - <url> entries to append to sitemap.xml

Safe to re-run any time (idempotent, overwrites its own output only).
Does NOT touch any existing site file outside /indicators, /embed, /og.

To add more indicators later: extend CORE_METRICS below. Every metric
key must exist in data-metric-sources.json under the country's entry
(for source/description text) - if it's missing there, that
country/metric pair is silently skipped rather than shipping with
placeholder text.
"""
import json, os, re, html as htmllib
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.abspath(__file__))
SITE_URL = "https://theeconomicatlas.com"

# country display name (as keyed in data-metric-sources.json) -> (iso2 data-file code, html page slug, flag alpha-2)
COUNTRIES = {
    "UK":            ("uk", "uk", "GB"),
    "US":            ("us", "us", "US"),
    "Argentina":     ("ar", "argentina", "AR"),
    "Australia":     ("au", "australia", "AU"),
    "Austria":       ("at", "austria", "AT"),
    "Brazil":        ("br", "brazil", "BR"),
    "Canada":        ("ca", "canada", "CA"),
    "Chile":         ("cl", "chile", "CL"),
    "Colombia":      ("co", "colombia", "CO"),
    "Denmark":       ("dk", "denmark", "DK"),
    "Eurozone":      ("ez", "eurozone", "EU"),
    "France":        ("fr", "france", "FR"),
    "Germany":       ("de", "germany", "DE"),
    "India":         ("in", "india", "IN"),
    "Indonesia":     ("id", "indonesia", "ID"),
    "Ireland":       ("ie", "ireland", "IE"),
    "Israel":        ("il", "israel", "IL"),
    "Italy":         ("it", "italy", "IT"),
    "Japan":         ("jp", "japan", "JP"),
    "Mexico":        ("mx", "mexico", "MX"),
    "Morocco":       ("ma", "morocco", "MA"),
    "Netherlands":   ("nl", "netherlands", "NL"),
    "Norway":        ("no", "norway", "NO"),
    "Poland":        ("pl", "poland", "PL"),
    "Singapore":     ("sg", "singapore", "SG"),
    "South Africa":  ("za", "southafrica", "ZA"),
    "South Korea":   ("kr", "southkorea", "KR"),
    "Spain":         ("es", "spain", "ES"),
    "Sweden":        ("se", "sweden", "SE"),
    "Switzerland":   ("ch", "switzerland", "CH"),
    "Thailand":      ("th", "thailand", "TH"),
    "Turkey":        ("tr", "turkey", "TR"),
}

# metric key (as in series/data-metric-sources.json) -> (url slug, short public title, search-friendly H1 suffix)
CORE_METRICS = {
    "gdp_level":   ("gdp",          "GDP"),
    "cpi":         ("inflation-rate", "Inflation Rate (CPI)"),
    "unemployment":("unemployment-rate", "Unemployment Rate"),
    "debt_gdp":    ("government-debt", "Government Debt (% of GDP)"),
}

# Matches each metric's real statTile() upIsGood setting on the actual
# country pages exactly (checked uk.html's real call sites) -- controls
# whether the delta arrow renders green (good) or red (bad) on an increase.
UP_IS_GOOD = {"gdp_level": True, "cpi": False, "unemployment": False, "debt_gdp": False}

# Matches the real site's STALE_DAYS thresholds exactly (used to decide
# the freshness LED colour on the LATEST card).
STALE_DAYS = {"months": 75, "quarters": 150, "years": 660}

MONTH_NAMES = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

def fmt_period_label(period):
    """Python port of the real site's fmtPeriod(): '2026-Q2' -> 'Q2 2026',
    '2026-05' -> 'May 2026', '2026' stays '2026'."""
    m = re.match(r"^(\d{4})-(\d{2})$", period)
    if m:
        year, mon = m.groups()
        return f"{MONTH_NAMES[int(mon)-1]} {year}"
    m = re.match(r"^(\d{4})-Q(\d)$", period)
    if m:
        year, q = m.groups()
        return f"Q{q} {year}"
    return period

def period_end_date(period):
    """Python port of the real site's periodEnd()."""
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

def freshness_led(latest_period, freq):
    """Python port of the real site's freshness(): green if within the
    normal stale-days window for this frequency, orange otherwise."""
    age_days = (date.today() - period_end_date(latest_period)).days
    threshold = STALE_DAYS.get(freq, 90)
    return "green" if age_days <= threshold else "orange"

def cur_fmt(raw_value, unit, decimals=2):
    """Python port of the real site's curFmt() -- NOT the same as
    fmt_value() below (that one is for the headline OG/meta figure and
    uses comma grouping); this one matches the live chart-axis/tile
    formatting exactly, decimal-only, no thousands separator.

    Also trims unnecessary trailing zeros (100.0bn -> 100bn), matching
    the site's own czTrimAxisZeros used in Customise & Export -- this
    port applies the same trim, and the real curFmt() on every country
    page was updated to do the same so tooltips/deltas/axis ticks match."""
    scale_map = [("bn", 1_000_000_000), ("m", 1_000_000), ("k", 1_000)]
    symbol, mult = unit, 1
    for suf, m in scale_map:
        if unit.endswith(suf) and len(unit) > len(suf):
            symbol, mult = unit[:-len(suf)], m
            break
    a = abs(raw_value) * mult
    sign = "\u2212" if raw_value < 0 else ""
    if a >= 1e12:
        out = f"{sign}{symbol}{a/1e12:.{decimals}f}tn"
    elif a >= 1e9:
        out = f"{sign}{symbol}{a/1e9:.{decimals}f}bn"
    else:
        out = f"{sign}{symbol}{a/1e6:.0f}m"
    return re.sub(r"(\.\d*[1-9])0+(?!\d)|\.0+(?!\d)", lambda m: m.group(1) or "", out)


# The real site does NOT display gdp_level raw for most countries -- every
# country page except US calls a client-side annualGDP() that sums the
# trailing 4 quarters, because their gdp_level series is a genuine
# per-quarter flow, not an annualized rate. US's own gdp_level ("GDP,
# nominal SAAR") is already published at a seasonally-adjusted ANNUAL
# rate, so it's used raw there and would be ~4x inflated if summed.
# Confirmed by inspecting every country page's actual statTile() call for
# gdp_level (see the "GDP (annual)" vs "GDP (annual rate)" label + whether
# it feeds through the gdpAnnual variable or s.gdp_level directly).
GDP_RAW_COUNTRIES = {"US"}

def annualize_gdp_points(points, freq, country_name):
    """Match the real site's annualGDP(): trailing 4-quarter sum for
    quarterly series (except US, which is already an annual rate),
    no-op for annual-frequency series."""
    if country_name in GDP_RAW_COUNTRIES or freq == "years":
        return points
    out = []
    for i in range(3, len(points)):
        window = points[i-3:i+1]
        if any(w[1] is None for w in window):
            continue
        out.append([points[i][0], sum(w[1] for w in window)])
    return out


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
"""

FOOTER_HTML = """<footer>
 Data from official national and international statistics sources. Series codes are shown with each metric;
 figures are the latest published observations and are subject to revision.
 Ideas or corrections: <a href="../contact">get in touch</a>. <a href="../privacy">Privacy</a> &middot; <a href="../terms">Terms</a>.
</footer>
<script>
(function(){
  var btn = document.getElementById("themeToggle");
  if(!btn) return;
  btn.addEventListener("click", function(){
    var isDark = document.documentElement.getAttribute("data-theme") === "dark";
    if(isDark){ document.documentElement.removeAttribute("data-theme"); try{localStorage.setItem("eatlas_theme","light");}catch(e){} }
    else{ document.documentElement.setAttribute("data-theme","dark"); try{localStorage.setItem("eatlas_theme","dark");}catch(e){} }
  });
})();
</script>
"""

def flag_emoji(alpha2):
    return "".join(chr(0x1F1E6 + ord(c) - 65) for c in alpha2.upper())

def header_for(slug):
    """Marks the current country's own link active in the real nav's
    country mega-menu, matching how every real country page marks
    itself, without needing 32 separate copies of the nav markup."""
    return HEADER_HTML_BASE.replace(f'href="../{slug}"', f'href="../{slug}" class="active"', 1)

def load_json(name):
    path = os.path.join(ROOT, name)
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def esc(s):
    return htmllib.escape(str(s), quote=True)

def fmt_value(v, unit):
    if v is None:
        return "N/A"
    unit = unit or ""
    if "%" in unit:
        return f"{v:.1f}%"

    # Unit strings on this site encode a currency/index symbol plus an
    # existing scale suffix (e.g. "£m" = millions of pounds, "IDRm" =
    # millions of rupiah, "$bn" = billions of dollars). Fold that into
    # the raw number first so we can re-express the combined magnitude
    # with a single clean suffix (k/m/bn/tn) instead of a wall of digits.
    scale_map = [("bn", 1_000_000_000), ("m", 1_000_000), ("k", 1_000)]
    currency = unit
    multiplier = 1
    for suffix, mult in scale_map:
        if unit.endswith(suffix) and len(unit) > len(suffix):
            currency = unit[: -len(suffix)]
            multiplier = mult
            break

    try:
        absolute = v * multiplier
    except TypeError:
        return f"{v} {unit}".strip()

    for suffix, mult in [("tn", 1_000_000_000_000), ("bn", 1_000_000_000), ("m", 1_000_000), ("k", 1_000)]:
        if abs(absolute) >= mult:
            out = f"{currency}{absolute / mult:,.2f}{suffix}".strip()
            return re.sub(r"(\.\d*[1-9])0+(?!\d)|\.0+(?!\d)", lambda m: m.group(1) or "", out)
    if currency:
        out = f"{currency}{absolute:,.2f}".strip()
        return re.sub(r"(\.\d*[1-9])0+(?!\d)|\.0+(?!\d)", lambda m: m.group(1) or "", out)
    return re.sub(r"(\.\d*[1-9])0+(?!\d)|\.0+(?!\d)", lambda m: m.group(1) or "", f"{absolute:,.2f}")

def sparkline_points_js(points):
    """Return a JS array literal of [period, value] pairs for Chart.js."""
    return json.dumps(points, ensure_ascii=False)

INDICATOR_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title_tag}</title>
<meta name="description" content="{meta_desc}">
<link rel="canonical" href="{canonical}">
<meta property="og:type" content="website">
<meta property="og:title" content="{og_title}">
<meta property="og:description" content="{meta_desc}">
<meta property="og:image" content="{og_image}">
<meta property="og:url" content="{canonical}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{og_title}">
<meta name="twitter:description" content="{meta_desc}">
<meta name="twitter:image" content="{og_image}">
<link rel="icon" type="image/png" sizes="32x32" href="../favicon-32.png">
<link rel="apple-touch-icon" href="../apple-touch-icon.png">
<link rel="stylesheet" href="../style.css?v=51">
<style>
  .indicator-wrap{{max-width:760px;margin:0 auto;padding:32px 24px 64px}}
  .indicator-crumb{{font-size:13px;margin-bottom:18px}}
  .indicator-crumb a{{color:var(--blue)}}
  .indicator-hero{{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;margin-bottom:18px}}
  .indicator-hero h1{{font-size:22px;font-weight:700;margin:0}}
  .indicator-links{{display:flex;gap:12px;flex-wrap:wrap;margin-top:24px}}
  .indicator-links a{{display:inline-block;padding:10px 18px;border-radius:8px;border:1px solid var(--hair);text-decoration:none;color:var(--ink);font-weight:600;font-size:14px}}
  .indicator-links a.primary{{background:var(--navy);color:#fff;border-color:var(--navy)}}
  .indicator-related{{margin-top:36px}}
  .indicator-related h2{{font-size:13px;font-weight:600;letter-spacing:.09em;text-transform:uppercase;color:var(--ink2)}}
  .indicator-related a{{display:block;padding:9px 0;border-bottom:1px solid var(--hair);text-decoration:none;color:var(--blue);font-size:14.5px}}
  /* Golden ratio (1.618:1) chart box, matching ChartMaker's own
     .cm-chart-outer proportions and generous padding, rather than the
     country pages' fixed 250px .chartbox -- this page is meant to be a
     single polished centerpiece, so it gets the more premium treatment. */
  .indicator-chart-outer{{position:relative;width:100%;aspect-ratio:1.618/1;border-radius:8px;border:1px solid var(--hair);background:var(--paper);}}
  .indicator-panel{{padding:28px 30px 24px !important;}}
</style>
<script type="application/ld+json">
{jsonld}
</script>
</head>
<body>
{header}
<main class="indicator-wrap">
  <p class="indicator-crumb"><a href="../{country_slug}">&larr; {country_name} overview</a></p>
  <div class="indicator-hero">
    <h1>{country_name} {metric_title}</h1>
  </div>

  <div class="hero" style="margin:0 0 22px;justify-content:flex-start;">
    <div class="stat" style="max-width:320px;">
      <p class="label">Latest</p>
      <p class="figure"><span class="led {led}" title="{led_title}" role="img" aria-label="{led_title}"></span>{latest_str}</p>
      <p class="delta {delta_dir}"><span class="arrow" aria-hidden="true">{delta_arrow}</span> {delta_display} vs prior</p>
      <p class="period">{latest_period} &middot; updated {updated}</p>
    </div>
  </div>

  <div class="panel indicator-panel">
    <div class="panelhead"><h2>{metric_title}</h2></div>
    <p class="range">{first_period} to {latest_period}</p>
    <div class="indicator-chart-outer"><canvas id="indicatorChart" role="img" aria-label="{country_name} {metric_title}, {first_period} to {latest_period}"></canvas></div>
    <p class="src">Source: {source}</p>
  </div>

  <p style="line-height:1.6;margin:22px 0 0;">{description}</p>

  <div class="indicator-links">
    <a class="primary" href="../{country_slug}">View full {country_name} data</a>
    <a href="../compare">Compare with other countries</a>
    <a href="../embed/{slug}">Embed this chart &#8599;</a>
  </div>

  <div class="indicator-related">
    <h2>Other {country_name} indicators</h2>
    {related_links}
  </div>
</main>
{footer}
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<script>
(function(){{
  var pts = {chart_points};
  var unit = {unit_json};
  var cs = getComputedStyle(document.documentElement);
  var INK = cs.getPropertyValue("--ink").trim() || "#171B1E";
  var INK2 = cs.getPropertyValue("--ink2").trim() || "#5A6167";
  var HAIR = cs.getPropertyValue("--hair").trim() || "#E7E9E4";
  var PANEL_BG = cs.getPropertyValue("--panel").trim() || "#fff";
  var LINE = "#37659E";
  var FONT = {{family: "'Avenir Next','Nunito Sans',sans-serif", size: 11.5}};
  function curFmt(raw, decimals){{
    if(unit.indexOf("%") > -1) return raw.toFixed(1) + "%";
    var scales = [["bn",1e9],["m",1e6],["k",1e3]], symbol = unit, mult = 1;
    for(var i=0;i<scales.length;i++){{
      var suf = scales[i][0];
      if(unit.slice(-suf.length) === suf && unit.length > suf.length){{ symbol = unit.slice(0,-suf.length); mult = scales[i][1]; break; }}
    }}
    var a = Math.abs(raw) * mult, sign = raw < 0 ? "\\u2212" : "";
    var out;
    if(a >= 1e12) out = sign + symbol + (a/1e12).toFixed(decimals) + "tn";
    else if(a >= 1e9) out = sign + symbol + (a/1e9).toFixed(decimals) + "bn";
    else out = sign + symbol + (a/1e6).toFixed(0) + "m";
    // Same trim as the site's own czTrimAxisZeros / curFmt: no unnecessary trailing zeros.
    return out.replace(/(\\.\\d*[1-9])0+(?!\\d)|\\.0+(?!\\d)/, function(m, keep){{ return keep || ""; }});
  }}
  function yearOf(label){{
    var m = /^(\\d{{4}})/.exec(label);
    return m ? m[1] : label;
  }}
  var canvas = document.getElementById("indicatorChart");
  new Chart(canvas, {{
    type: "line",
    data: {{
      labels: pts.map(function(p){{return p[0];}}),
      datasets: [{{
        data: pts.map(function(p){{return p[1];}}),
        borderColor: LINE, borderWidth: 2, pointRadius: 0, pointHitRadius: 8, tension: 0.25
      }}]
    }},
    options: {{
      responsive: true, maintainAspectRatio: false, animation: false,
      interaction: {{mode: "index", intersect: false}},
      plugins: {{
        legend: {{display: false}},
        tooltip: {{
          backgroundColor: PANEL_BG, titleColor: INK, bodyColor: INK, borderColor: HAIR, borderWidth: 1,
          titleFont: {{family: FONT.family, weight: "600"}}, bodyFont: {{family: FONT.family}}, displayColors: false,
          callbacks: {{ label: function(ctx){{ return curFmt(ctx.parsed.y, 2); }} }}
        }}
      }},
      scales: {{
        x: {{grid: {{display: false}}, border: {{color: HAIR}}, ticks: {{color: INK2, font: FONT, maxTicksLimit: 7, maxRotation: 0,
             callback: function(v){{ return yearOf(this.getLabelForValue(v)); }} }}}},
        y: {{grid: {{color: HAIR}}, border: {{display: false}}, ticks: {{color: INK2, font: FONT, maxTicksLimit: 6,
             callback: function(v){{ return curFmt(v, 1); }} }}}}
      }}
    }}
  }});
}})();
</script>
</body>
</html>
"""


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
  /* Standalone (opened directly, not inside an iframe) gets a centred,
     bounded presentation so it doesn't look like a broken full-width
     page. Genuinely embedded (window !== window.top) fills its iframe
     edge-to-edge instead, since the host page controls sizing there. */
  body.standalone{{background:#F5F6F3;min-height:100vh;display:flex;align-items:flex-start;justify-content:center;padding:40px 20px;}}
  .w{{padding:18px 20px 14px;border:1px solid #E4E6E1;border-radius:12px;max-width:100%;background:#fff;box-shadow:0 1px 2px rgba(0,0,0,.04);}}
  body.standalone .w{{width:380px;box-shadow:0 2px 12px rgba(0,0,0,.06);}}
  .w-head{{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px}}
  .w-title{{font-size:.82rem;font-weight:700;opacity:.7;letter-spacing:.01em}}
  .w-value{{font-size:1.9rem;font-weight:700;margin:2px 0;color:#171B1E}}
  .w-period{{font-size:.72rem;opacity:.55;margin-bottom:10px}}
  .w-chart-outer{{width:100%;aspect-ratio:1.618/1;position:relative;}}
  .w-badge{{display:flex;align-items:center;gap:5px;font-size:.72rem;opacity:.6;text-decoration:none;color:#171B1E;margin-top:10px}}
  .w-badge:hover{{opacity:1}}
  #chart svg{{display:block;width:100%;height:100%}}
</style>
</head>
<body>
<div class="w">
  <div class="w-head"><span class="w-title">{flag} {country_name} &middot; {metric_title}</span></div>
  <div class="w-value" id="val">&hellip;</div>
  <div class="w-period" id="per"></div>
  <div class="w-chart-outer" id="chart"></div>
  <a class="w-badge" href="{indicator_url}" target="_blank" rel="noopener">Powered by The Economic Atlas &#8594;</a>
</div>
<script>
if(window.self === window.top){{ document.body.classList.add("standalone"); }}
</script>
<script>
(function(){{
  fetch("{data_url}").then(function(r){{return r.json();}}).then(function(d){{
    var s = d.series && d.series["{metric_key}"];
    if(!s || !s.points || !s.points.length) return;
    var rawPts = s.points;
    var isGdp = "{metric_key}" === "gdp_level";
    var gdpNeedsSum = isGdp && {gdp_needs_sum} && s.freq !== "years";
    var fullPts = rawPts;
    if(gdpNeedsSum){{
      fullPts = [];
      for(var gi=3; gi<rawPts.length; gi++){{
        var w = rawPts.slice(gi-3, gi+1);
        if(w.some(function(p){{return p[1]==null;}})) continue;
        fullPts.push([rawPts[gi][0], w.reduce(function(sum,p){{return sum+p[1];}},0)]);
      }}
    }}
    var pts = fullPts.slice(-24);
    if(!pts.length) return;
    var last = pts[pts.length-1];
    var unit = s.unit || "";
    var v = last[1];
    function fmtValue(v, unit){{
      unit = unit || "";
      if(unit.indexOf("%") > -1) return v.toFixed(1) + "%";
      var scales = [["bn",1e9],["m",1e6],["k",1e3]], currency = unit, mult = 1;
      for(var i=0;i<scales.length;i++){{
        var suf = scales[i][0];
        if(unit.slice(-suf.length) === suf && unit.length > suf.length){{ currency = unit.slice(0,-suf.length); mult = scales[i][1]; break; }}
      }}
      var abs = v * mult;
      var big = [["tn",1e12],["bn",1e9],["m",1e6],["k",1e3]];
      var out = null;
      for(var j=0;j<big.length;j++){{
        if(Math.abs(abs) >= big[j][1]){{ out = currency + (abs/big[j][1]).toLocaleString(undefined,{{minimumFractionDigits:2,maximumFractionDigits:2}}) + big[j][0]; break; }}
      }}
      if(out === null) out = currency + abs.toLocaleString(undefined,{{minimumFractionDigits:2,maximumFractionDigits:2}});
      return out.replace(/(\\.\\d*[1-9])0+(?!\\d)|\\.0+(?!\\d)/, function(m, keep){{ return keep || ""; }});
    }}
    var vs = fmtValue(v, unit);
    document.getElementById("val").textContent = vs;
    document.getElementById("per").textContent = "Latest: " + last[0];
    var vals = pts.map(function(p){{return p[1];}}).filter(function(v){{return v!==null;}});
    if(vals.length<2) return;
    var lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals), span=(hi-lo)||1;
    var W=340,H=210,pad=6,n=pts.length,step=(W-2*pad)/(n-1);
    var coords = pts.map(function(p,i){{
      var x = pad + i*step, y = pad + (H-2*pad)*(1-(p[1]-lo)/span);
      return [x,y];
    }});
    var lineStr = coords.map(function(c){{return c[0].toFixed(1)+","+c[1].toFixed(1);}}).join(" ");
    var areaStr = lineStr + " " + (W-pad).toFixed(1)+","+(H-pad).toFixed(1) + " " + pad.toFixed(1)+","+(H-pad).toFixed(1);
    var lastC = coords[coords.length-1];
    document.getElementById("chart").innerHTML =
      '<svg viewBox="0 0 '+W+' '+H+'" preserveAspectRatio="none">' +
      '<polygon points="'+areaStr+'" fill="#37659E" fill-opacity="0.08"/>' +
      '<polyline points="'+lineStr+'" fill="none" stroke="#37659E" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>' +
      '<circle cx="'+lastC[0].toFixed(1)+'" cy="'+lastC[1].toFixed(1)+'" r="3.5" fill="#1E4566"/>' +
      '</svg>';
  }}).catch(function(){{}});
}})();
</script>
</body>
</html>
"""

def main():
    sources = load_json("data-metric-sources.json")
    out_indicators = os.path.join(ROOT, "indicators")
    out_embed = os.path.join(ROOT, "embed")
    out_og = os.path.join(ROOT, "og")
    os.makedirs(out_indicators, exist_ok=True)
    os.makedirs(out_embed, exist_ok=True)
    os.makedirs(out_og, exist_ok=True)

    sitemap_entries = []
    generated = 0
    skipped = []

    for country_name, (iso2, slug, alpha2) in COUNTRIES.items():
        data_file = "data.json" if iso2 == "uk" else f"data-{iso2}.json"
        data_path = os.path.join(ROOT, data_file)
        if not os.path.exists(data_path):
            skipped.append((country_name, "ALL", "missing data file"))
            continue
        data = load_json(data_file)
        series = data.get("series", {})
        updated = data.get("updated", "")[:10]
        flag = flag_emoji(alpha2)
        country_sources = sources.get(country_name, {})

        available_metrics = [m for m in CORE_METRICS if m in series and m in country_sources]

        for metric_key in CORE_METRICS:
            metric_slug, metric_title = CORE_METRICS[metric_key]
            if metric_key not in series:
                skipped.append((country_name, metric_key, "no series data"))
                continue
            if metric_key not in country_sources:
                skipped.append((country_name, metric_key, "no source citation on file"))
                continue

            s = series[metric_key]
            pts = [p for p in s.get("points", []) if p[1] is not None]
            if metric_key == "gdp_level":
                pts = annualize_gdp_points(pts, s.get("freq", ""), country_name)
            if len(pts) < 2:
                skipped.append((country_name, metric_key, "insufficient points"))
                continue
            unit = s.get("unit", "")
            latest_period, latest_val = pts[-1]
            prev_val = pts[-2][1]
            latest_str = fmt_value(latest_val, unit)

            delta = round(latest_val - prev_val, 2)
            up_is_good = UP_IS_GOOD.get(metric_key, True)
            if delta == 0:
                delta_dir, delta_arrow = "flat", "\u2582"
            elif (delta > 0) == up_is_good:
                delta_dir, delta_arrow = "good", "\u25b2"
            else:
                delta_dir, delta_arrow = "bad", "\u25bc"
            delta_str = cur_fmt(delta, unit, 1) if ("%" not in unit) else f"{abs(delta):.1f}pp"
            delta_sign = "+" if delta > 0 else ("\u2212" if delta < 0 else "")
            delta_display = f"{delta_sign}{delta_str.lstrip(chr(0x2212))}" if "%" not in unit else f"{delta_sign}{delta_str}"

            led = freshness_led(latest_period, s.get("freq", ""))
            led_title = "Updated on schedule" if led == "green" else f"Awaiting next release \u00b7 last data {fmt_period_label(latest_period)}"

            first_period_label = fmt_period_label(pts[0][0])
            latest_period_label = fmt_period_label(latest_period)

            meta = country_sources[metric_key]
            description = meta.get("description", "")
            source_text = meta.get("source", "")

            page_slug = f"{slug}-{metric_slug}"
            canonical = f"{SITE_URL}/indicators/{page_slug}"
            og_image = f"{SITE_URL}/og/{page_slug}.png"
            data_url = f"../{data_file}"
            indicator_url = canonical

            meta_label = re.sub(r"\s*\([^)]*\)", "", metric_title).strip().lower()
            title_tag = f"{country_name} {metric_title} \u00b7 Live Data & History | The Economic Atlas"
            og_title = f"{country_name} {metric_title}: {latest_str}"
            meta_desc = f"{country_name} {meta_label}: {latest_str} as of {latest_period}. {description}".strip()
            if len(meta_desc) > 300:
                meta_desc = meta_desc[:297] + "..."

            chart_pts = pts[-200:]  # cap chart payload; still plenty of history for a trend view
            chart_points_js = sparkline_points_js(chart_pts)

            jsonld = json.dumps({
                "@context": "https://schema.org",
                "@type": "Dataset",
                "name": f"{country_name} {metric_title}",
                "description": description,
                "url": canonical,
                "temporalCoverage": f"{pts[0][0]}/{pts[-1][0]}",
                "creator": {"@type": "Organization", "name": "The Economic Atlas", "url": SITE_URL},
                "distribution": {"@type": "DataDownload", "encodingFormat": "JSON", "contentUrl": f"{SITE_URL}/{data_file}"},
                "variableMeasured": metric_title,
            }, ensure_ascii=False, indent=2)

            related = [m for m in available_metrics if m != metric_key]
            related_links = "\n    ".join(
                f'<a href="{slug}-{CORE_METRICS[m][0]}">{country_name} {CORE_METRICS[m][1]}</a>'
                for m in related
            ) or f'<a href="../{slug}">See all {country_name} data &rarr;</a>'

            html_out = INDICATOR_TEMPLATE.format(
                title_tag=esc(title_tag), meta_desc=esc(meta_desc), canonical=canonical,
                og_title=esc(og_title), og_image=og_image, jsonld=jsonld,
                header=header_for(slug), footer=FOOTER_HTML,
                country_slug=slug, flag=flag, country_name=esc(country_name),
                metric_title=esc(metric_title), latest_str=esc(latest_str),
                latest_period=esc(latest_period_label), first_period=esc(first_period_label), updated=esc(updated),
                chart_points=chart_points_js, description=esc(description), source=esc(source_text),
                slug=page_slug, related_links=related_links,
                led=led, led_title=esc(led_title), delta_dir=delta_dir, delta_arrow=delta_arrow,
                delta_display=esc(delta_display), unit=esc(unit), unit_json=json.dumps(unit),
            )
            with open(os.path.join(out_indicators, f"{page_slug}.html"), "w", encoding="utf-8") as f:
                f.write(html_out)

            embed_out = EMBED_TEMPLATE.format(
                country_name=esc(country_name), metric_title=esc(metric_title), flag=flag,
                indicator_url=canonical, data_url=data_url, metric_key=metric_key,
                gdp_needs_sum=("false" if country_name in GDP_RAW_COUNTRIES else "true"),
            )
            with open(os.path.join(out_embed, f"{page_slug}.html"), "w", encoding="utf-8") as f:
                f.write(embed_out)

            sitemap_entries.append(
                f"  <url><loc>{canonical}</loc><lastmod>{updated}</lastmod><changefreq>daily</changefreq></url>"
            )
            generated += 1

    with open(os.path.join(out_indicators, "sitemap-fragment.xml"), "w", encoding="utf-8") as f:
        f.write("\n".join(sitemap_entries) + "\n")

    print(f"Generated {generated} indicator pages + {generated} embed pages.")
    if skipped:
        print(f"Skipped {len(skipped)} country/metric pairs (no data or no citation on file):")
        for c, m, reason in skipped:
            print(f"  {c} / {m}: {reason}")

if __name__ == "__main__":
    main()
