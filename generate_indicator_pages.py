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

HEADER_HTML = """<script>(function(){
  try{
    var saved = localStorage.getItem("eatlas_theme");
    if(saved === "dark" || (!saved && window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches)){
      document.documentElement.setAttribute("data-theme", "dark");
    }
  }catch(e){}
})();</script>
<nav class="top"><div class="wrap">
 <a class="brand" href="../index"><img src="../logo-64.png" alt="" width="26" height="26" style="display:block;border-radius:50%;background:#fff;padding:1px;">The Economic Atlas</a>
 <div class="navlinks" id="navLinks">
 <a href="../compare" style="text-decoration:none;color:inherit;font-weight:600;padding:8px 12px;">Compare</a>
 <a href="../contact" style="text-decoration:none;color:inherit;font-weight:600;padding:8px 12px;">Contact</a>
 <button type="button" class="theme-toggle" id="themeToggle" aria-label="Switch to dark mode" title="Switch to dark mode">&#127769;</button>
 </div>
</div></nav>
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
            return f"{currency}{absolute / mult:,.2f}{suffix}".strip()
    if currency:
        return f"{currency}{absolute:,.2f}".strip()
    return f"{absolute:,.2f}"

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
<link rel="stylesheet" href="../style.css?v=51">
<style>
  .indicator-wrap{{max-width:760px;margin:0 auto;padding:32px 24px 64px}}
  .indicator-crumb{{font-size:13px;margin-bottom:18px}}
  .indicator-crumb a{{color:var(--blue)}}
  .indicator-hero{{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;margin-bottom:18px}}
  .indicator-flag{{font-size:1.8rem;line-height:1}}
  .indicator-hero h1{{font-size:22px;font-weight:700;margin:0}}
  .indicator-links{{display:flex;gap:12px;flex-wrap:wrap;margin-top:24px}}
  .indicator-links a{{display:inline-block;padding:10px 18px;border-radius:8px;border:1px solid var(--hair);text-decoration:none;color:var(--ink);font-weight:600;font-size:14px}}
  .indicator-links a.primary{{background:var(--navy);color:#fff;border-color:var(--navy)}}
  .related{{margin-top:36px}}
  .related h2{{font-size:13px;font-weight:600;letter-spacing:.09em;text-transform:uppercase;color:var(--ink2)}}
  .related a{{display:block;padding:9px 0;border-bottom:1px solid var(--hair);text-decoration:none;color:var(--blue);font-size:14.5px}}
</style>
<script type="application/ld+json">
{jsonld}
</script>
</head>
<body>
{header}
<main class="indicator-wrap">
  <p class="indicator-crumb"><a href="../{country_slug}.html">&larr; {country_name} overview</a></p>
  <div class="indicator-hero">
    <span class="indicator-flag">{flag}</span>
    <h1>{country_name} {metric_title}</h1>
  </div>

  <div class="hero" style="margin:0 0 22px;justify-content:flex-start;">
    <div class="stat" style="max-width:320px;">
      <p class="label">Latest</p>
      <p class="figure">{latest_str}</p>
      <p class="period">{latest_period} &middot; updated {updated}</p>
    </div>
  </div>

  <div class="panel">
    <div class="panelhead"><h2>{metric_title}</h2></div>
    <p class="range">{first_period} to {latest_period}</p>
    <div class="chartbox"><canvas id="indicatorChart" role="img" aria-label="{country_name} {metric_title}, {first_period} to {latest_period}"></canvas></div>
    <p class="src">Source: {source}</p>
  </div>

  <p style="line-height:1.6;margin:22px 0 0;">{description}</p>

  <div class="indicator-links">
    <a class="primary" href="../{country_slug}.html">View full {country_name} data</a>
    <a href="../compare.html">Compare with other countries</a>
    <a href="../embed/{slug}.html">Embed this chart &#8599;</a>
  </div>

  <div class="related">
    <h2>Other {country_name} indicators</h2>
    {related_links}
  </div>
</main>
{footer}
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<script>
(function(){{
  var pts = {chart_points};
  var cs = getComputedStyle(document.documentElement);
  var INK = cs.getPropertyValue("--ink").trim() || "#171B1E";
  var INK2 = cs.getPropertyValue("--ink2").trim() || "#5A6167";
  var HAIR = cs.getPropertyValue("--hair").trim() || "#E7E9E4";
  var PANEL_BG = cs.getPropertyValue("--panel").trim() || "#fff";
  var LINE = "#37659E";
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
        tooltip: {{backgroundColor: PANEL_BG, titleColor: INK, bodyColor: INK, borderColor: HAIR, borderWidth: 1, displayColors: false}}
      }},
      scales: {{
        x: {{grid: {{display: false}}, ticks: {{color: INK2, maxTicksLimit: 7, maxRotation: 0}}}},
        y: {{grid: {{color: HAIR}}, ticks: {{color: INK2, maxTicksLimit: 6}}}}
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
<meta name="robots" content="noindex">
<style>
  *{{box-sizing:border-box}}
  html,body{{margin:0;padding:0;font-family:"Avenir Next","Avenir","Nunito Sans",system-ui,sans-serif;background:#fff;color:#171B1E}}
  .w{{padding:14px 16px 10px;border:1px solid #E4E6E1;border-radius:10px;max-width:100%}}
  .w-head{{display:flex;align-items:center;justify-content:space-between;margin-bottom:6px}}
  .w-title{{font-size:.85rem;font-weight:700;opacity:.75}}
  .w-value{{font-size:1.8rem;font-weight:700;margin:2px 0}}
  .w-period{{font-size:.72rem;opacity:.55;margin-bottom:8px}}
  .w-badge{{display:flex;align-items:center;gap:5px;font-size:.7rem;opacity:.6;text-decoration:none;color:#171B1E;margin-top:8px}}
  .w-badge:hover{{opacity:1}}
  #chart svg{{display:block}}
</style>
</head>
<body>
<div class="w">
  <div class="w-head"><span class="w-title">{flag} {country_name} &middot; {metric_title}</span></div>
  <div class="w-value" id="val">&hellip;</div>
  <div class="w-period" id="per"></div>
  <div id="chart"></div>
  <a class="w-badge" href="{indicator_url}" target="_blank" rel="noopener">Powered by The Economic Atlas &#8594;</a>
</div>
<script>
(function(){{
  fetch("{data_url}").then(function(r){{return r.json();}}).then(function(d){{
    var s = d.series && d.series["{metric_key}"];
    if(!s || !s.points || !s.points.length) return;
    var pts = s.points.slice(-24);
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
      for(var j=0;j<big.length;j++){{
        if(Math.abs(abs) >= big[j][1]) return currency + (abs/big[j][1]).toLocaleString(undefined,{{minimumFractionDigits:2,maximumFractionDigits:2}}) + big[j][0];
      }}
      return currency + abs.toLocaleString(undefined,{{minimumFractionDigits:2,maximumFractionDigits:2}});
    }}
    var vs = fmtValue(v, unit);
    document.getElementById("val").textContent = vs;
    document.getElementById("per").textContent = "Latest: " + last[0];
    var vals = pts.map(function(p){{return p[1];}}).filter(function(v){{return v!==null;}});
    if(vals.length<2) return;
    var lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals), span=(hi-lo)||1;
    var W=280,H=64,pad=4,n=pts.length,step=(W-2*pad)/(n-1);
    var coords = pts.map(function(p,i){{
      var x = pad + i*step, y = pad + (H-2*pad)*(1-(p[1]-lo)/span);
      return x.toFixed(1)+","+y.toFixed(1);
    }}).join(" ");
    document.getElementById("chart").innerHTML =
      '<svg viewBox="0 0 '+W+' '+H+'" width="100%" height="'+H+'"><polyline points="'+coords+'" fill="none" stroke="#4796CE" stroke-width="2"/></svg>';
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
            if len(pts) < 2:
                skipped.append((country_name, metric_key, "insufficient points"))
                continue
            unit = s.get("unit", "")
            latest_period, latest_val = pts[-1]
            latest_str = fmt_value(latest_val, unit)

            meta = country_sources[metric_key]
            description = meta.get("description", "")
            source_text = meta.get("source", "")

            page_slug = f"{slug}-{metric_slug}"
            canonical = f"{SITE_URL}/indicators/{page_slug}"
            og_image = f"{SITE_URL}/og/{page_slug}.png"
            data_url = f"../{data_file}"
            indicator_url = canonical

            meta_label = re.sub(r"\s*\([^)]*\)", "", metric_title).strip().lower()
            title_tag = f"{country_name} {metric_title} — Live Data & History | The Economic Atlas"
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
                f'<a href="{slug}-{CORE_METRICS[m][0]}.html">{country_name} {CORE_METRICS[m][1]}</a>'
                for m in related
            ) or f'<a href="../{slug}.html">See all {country_name} data &rarr;</a>'

            html_out = INDICATOR_TEMPLATE.format(
                title_tag=esc(title_tag), meta_desc=esc(meta_desc), canonical=canonical,
                og_title=esc(og_title), og_image=og_image, jsonld=jsonld,
                header=HEADER_HTML, footer=FOOTER_HTML,
                country_slug=slug, flag=flag, country_name=esc(country_name),
                metric_title=esc(metric_title), latest_str=esc(latest_str),
                latest_period=esc(latest_period), first_period=esc(pts[0][0]), updated=esc(updated),
                chart_points=chart_points_js, description=esc(description), source=esc(source_text),
                slug=page_slug, related_links=related_links,
            )
            with open(os.path.join(out_indicators, f"{page_slug}.html"), "w", encoding="utf-8") as f:
                f.write(html_out)

            embed_out = EMBED_TEMPLATE.format(
                country_name=esc(country_name), metric_title=esc(metric_title), flag=flag,
                indicator_url=canonical, data_url=data_url, metric_key=metric_key,
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
