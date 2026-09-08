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

# Countries whose gdp_level is already USD-denominated at source (US has
# no fx_to_usd block at all; Switzerland's only live GDP source, World
# Bank NY.GDP.MKTP.CD, is USD-native) -- Dollarise would be a silent
# no-op (or worse, a double-conversion) for these, matching the real
# site's isAlreadyUSD() guard, so the toggle is simply not shown there.
GDP_ALREADY_USD = {"US", "Switzerland"}

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

# The historical FX-rate-matching, monthKey and convertSeriesToUSD logic
# below is extracted verbatim from the real site (not reimplemented) --
# including a previously-fixed bug where using today's flat rate instead
# of each point's own contemporaneous rate understated old values by
# double-digit percentages. Embedding it here keeps Dollarise on the
# indicator pages numerically identical to the real country pages.
TOGGLE_HELPERS_JS = r"""
  function monthKey(period){
    var yearMatch = period.match(/^(\d{4})/);
    if(!yearMatch) return null;
    var year = parseInt(yearMatch[1], 10);
    var qMatch = period.match(/^\d{4}-Q([1-4])$/);
    if(qMatch) return year*12 + (parseInt(qMatch[1],10)-1)*3;
    var mMatch = period.match(/^\d{4}-(\d{2})$/);
    if(mMatch) return year*12 + (parseInt(mMatch[1],10)-1);
    return year*12;
  }
  function rateForPeriod(period, history){
    if(!history || !history.length) return null;
    var matches;
    if(/^\d{4}$/.test(period)){
      matches = history.filter(function(h){ return h[0].indexOf(period+"-")===0; });
    } else if(/^\d{4}-Q[1-4]$/.test(period)){
      var parts = period.split("-Q"), y = parts[0], q = parts[1];
      var startMonth = (parseInt(q,10)-1)*3 + 1;
      var wanted = [startMonth, startMonth+1, startMonth+2].map(function(m){ return y+"-"+String(m).padStart(2,"0"); });
      matches = history.filter(function(h){ return wanted.indexOf(h[0])>-1; });
    } else {
      matches = history.filter(function(h){ return h[0]===period; });
    }
    if(matches.length) return matches.reduce(function(sum,h){ return sum+h[1]; }, 0) / matches.length;
    var targetKey = monthKey(period);
    var best = history[0], bestDist = Infinity;
    for(var i=0;i<history.length;i++){
      var dist = Math.abs(monthKey(history[i][0]) - targetKey);
      if(dist < bestDist){ bestDist = dist; best = history[i]; }
    }
    return best[1];
  }
  function convertPtsToUSD(pts, fx){
    return pts.map(function(p){
      var rate = fx.history ? rateForPeriod(p[0], fx.history) : fx.rate;
      var v = fx.direction==="multiply" ? p[1]*rate : p[1]/rate;
      return [p[0], v];
    });
  }
"""

