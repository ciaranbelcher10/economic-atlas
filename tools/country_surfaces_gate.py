#!/usr/bin/env python3
"""Every country in generate_indicator_pages.COUNTRIES, on every shared surface.

    python3 tools/country_surfaces_gate.py          # exit 1 on any gap

Written after the China launch, where three stale surfaces (index.html map
without Thailand, Dashboard's ISO_OF frozen at 18 countries, eight mini-maps
highlighting the wrong country as "You are here") had survived every other
gate because nothing checked the country roster across files. COUNTRIES is
the single source of truth; this gate fails if any surface disagrees with it.
Read-only.
"""
from __future__ import annotations

import glob, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import generate_indicator_pages as g  # noqa: E402
import fx_config as fxc               # noqa: E402
import check_data_freshness as cdf    # noqa: E402

FAILS: list[str] = []
CHECKS = 0
# Pages with no country nav or no mini-map by design.
# The Eurozone is an aggregate: no single map shape, so no ISO number or mini-map route.
NO_MAP = {"Eurozone"}
# Not a per-country fetcher: the daily bond run, scheduled before v2.0.20 without a rotation group.
OECD_UNGROUPED_OK = {"fetch_bonds_daily.py"}
NO_NAV = {"404.html", "gdp-by-country.html", "inflation-by-country.html", "unemployment-by-country.html"}


def check(ok, msg):
    global CHECKS
    CHECKS += 1
    if not ok:
        FAILS.append(msg)


def obj(text, varname):
    m = re.search(r"(?:var|const|let)\s+" + re.escape(varname) + r"\s*=\s*([\{\[])", text)
    if not m:
        return ""
    o, c = ("{", "}") if m.group(1) == "{" else ("[", "]")
    d = 0
    for j in range(m.end(1) - 1, len(text)):
        d += (text[j] == o) - (text[j] == c)
        if d == 0:
            return text[m.end(1) - 1:j + 1]
    return ""


def has_key(body, key):
    forms = [json.dumps(key)] + ([key] if re.fullmatch(r"[A-Za-z_]\w*", key) else [])
    return any(re.search(r"(?<![\w\"])" + re.escape(k) + r"\s*:", body) for k in forms)


def page(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def main():
    countries = {n: dict(code=v[0], slug=v[1], iso2=v[2], region=v[3]) for n, v in g.COUNTRIES.items()}
    n_countries = len(countries)
    compare, dash, cm, markets = (page(f) for f in ("compare.html", "dashboard.html", "chartmaker.html", "markets.html"))
    iso_of = obj(compare, "ISO_OF")
    isonum = {n: re.search(r"(?<![\w\"])" + re.escape(n if re.fullmatch(r"\w+", n) else json.dumps(n)) + r'\s*:\s*"(\d{3})"', iso_of)
              for n in countries}
    sources = json.load(open(ROOT / "data-metric-sources.json", encoding="utf-8"))
    html = [Path(p).name for p in sorted(glob.glob(str(ROOT / "*.html")))]
    texts = {f: page(f) for f in html}

    for n, c in countries.items():
        slug, code = c["slug"], c["code"]
        datafile = "data-uk.json" if code == "uk" else f"data-{code}.json"
        check((ROOT / f"{slug}.html").exists(), f"{n}: {slug}.html missing")
        check((ROOT / datafile).exists(), f"{n}: {datafile} missing")
        # nav
        for f, t in texts.items():
            if f in NO_NAV or '<p class="dhead">' not in t:
                continue
            check(f'href="{slug}"' in t, f"{n}: missing from nav on {f}")
        # mini-maps: every page that has one routes this country, and its own page marks itself
        num = isonum[n].group(1) if isonum[n] else None
        if n in NO_MAP:
            num = None
        else:
            check(num is not None, f"{n}: no ISO_OF entry in compare.html")
        for f, t in texts.items():
            if n in NO_MAP:
                break
            if "CURRENT=new Set(" in t:
                check(f'.has(id)?"{slug}"' in t, f"{n}: mini-map on {f} does not link to it")  # v1.7.56: the routing pattern, not a bare string
        if num and f"{slug}.html" in texts:
            cur = re.search(r'CURRENT=new Set\(\["(\d{3})"', texts[f"{slug}.html"])
            check(cur and cur.group(1) == num, f"{n}: {slug}.html mini-map marks {cur.group(1) if cur else None} as 'You are here', expected {num}")
        if n not in NO_MAP:
            check(f'.has(id) ? "{slug}"' in texts["index.html"], f"{n}: homepage map does not link to it")
        # the three apps
        for fname, t, maps in (("compare.html", compare, ["FILES", "COUNTRY_LABEL", "COUNTRY_COLOR", "ISO_OF", "REGION_OF", "SOURCE_MAP"]),
                               ("dashboard.html", dash, ["FILES", "ISO_OF", "REGISTRY_KEY_TO_CODE"]),
                               ("chartmaker.html", cm, ["FILES", "COUNTRY_CURRENCY", "COUNTRY_COLOR", "REGISTRY_KEY_TO_CODE", "REGION_OF"])):
            for v in maps:
                if n in NO_MAP and v == "ISO_OF":
                    continue
                check(has_key(obj(t, v), n), f"{n}: not in {fname} {v}")
            if "REGION_GROUPS" in t:
                check(json.dumps(n) in obj(t, "REGION_GROUPS"), f"{n}: not in {fname} REGION_GROUPS")
        fm = re.search(re.escape(n if re.fullmatch(r"\w+", n) else json.dumps(n)) + r'\s*:\s*"([^"]+)"', obj(compare, "FILES"))
        check(fm and fm.group(1) == datafile, f"{n}: compare.html FILES points at {fm.group(1) if fm else None}, expected {datafile}")
        # markets: every country serving a 10-year yield has a row
        try:
            series = json.load(open(ROOT / datafile, encoding="utf-8")).get("series", {})
        except Exception:
            series = {}
        if "bond_yield_10y" in series:
            check(re.search(r"[{,]\s*" + code + r"\s*:", obj(markets, "C")) is not None, f"{n}: serves bond_yield_10y but has no markets.html row")
        # config files
        check(n in fxc.COUNTRY_FX or n in fxc.EURO_MEMBERS, f"{n}: not in fx_config.COUNTRY_FX")
        check(n in cdf.DATA_FILES, f"{n}: not in check_data_freshness.DATA_FILES")
        check(n in sources, f"{n}: no data-metric-sources.json entry")


    # ---- v2.0.20: surfaces added after v1.7.4 (wired by tools/add_country.py since v2.0.20) ----
    idx = texts["index.html"]
    chooser = page("chooser.js")
    mobile = page("mobile.js")
    cal = texts["calendar.html"]
    alerts = page("send_calendar_alerts.py")
    probe = page("tools/probe_external_all.py")
    slugs = dict(re.findall(r'"([^"]+)": "([a-z-]+)"', alerts[alerts.index("COUNTRY_SLUGS = {"):alerts.index("\n}", alerts.index("COUNTRY_SLUGS = {"))]))
    regions = obj(chooser, "REGIONS")
    for n, c in countries.items():
        check(f'"name": {json.dumps(g.PLACE_NAME.get(n, n) + " economic data")}' in idx, f"{n}: no Dataset in index.html's DataCatalog")
        check(json.dumps(n) in regions, f"{n}: not in chooser.js REGIONS (Chartmaker/Dashboard region pickers)")
        check(slugs.get(n) == c["slug"], f"{n}: send_calendar_alerts.COUNTRY_SLUGS gives {slugs.get(n)}, expected {c['slug']}")
        check(re.search(r'"' + c["code"] + r'":\s*"', probe[probe.index("CITE_NAME = {"):]) is not None,
              f"{n}: not in tools/probe_external_all.py CITE_NAME (verify_all would skip it)")
    # membership groups agree across their four copies; euro members are in the euro area and the EU
    def groups(text, rx):
        return {m.group(1): set(re.findall(r'"([^"]+)"', m.group(2))) for m in re.finditer(rx, text)}
    copies = {"chooser.js": groups(chooser, r'\{ ?name: "([^"]+)", members: \[([^\]]*)\]'),
              "compare.html": groups(compare, r'\{ ?name: "([^"]+)", members: \[([^\]]*)\]'),
              "calendar.html": groups(cal, r'\{ ?name: "([^"]+)", members: \[([^\]]*)\]'),
              "mobile.js": groups(mobile, r'\{name:"([^"]+)", list:\[([^\]]*)\]')}
    ref = copies["chooser.js"]
    for f, gs in copies.items():
        for grp, mem in gs.items():
            if grp in ref and f != "chooser.js":
                check(mem == ref[grp], f"{f} {grp} group differs from chooser.js: {sorted(mem ^ ref[grp])}")
    for n in fxc.EURO_MEMBERS:
        check(n in ref.get("Euro area", set()) and n in ref.get("EU", set()), f"{n}: euro member missing from chooser.js Euro area/EU groups")
    # calendar: every economy with events is listed, coloured, chipped and loaded
    cal_files = set(re.findall(r'"(data-calendar-[a-z-]+\.json)"', cal))
    wd = obj(cal, "COUNTRIES_WITH_DATA") or cal[cal.index("COUNTRIES_WITH_DATA"):cal.index("];", cal.index("COUNTRIES_WITH_DATA"))]
    cc = mobile[mobile.index("var CC = {"):mobile.index("};", mobile.index("var CC = {"))]
    for f in sorted(glob.glob(str(ROOT / "data-calendar-*.json"))):
        name = Path(f).name
        check(name in cal_files, f"{name} exists but calendar.html does not load it")
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        evs = d.get("events", d) if isinstance(d, dict) else d
        for who in {e.get("country") for e in (evs if isinstance(evs, list) else []) if isinstance(e, dict) and e.get("country")}:
            if who in countries:
                check(json.dumps(who) in wd, f"{who}: has calendar events but is not in calendar.html COUNTRIES_WITH_DATA")
                check(json.dumps(who) + ":" in cc, f"{who}: has calendar events but no mobile.js calendar chip code (CC)")
    # workflows: every country is fetched and committed; every per-country fetcher runs
    wf = {k: page(f".github/workflows/{k}.yml") for k in ("update-data", "update-trade-data", "update-calendar")}
    for n, c in countries.items():
        datafile = "data-uk.json" if c["code"] == "uk" else f"data-{c['code']}.json"
        check(datafile in wf["update-data"], f"{n}: {datafile} is not in update-data.yml's commit list")
        check(f"{c['slug']}.html" in wf["update-data"], f"{n}: {c['slug']}.html is not in update-data.yml's commit list (key figures would never be committed)")
    for f in sorted(glob.glob(str(ROOT / "fetch_*.py"))):
        f = Path(f).name
        which = "update-trade-data" if f.endswith("_trade_partners.py") else "update-calendar" if f.startswith("fetch_calendar_") else "update-data"
        if re.fullmatch(r"fetch_([a-z]{2}|[a-z]{2}_trade_partners|calendar_[a-z_]+)\.py", f):
            check(f"python {f}" in wf[which], f"{f} is never run by {which}.yml")
    # OECD rotation (v1.9.57): a fetcher that calls the OECD and has no group fetches every hour
    import oecd_turn
    for f in sorted(glob.glob(str(ROOT / "fetch_*.py"))):
        f = Path(f).name
        if f in OECD_UNGROUPED_OK:
            continue
        if re.search(r"sdmx\.oecd\.org|oecd_[a-z]+|import oecd", page(f)):
            check(f in oecd_turn.GROUPS, f"{f} calls the OECD but has no oecd_turn.GROUPS entry (it would call every hour)")

    # counts in copy
    m = re.search(r"\b(\d\d) economies\b", texts["index.html"])
    check(m and int(m.group(1)) == n_countries, f"index.html says {m.group(1) if m else '?'} economies, COUNTRIES has {n_countries}")
    for m in re.finditer(r"across (\d\d) countries", compare):
        check(int(m.group(1)) == n_countries, f"compare.html says {m.group(1)} countries, COUNTRIES has {n_countries}")
    check(len(cdf.DATA_FILES) == n_countries, f"check_data_freshness.DATA_FILES has {len(cdf.DATA_FILES)}, COUNTRIES has {n_countries}")

    print(f"country surfaces gate: {n_countries} countries, {CHECKS} checks, {len(FAILS)} gaps")
    for f in FAILS:
        print("  GAP  " + f)
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