def build_toggle_html_and_js(toggle_data, metric_key, up_is_good, freshness_led_fn, fmt_period_label_fn):
    """Returns (buttons_html, script_js) for the Dollarise/Make it real
    toggles -- empty strings if this metric has neither applicable
    (matching the real site, where these are no-ops for every metric
    except gdp_level)."""
    if not toggle_data:
        return "", ""

    has_real = toggle_data.get("real") is not None
    has_dollar = toggle_data.get("fx") is not None
    if not has_real and not has_dollar:
        return "", ""

    buttons = ['<div class="metric-toggles" aria-label="Display options" style="margin:0 0 20px;">']
    if has_real:
        buttons.append('<button type="button" class="mtoggle" id="indToggleReal" aria-pressed="false">'
                        '<span class="mtoggle-switch" aria-hidden="true"></span>Make it real</button>')
    if has_dollar:
        buttons.append('<button type="button" class="mtoggle" id="indToggleDollar" aria-pressed="false">'
                        '<span class="mtoggle-switch" aria-hidden="true"></span>Dollarise</button>')
    buttons.append('</div>')
    buttons_html = "\n".join(buttons)

    js = TOGGLE_HELPERS_JS + """
  var TOGGLE_STATE = {real: false, dollar: false};
  var NOMINAL_PTS = """ + json.dumps(toggle_data["nominal"]) + """;
  var REAL_PTS = """ + json.dumps(toggle_data.get("real")) + """;
  var FX = """ + json.dumps(toggle_data.get("fx")) + """;
  var BASE_UNIT = """ + json.dumps(toggle_data["unit"]) + """;
  var UP_IS_GOOD = """ + ("true" if up_is_good else "false") + """;
  function usdUnit(u){
    for (var i=0, scales=["bn","m","k"]; i<scales.length; i++){
      var suf = scales[i];
      if(u.slice(-suf.length)===suf && u.length>suf.length) return "$"+suf;
    }
    return "$";
  }
  function currentPtsAndUnit(){
    var pts = TOGGLE_STATE.real && REAL_PTS ? REAL_PTS : NOMINAL_PTS;
    var unitNow = BASE_UNIT;
    if(TOGGLE_STATE.dollar && FX){
      pts = convertPtsToUSD(pts, FX);
      unitNow = usdUnit(BASE_UNIT);
    }
    return {pts: pts, unit: unitNow};
  }
  function updateIndicatorDisplay(){
    var r = currentPtsAndUnit();
    var pts = r.pts, unitNow = r.unit;
    var render = window.EATLAS_INDICATOR_RENDER;
    var latest = pts[pts.length-1], prev = pts[pts.length-2];
    var latestStr = render.curFmt(latest[1], 2, unitNow);
    document.getElementById("indicatorFigure").textContent = latestStr;
    var delta = Math.round((latest[1]-prev[1])*100)/100;
    var dir = delta===0 ? "flat" : ((delta>0)===UP_IS_GOOD ? "good" : "bad");
    var arrow = delta===0 ? "\\u2582" : (delta>0 ? "\\u25b2" : "\\u25bc");
    var deltaStr = render.curFmt(delta, 1, unitNow);
    if(delta > 0) deltaStr = "+" + deltaStr;
    var deltaEl = document.getElementById("indicatorDelta");
    deltaEl.className = "delta " + dir;
    deltaEl.innerHTML = '<span class="arrow" aria-hidden="true">' + arrow + '</span> ' + deltaStr + ' vs prior';
    render.renderChart(pts, unitNow);
  }
  function wireToggle(id, key){
    var btn = document.getElementById(id);
    if(!btn) return;
    btn.addEventListener("click", function(){
      TOGGLE_STATE[key] = !TOGGLE_STATE[key];
      btn.classList.toggle("on", TOGGLE_STATE[key]);
      btn.setAttribute("aria-pressed", TOGGLE_STATE[key] ? "true" : "false");
      updateIndicatorDisplay();
    });
  }
  wireToggle("indToggleReal", "real");
  wireToggle("indToggleDollar", "dollar");
"""
    return buttons_html, js


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
 </div>
 </div>
</div>
<script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2"></script>
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
      authModalSub.textContent = "Free, for now -- this may change in future.";
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
    authSubmitBtn.disabled = true;
    clearMsg(authMsg);
    if(mode === "signup"){
      sb.auth.signUp({ email: email, password: password }).then(function(res){
        authSubmitBtn.disabled = false;
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
      sb.auth.signInWithPassword({ email: email, password: password }).then(function(res){
        authSubmitBtn.disabled = false;
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
    authForgotSubmitBtn.disabled = true;
    clearMsg(authForgotMsg);
    sb.auth.resetPasswordForEmail(email).then(function(res){
      authForgotSubmitBtn.disabled = false;
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
    authResetSubmitBtn.disabled = true;
    clearMsg(authResetMsg);
    sb.auth.updateUser({ password: password }).then(function(res){
      authResetSubmitBtn.disabled = false;
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
    sb.auth.signOut().then(function(){
      closeAuthModal();
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
<link rel="stylesheet" href="../mobile.css?v=10">
<style>
  .indicator-wrap{{max-width:760px;margin:0 auto;padding:32px 24px 64px}}
  .indicator-crumb{{margin-bottom:18px}}
  .indicator-backbtn{{border:1px solid var(--hair); background:var(--panel); color:var(--ink);
    font:700 13px "Avenir Next","Avenir","Nunito Sans",sans-serif; padding:7px 14px; border-radius:999px;
    text-decoration:none; display:inline-flex; align-items:center; gap:6px;}}
  .indicator-backbtn:hover{{border-color:var(--blue); color:var(--navy);}}
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
  <p class="indicator-crumb"><a class="indicator-backbtn" href="../{country_slug}">&larr; {country_name} overview</a></p>
  <div class="indicator-hero">
    <h1>{country_name} {metric_title}</h1>
  </div>
{toggle_buttons_html}
  <div class="hero" style="margin:0 0 22px;justify-content:flex-start;">
    <div class="stat" style="max-width:320px;">
      <p class="label">Latest</p>
      <p class="figure"><span class="led {led}" id="indicatorLed" title="{led_title}" role="img" aria-label="{led_title}"></span><span id="indicatorFigure">{latest_str}</span></p>
      <p class="delta {delta_dir}" id="indicatorDelta"><span class="arrow" aria-hidden="true">{delta_arrow}</span> {delta_display} vs prior</p>
      <p class="period" id="indicatorPeriod">{latest_period} &middot; updated {updated}</p>
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
  var nominalPts = {chart_points};
  var unit = {unit_json};
  var cs = getComputedStyle(document.documentElement);
  var INK = cs.getPropertyValue("--ink").trim() || "#171B1E";
  var INK2 = cs.getPropertyValue("--ink2").trim() || "#5A6167";
  var HAIR = cs.getPropertyValue("--hair").trim() || "#E7E9E4";
  var PANEL_BG = cs.getPropertyValue("--panel").trim() || "#fff";
  var LINE = "#37659E";
  var FONT = {{family: "'Avenir Next','Nunito Sans',sans-serif", size: 11.5}};
  function curFmt(raw, decimals, unitOverride){{
    var u = unitOverride || unit;
    if(u.indexOf("%") > -1) return raw.toFixed(1) + "%";
    var scales = [["bn",1e9],["m",1e6],["k",1e3]], symbol = u, mult = 1;
    for(var i=0;i<scales.length;i++){{
      var suf = scales[i][0];
      if(u.slice(-suf.length) === suf && u.length > suf.length){{ symbol = u.slice(0,-suf.length); mult = scales[i][1]; break; }}
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
  var chart = null;
  function renderChart(pts, unitForChart){{
    var canvas = document.getElementById("indicatorChart");
    if(chart){{ chart.destroy(); chart = null; }}
    chart = new Chart(canvas, {{
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
            callbacks: {{ label: function(ctx){{ return curFmt(ctx.parsed.y, 2, unitForChart); }} }}
          }}
        }},
        scales: {{
          x: {{grid: {{display: false}}, border: {{color: HAIR}}, ticks: {{color: INK2, font: FONT, maxTicksLimit: 7, maxRotation: 0,
               callback: function(v){{ return yearOf(this.getLabelForValue(v)); }} }}}},
          y: {{grid: {{color: HAIR}}, border: {{display: false}}, ticks: {{color: INK2, font: FONT, maxTicksLimit: 6,
               callback: function(v){{ return curFmt(v, 1, unitForChart); }} }}}}
        }}
      }}
    }});
  }}
  renderChart(nominalPts, unit);
  window.EATLAS_INDICATOR_RENDER = {{renderChart: renderChart, curFmt: curFmt, nominalPts: nominalPts, unit: unit}};
}})();
</script>
{toggle_block}
<script src="../mobile.js?v=10"></script>
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

            # Dollarise / Make it real: only meaningfully apply to gdp_level
            # (the real site's own buildDisplaySeries() only swaps gdp_real
            # in for "real terms", and Dollarise only converts currency-
            # denominated series -- the other 3 core metrics here are all
            # percentages, which the real toggles don't touch either).
            toggle_data = None
            if metric_key == "gdp_level":
                real_series = series.get("gdp_real")
                real_pts = None
                if real_series:
                    rp = [p for p in real_series.get("points", []) if p[1] is not None]
                    rp = annualize_gdp_points(rp, real_series.get("freq", ""), country_name)
                    if len(rp) >= 2:
                        real_pts = rp
                fx = data.get("fx_to_usd") if country_name not in GDP_ALREADY_USD else None
                if real_pts or fx:
                    toggle_data = {
                        "nominal": pts, "real": real_pts, "unit": unit,
                        "fx": fx,
                    }

            latest_period, latest_val = pts[-1]
            prev_val = pts[-2][1]
            latest_str = fmt_value(latest_val, unit)

            delta = round(latest_val - prev_val, 2)
            up_is_good = UP_IS_GOOD.get(metric_key, True)
            # Arrow direction and good/bad colour are independent, matching
            # the real site's statTile() exactly: arrow follows the actual
            # sign of the change; dir/colour follows whether that direction
            # is favourable for this metric. Conflating the two (an earlier
            # version of this script) made "inflation fell" render with an
            # up-arrow just because falling inflation is good news.
            delta_dir = "flat" if delta == 0 else ("good" if (delta > 0) == up_is_good else "bad")
            delta_arrow = "\u2582" if delta == 0 else ("\u25b2" if delta > 0 else "\u25bc")
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

            toggle_buttons_html, toggle_js = build_toggle_html_and_js(
                toggle_data, metric_key, up_is_good, freshness_led, fmt_period_label
            )
            toggle_block = f"<script>\n(function(){{\n{toggle_js}\n}})();\n</script>" if toggle_js else ""

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
                toggle_buttons_html=toggle_buttons_html, toggle_block=toggle_block,
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
