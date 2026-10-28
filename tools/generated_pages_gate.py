#!/usr/bin/env python3
"""Generated-pages gate (v1.9.13).

indicators/, embed/, rankings/ and sitemap.xml are built by CI after a deploy (generate_indicator_pages.py),
so a gate that reads the committed copies tests stale files. This gate does what CI will do instead: it copies
the generator and its inputs (the root *.json, *.html and *.py files) into a temporary folder, runs the real
generator there, and checks what came out, against the source data and against rules written independently of
the generator's own code. It never writes to the repository.

Checks (every one is mutation-tested in tools/test_generated_pages_gate.py):

  1. the generator exits 0 and its summary line matches the files it wrote, the manifest and the sitemap;
  2. every indicator page's title ends with the period of the last point of its OWN embedded series, formatted
     independently here ("Aug 2026", "Q2 2026", "2025", and "Jun–Aug 2026" for the UK's rolling three-month
     Labour Force Survey rates, which the ONS labels by the middle month);
  3. every embedded series equals its source series in the data file (rolling four-quarter GDP totals: same
     last period and three fewer points; computed keys such as fx_usd are counted, not compared);
  4. the embed page shows the same period label as its indicator page;
  5. ranking rows are well formed, and the UK's Labour Force Survey ranking row shows the rolling range, and
     compares with the previous non-overlapping three months, labelled as a range, as the indicator page does;
  6. sitemap.xml lists every generated indicator and ranking page exactly once and points at no missing file;
  7. page hygiene: canonical link, JSON-LD parses, and no NaN/undefined/Infinity in visible text;
  8. copy: no "checked hourly" family of claims, no em dashes or double hyphens, no "illustrative"/"sample data";
  9. methodology-by-economy.html (v1.9.15): every one of the indicator pages is documented exactly once; each row's
     series label and frequency equal the data file's; each economy's "Not tracked" line and the gap table equal an
     independent recomputation; each hand-written note appears exactly when its condition holds in the data; every
     local link resolves.

Run from anywhere:   python3 tools/generated_pages_gate.py
Options:             --generator PATH   use another copy of the generator (the tests do)
                     --repo PATH        take the inputs from another checkout
                     --keep             leave the temporary folder in place and print its path
"""
import argparse
import glob
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from html import unescape

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = "https://theeconomicatlas.com"
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
UK_LFS = {"unemployment", "employment", "inactivity", "unemployment_1624"}
GENERATED_ROOT = {"methodology-by-economy.html"}   # root pages the generator writes: never staged from the repo
RANKING_KEY = {"unemployment-rate-by-country": "unemployment"}   # rankings that carry a UK Labour Force Survey row
fails = []
counts = {}


def check(cond, msg):
    if not cond:
        fails.append(msg)
    return cond


def bump(k, n=1):
    counts[k] = counts.get(k, 0) + n


def label(period, rolling=False):
    """The period as a reader sees it. Written here on purpose, not imported from the generator."""
    period = str(period)
    m = re.fullmatch(r"(\d{4})-(\d{2})", period)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        if rolling:
            sy, sm = (y, mo - 1) if mo > 1 else (y - 1, 12)
            ey, em = (y, mo + 1) if mo < 12 else (y + 1, 1)
            a, b = MONTHS[sm - 1], MONTHS[em - 1]
            return f"{a}\u2013{b} {ey}" if sy == ey else f"{a} {sy}\u2013{b} {ey}"
        return f"{MONTHS[mo - 1]} {y}"
    m = re.fullmatch(r"(\d{4})-Q([1-4])", period)
    if m:
        return f"Q{m.group(2)} {m.group(1)}"
    return period


def visible(h):
    h = re.sub(r"<script.*?</script>|<style.*?</style>|<!--.*?-->", " ", h, flags=re.S)
    return unescape(re.sub(r"<[^>]+>", " ", h))


def meta_text(h):
    parts = re.findall(r"<title>(.*?)</title>", h, re.S) + re.findall(r'<meta[^>]*\bcontent="([^"]*)"', h)
    return unescape(" ".join(parts))


def stage(repo, generator):
    tmp = tempfile.mkdtemp(prefix="gpg_")
    n = 0
    # the generator reads the root *.json and *.html and lazily imports root modules (fx_config); the chosen
    # generator is copied LAST so it replaces the repo's own
    for pat in ("*.json", "*.html", "*.py"):
        for f in glob.glob(os.path.join(repo, pat)):
            if os.path.basename(f) in GENERATED_ROOT:
                continue     # generated output, not input: it must come from the generator or it proves nothing
            shutil.copy(f, os.path.join(tmp, os.path.basename(f)))
            n += 1
    shutil.copy(generator, os.path.join(tmp, "generate_indicator_pages.py"))
    r = subprocess.run([sys.executable, "generate_indicator_pages.py"], cwd=tmp, capture_output=True, text=True,
                       timeout=600, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    return tmp, r, n


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def cfg_of(h):
    m = re.search(r"EATLAS_IND\.initIndicator\((\{.*?\})\);</script>", h, re.S)
    return json.loads(m.group(1)) if m else None


def run_checks(tmp, r, repo):
    # 1. generator ran, summary matches the files
    check(r.returncode == 0, f"generator exited {r.returncode}: {r.stderr[-300:]}")
    m = re.search(r"Generated (\d+) indicator pages, (\d+) embeds and (\d+) rankings\.", r.stdout)
    if not check(m, "generator printed no 'Generated N indicator pages, N embeds and N rankings.' line"):
        return
    n_ind, n_emb, n_rank = (int(x) for x in m.groups())
    ind_files = sorted(glob.glob(os.path.join(tmp, "indicators", "*.html")))
    emb_files = sorted(glob.glob(os.path.join(tmp, "embed", "*.html")))
    rank_files = sorted(f for f in glob.glob(os.path.join(tmp, "rankings", "*.html")) if os.path.basename(f) != "index.html")
    check(len(ind_files) == n_ind, f"summary says {n_ind} indicator pages, found {len(ind_files)}")
    check(len(emb_files) == n_emb, f"summary says {n_emb} embeds, found {len(emb_files)}")
    check(len(rank_files) == n_rank, f"summary says {n_rank} rankings, found {len(rank_files)}")
    check(n_ind == n_emb and n_ind > 0, f"indicator pages ({n_ind}) and embeds ({n_emb}) must pair up")
    bump("indicator pages", n_ind), bump("embeds", n_emb), bump("rankings", n_rank)

    man = json.loads(read(os.path.join(tmp, "indicators", "manifest.json")))
    # the manifest lists metric slugs per country ("gdp", "real-gdp"), so it can only be compared by count
    check(sum(len(v) for v in man["indicators"].values()) == n_ind,
          "manifest indicator count differs from the pages written")
    page_slugs = {os.path.basename(f)[:-5] for f in ind_files}
    check({x["slug"] for x in man["rankings"]} == {os.path.basename(f)[:-5] for f in rank_files},
          "manifest rankings differ from the files written")

    data_cache = {}

    def series_of(data_file, key):
        if data_file not in data_cache:
            p = os.path.join(tmp, data_file)
            data_cache[data_file] = json.loads(read(p))["series"] if os.path.exists(p) else None
        d = data_cache[data_file]
        return None if d is None else d.get(key)

    labels = {}
    for f in ind_files:
        slug = os.path.basename(f)[:-5]
        h = read(f)
        cfg = cfg_of(h)
        if not check(cfg, f"{slug}: no initIndicator config"):
            continue
        data_file = os.path.basename(cfg.get("dataUrl", ""))
        pts = cfg.get("points") or []
        if not check(len(pts) >= 2, f"{slug}: fewer than two points"):
            continue
        check([p[0] for p in pts] == sorted(set(p[0] for p in pts)), f"{slug}: periods not strictly ascending")
        rolling = data_file == "data-uk.json" and cfg.get("key") in UK_LFS and cfg.get("freq") == "months"
        want = label(pts[-1][0], rolling)
        labels[slug] = want
        # 2. title period
        t = unescape((re.search(r"<title>(.*?)</title>", h, re.S) or [None, ""])[1])
        tm = re.search(r"\(([^()]*)\) \| The Economic Atlas$", t)
        check(tm and tm.group(1) == want, f"{slug}: title says '{tm.group(1) if tm else t}', last data point is '{want}'")
        if rolling:
            bump("rolling-range pages")
        # 3. fidelity to the data file
        s = series_of(data_file, cfg.get("key"))
        if s is None:
            bump("computed-key pages (not compared)")
        elif cfg.get("annualise") and pts != s["points"]:
            # a quarterly flow summed over four quarters: the same last period and three fewer points. (Series
            # already published annually, or already annualised at source such as Japan's, pass through unchanged
            # and fall into the plain comparison below.)
            check(pts[-1][0] == s["points"][-1][0] and len(pts) == len(s["points"]) - 3,
                  f"{slug}: rolling four-quarter total does not line up with {data_file}[{cfg['key']}]")
            bump("rolling-total pages (shape compared)")
        else:
            check(pts == s["points"], f"{slug}: embedded series differs from {data_file}[{cfg['key']}]")
            bump("pages equal to source")
        # 7. hygiene
        want_canon = f"{SITE}/indicators/{slug}"
        cm = re.search(r'<link rel="canonical" href="([^"]*)"', h)
        check(cm and cm.group(1) == want_canon, f"{slug}: canonical is {cm.group(1) if cm else None}")
        for blk in re.findall(r'<script type="application/ld\+json">(.*?)</script>', h, re.S):
            try:
                json.loads(blk)
            except ValueError:
                check(False, f"{slug}: JSON-LD does not parse")

    # 4. embeds show the same period
    for f in emb_files:
        slug = os.path.basename(f)[:-5]
        if not check(slug in labels, f"embed {slug}: no matching indicator page"):
            continue
        check(labels[slug] in unescape(read(f)), f"embed {slug}: does not show '{labels[slug]}'")

    # 5. rankings
    uk_lfs_series = series_of("data-uk.json", "unemployment")
    for f in rank_files:
        slug = os.path.basename(f)[:-5]
        h = read(f)
        rows = re.findall(r'<tr data-rank="(\d+)" data-country="([^"]*)" data-value="([^"]*)" data-change="([^"]*)" '
                          r'data-period="([^"]*)" data-source="[^"]*">(.*?)</tr>', h, re.S)
        check(len(rows) >= 5, f"ranking {slug}: only {len(rows)} rows")
        bump("ranking rows", len(rows))
        for rank, country, value, change, period, body in rows:
            try:
                ok = math.isfinite(float(value)) and (change == "" or math.isfinite(float(change)))
            except ValueError:
                ok = False
            check(ok, f"ranking {slug}: {country} has value '{value}' change '{change}'")
            check(re.fullmatch(r"\d{4}-\d{2}-\d{2}", period), f"ranking {slug}: {country} period '{period}'")
        if slug in RANKING_KEY and uk_lfs_series:
            pts = uk_lfs_series["points"]
            uk = [r for r in rows if r[1] == "UK"]
            if check(len(uk) == 1, f"ranking {slug}: expected one UK row, found {len(uk)}"):
                _, _, value, change, _, body = uk[0]
                lat, prev = pts[-1], pts[-4]
                cell = unescape(re.sub(r"<[^>]+>", "", body))
                check(label(lat[0], True) in cell, f"ranking {slug}: UK row does not show '{label(lat[0], True)}'")
                check(abs(float(value) - lat[1]) < 1e-9, f"ranking {slug}: UK value {value}, data {lat[1]}")
                check(change != "" and abs(float(change) - round(lat[1] - prev[1], 1)) < 1e-9,
                      f"ranking {slug}: UK change {change}, expected {round(lat[1] - prev[1], 1)} "
                      f"(latest {lat[0]} against {prev[0]}, the previous non-overlapping three months)")
                tip = re.search(r'class="num chg" title="([^"]*)"', body)
                check(tip and unescape(tip.group(1)) == f"Change on {label(prev[0], True)}",
                      f"ranking {slug}: UK change tooltip is '{tip.group(1) if tip else None}', "
                      f"expected 'Change on {label(prev[0], True)}'")
                bump("UK rolling ranking rows checked")
        for blk in re.findall(r'<script type="application/ld\+json">(.*?)</script>', h, re.S):
            try:
                json.loads(blk)
            except ValueError:
                check(False, f"ranking {slug}: JSON-LD does not parse")

    # 6. sitemap
    sm = read(os.path.join(tmp, "sitemap.xml"))
    locs = re.findall(r"<loc>(.*?)</loc>", sm)
    check(len(locs) == len(set(locs)), "sitemap has duplicate entries")
    locset = set(locs)
    for slug in page_slugs:
        check(f"{SITE}/indicators/{slug}" in locset, f"sitemap lacks indicators/{slug}")
    for f in rank_files:
        slug = os.path.basename(f)[:-5]
        check(f"{SITE}/rankings/{slug}" in locset, f"sitemap lacks rankings/{slug}")
    for loc in locs:
        mm = re.fullmatch(re.escape(SITE) + r"/(indicators|rankings)/([^/]+)", loc)
        if mm:
            check(os.path.exists(os.path.join(tmp, mm.group(1), mm.group(2) + ".html")), f"sitemap points at missing {loc}")
    bump("sitemap entries", len(locs))

    # 9. methodology by economy
    meth = check_methodology(tmp, repo, ind_files, labels, series_of)

    # 7/8. visible text and copy rules on everything generated
    rules = [("hourly claim", re.compile(r"checked hourly|checks hourly|hourly against|updated hourly|from source every hour", re.I)),
             ("em dash", re.compile("\u2014")),
             ("double hyphen", re.compile(r"(?<![-\w])--(?![-\w>])")),
             ("illustrative / sample data", re.compile(r"illustrative|sample data", re.I)),
             ("NaN/undefined/Infinity", re.compile(r"\b(NaN|undefined|Infinity)\b"))]
    for f in ind_files + emb_files + rank_files + ([meth] if meth else []):
        h = read(f)
        text, meta = visible(h), meta_text(h)
        for name, rx in rules:
            hit = rx.search(text) or rx.search(meta)
            check(not hit, f"{os.path.relpath(f, tmp)}: {name} ('{hit.group(0) if hit else ''}')")
    bump("pages scanned for copy", len(ind_files) + len(emb_files) + len(rank_files) + (1 if meth else 0))


# Methodology-by-economy checks. These are a SECOND, independent statement of the rules in
# methodology_by_economy.py: changing a rule means changing it in both places, on purpose.
GATE_CORE = [("GDP", ["gdp"]), ("Real GDP", ["real-gdp"]), ("GDP growth", ["gdp-growth-rate", "gdp-annual-growth-rate"]),
             ("Inflation", ["inflation-rate"]), ("Unemployment", ["unemployment-rate"]),
             ("Employment rate", ["employment-rate"]), ("Labour force participation", ["labour-force-participation-rate"]),
             ("Policy interest rate", ["interest-rate"]), ("10-year bond yield", ["10-year-government-bond-yield"]),
             ("Exchange rate", ["exchange-rate"]), ("Business confidence", ["business-confidence"]),
             ("Trade balance", ["balance-of-trade"]), ("Current account", ["current-account-to-gdp"]),
             ("Foreign direct investment", ["foreign-direct-investment"]), ("Government debt", ["government-debt"]),
             ("Government budget balance", ["government-budget"])]
GATE_EURO = {"Austria", "Belgium", "Bulgaria", "Croatia", "Cyprus", "Estonia", "Finland", "France", "Germany", "Greece",
             "Ireland", "Italy", "Latvia", "Lithuania", "Luxembourg", "Malta", "Netherlands", "Portugal", "Slovakia",
             "Slovenia", "Spain"}
FREQ_WORD = {"months": "Monthly", "quarters": "Quarterly", "years": "Annual"}
OECD_PHRASE = "latest quarters from OECD QNA"
# section id -> (text fragment of the note, how to tell from the data that it is still true)
NOTE_RULES = {
    "uk": ("rolling three-month averages", lambda ctx: "\u2013" in ctx["labels"].get("uk-unemployment-rate", "")),
    "southafrica": ("LRUN64TTZAQ156S", lambda ctx: "LRUN64TTZAQ156S" in ctx["lab"]("unemployment") and ", SA" in ctx["lab"]("unemployment")),
    "switzerland": ("sporting events", lambda ctx: "CLVMNACSAB1GQCH" in ctx["lab"]("gdp_growth")),
    "poland": ("goods balance", lambda ctx: "Eurostat" in ctx["lab"]("trade_balance") and "\u20ac" in ctx["unit"]("trade_balance")),
    "argentina": ("so growth is shown year on year", lambda ctx: "not seasonally adjusted" in ctx["lab"]("gdp_growth") and "YoY" in ctx["lab"]("gdp_growth")),
}


def check_methodology(tmp, repo, ind_files, labels, series_of):
    path = os.path.join(tmp, "methodology-by-economy.html")
    if not check(os.path.exists(path), "methodology-by-economy.html was not generated"):
        return None
    h = read(path)
    cm = re.search(r'<link rel="canonical" href="([^"]*)"', h)
    check(cm and cm.group(1) == f"{SITE}/methodology-by-economy", f"methodology: canonical is {cm.group(1) if cm else None}")
    for blk in re.findall(r'<script type="application/ld\+json">(.*?)</script>', h, re.S):
        try:
            json.loads(blk)
        except ValueError:
            check(False, "methodology: JSON-LD does not parse")
    # --- sections
    secs = re.findall(r'<section class="[^"]*\bmb-econ\b[^"]*" id="([^"]*)"[^>]*>(.*?)</section>', h, re.S)
    page_set = {os.path.basename(f)[:-5] for f in ind_files}
    seen_pages = []
    expected_missing = {}
    for sid, body in secs:
        name = unescape((re.search(r"<h2>(.*?)</h2>", body, re.S) or [None, ""])[1])
        rows = re.findall(r'<tr><th scope="row"><a href="indicators/([^"]*)">(.*?)</a></th><td[^>]*>(.*?)</td><td[^>]*>(.*?)</td><td[^>]*>(.*?)</td></tr>', body, re.S)
        check(rows, f"methodology {name}: no rows")
        slugs, first_cfg = set(), None
        for page, title, label, freq, adj in rows:
            seen_pages.append(page)
            check(page.startswith(sid + "-"), f"methodology {name}: row links to {page}, which is not this economy's")
            slugs.add(page[len(sid) + 1:])
            f = os.path.join(tmp, "indicators", page + ".html")
            if not os.path.exists(f):
                check(False, f"methodology {name}: links to missing indicator page {page}")
                continue
            cfg = cfg_of(read(f))
            first_cfg = first_cfg or cfg
            check(unescape(freq) == FREQ_WORD.get(cfg["freq"]), f"methodology {name}/{page}: frequency '{freq}', data says {cfg['freq']}")
            s = series_of(os.path.basename(cfg.get("dataUrl", "")), cfg.get("key"))
            if s is not None:
                check(unescape(label) == s["label"].strip(), f"methodology {name}/{page}: label '{unescape(label)[:60]}' differs from the data's '{s['label'][:60]}'")
            else:
                check(unescape(label).strip() != "", f"methodology {name}/{page}: empty label")
            check(unescape(adj).strip() != "" and unescape(title).strip() != "", f"methodology {name}/{page}: empty title or adjustment")
            if re.search(r"\bSCA\b", unescape(label)):
                check(unescape(adj) in ("Seasonally and calendar adjusted", "Seasonally adjusted"),
                      f"methodology {name}/{page}: the label says SCA but the Adjustment column says '{unescape(adj)}'")
        m = re.search(r"(\d+) indicators</span>", body)
        check(m and int(m.group(1)) == len(rows), f"methodology {name}: says {m.group(1) if m else None} indicators, lists {len(rows)}")
        # --- gaps, recomputed here
        want = [t for t, ss in GATE_CORE
                if not any(x in slugs for x in ss) and not (t == "Exchange rate" and (name in GATE_EURO or name == "US"))]
        expected_missing[name] = want
        gm = re.search(r'<p class="mb-gaps"><strong>Not tracked:</strong> (.*?)\.</p>', body, re.S)
        got = [] if (gm and "nothing on the core list" in gm.group(1)) else [unescape(x).strip() for x in (gm.group(1).split(", ") if gm else ["<missing>"])]
        check(got == want, f"methodology {name}: 'Not tracked' says {got}, recomputed {want}")
        # --- notes
        notes = [unescape(x) for x in re.findall(r"<li>(.*?)</li>", body, re.S)]
        data_file = os.path.basename((first_cfg or {}).get("dataUrl", ""))
        ctx = {"labels": labels, "lab": lambda k, df=data_file: ((series_of(df, k) or {}).get("label") or ""),
               "unit": lambda k, df=data_file: ((series_of(df, k) or {}).get("unit") or "")}
        for nsid, (frag, holds) in NOTE_RULES.items():
            shown = any(frag in n for n in notes)
            if nsid == sid:
                check(shown == bool(holds(ctx)), f"methodology {name}: note '{frag}' shown={shown}, but its condition in the data is {bool(holds(ctx))}")
            else:
                check(not shown, f"methodology {name}: carries the note meant for {nsid}")
        oecd_rows = any(OECD_PHRASE in unescape(r[2]) for r in rows)
        oecd_note = any("The latest quarters of" in n for n in notes)
        check(oecd_rows == oecd_note, f"methodology {name}: OECD QNA note shown={oecd_note}, labels carry the phrase={oecd_rows}")
        for n in notes:
            check(n.strip() != "", f"methodology {name}: empty note")
        check("None" not in re.findall(r'<tr class="mb-theme"><th colspan="4">(.*?)</th></tr>', body), f"methodology {name}: a row has no theme")
    # --- looks and behaves like the rest of the site: shared assets, no inline styling, working navigation
    head = h.split("</head>")[0]
    for asset in ("indicator.css", "doc.css"):
        check(re.search(r'<link[^>]*stylesheet[^>]*href="%s(\?[^"]*)?"' % re.escape(asset), head), f"methodology: head does not link {asset}")
    check(re.search(r'<script[^>]*src="doc\.js(\?[^"]*)?"', h), "methodology: doc.js is not loaded")
    check("chart.umd" not in h and "indicator-kit" not in h, "methodology: a text page must not load the charting library or the indicator kit")
    main = h[h.find("<main"):h.find("</main>")]
    check(main and not re.search(r"\sstyle=", main), "methodology: inline style attributes inside <main>")
    check(len(re.findall(r"<h1[ >]", main)) == 1, "methodology: exactly one h1 expected")
    sec_ids = {sid for sid, _ in secs}
    toc = re.search(r'<nav class="panel ind-panel doc-toc".*?</nav>', main, re.S)
    toc_ids = re.findall(r'href="#([^"]+)"', toc.group(0)) if toc else []
    all_ids = set(re.findall(r'\sid="([^"]+)"', main))
    check(toc_ids and all(t in all_ids for t in toc_ids), f"methodology: contents link to missing ids {[t for t in toc_ids if t not in all_ids]}")
    idx = re.search(r'<nav class="mb-index".*?</nav>', main, re.S)
    idx_ids = re.findall(r'href="#([^"]+)" data-for="([^"]+)"', idx.group(0)) if idx else []
    check(sorted(i for i, _ in idx_ids) == sorted(sec_ids) and all(a == b for a, b in idx_ids),
          "methodology: the economy index does not match the economy sections one to one")
    check(re.search(r'<input[^>]*id="docFilter"', main) and re.search(r'id="docCount"', main) and re.search(r'id="docEmpty"', main),
          "methodology: the find-an-economy controls are missing")
    regions = {re.search(r'data-region="([^"]*)"', t[0]).group(1) for t in re.findall(r'(<section class="[^"]*\bmb-econ\b[^"]*"[^>]*>)', main, re.S) for t in [(t,)]}
    chips = set(re.findall(r'class="rk-btn doc-chip[^"]*" data-region="([^"]*)"', main))
    check("" in chips and (chips - {""}) == regions and all(regions), f"methodology: region chips {sorted(chips)} do not match the sections' regions {sorted(regions)}")
    for sid, body in secs:
        nm = re.search(r'data-name="([^"]*)"', h[h.find(f'id="{sid}"') - 120:h.find(f'id="{sid}"') + 200])
        check(nm and unescape(nm.group(1)) == unescape((re.search(r"<h2>(.*?)</h2>", body, re.S) or [None, ""])[1]), f"methodology {sid}: data-name differs from the heading")
    # --- completeness: every indicator page documented exactly once
    check(sorted(seen_pages) == sorted(page_set),
          f"methodology documents {len(seen_pages)} indicator rows for {len(page_set)} pages "
          f"(missing {sorted(page_set - set(seen_pages))[:3]}, extra {sorted(set(seen_pages) - page_set)[:3]})")
    check(len(seen_pages) == len(set(seen_pages)), "methodology lists an indicator page twice")
    # --- the gap table equals the sections
    gap = re.search(r"<h2>Where the site has gaps</h2>(.*?)<h2>The \d+ economies</h2>", h, re.S)
    table = {unescape(a): (int(b), [x.strip() for x in unescape(c).split(", ")]) for a, b, c in
             re.findall(r'<tr><th scope="row">(.*?)</th><td[^>]*>(\d+)</td><td[^>]*>(.*?)</td></tr>', gap.group(1) if gap else "", re.S)}
    for t, _ in GATE_CORE:
        lacking = sorted(n for n, miss in expected_missing.items() if t in miss)
        if lacking:
            check(t in table and table[t][0] == len(lacking) and sorted(table[t][1]) == lacking,
                  f"methodology gap table for '{t}': {table.get(t, ('absent',))[0]} listed, recomputed {len(lacking)}")
        else:
            check(t not in table, f"methodology gap table lists '{t}' though no economy lacks it")
    # --- every local link resolves
    for ref in re.findall(r'(?:href|src)="([^"]+)"', h):
        if re.match(r"(https?:|mailto:|tel:|data:|javascript:|//|#)", ref):
            continue
        p = ref.split("#")[0].split("?")[0]
        if not p:
            continue
        cands = [os.path.join(b, p + suf) for b in (repo, tmp) for suf in ("", ".html", "/index.html")]
        check(any(os.path.isfile(c) for c in cands), f"methodology: link '{ref}' does not resolve")
    bump("methodology economies", len(secs)), bump("methodology rows", len(seen_pages))
    return path


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--generator")
    ap.add_argument("--repo")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--max-fails", type=int, default=40, help="how many failures to print (the exit code counts all)")
    a = ap.parse_args()
    repo = os.path.abspath(a.repo) if a.repo else os.path.dirname(HERE)
    generator = os.path.abspath(a.generator) if a.generator else os.path.join(repo, "generate_indicator_pages.py")
    if not os.path.exists(generator):
        sys.exit(f"no generator at {generator}")
    tmp, r, n_in = stage(repo, generator)
    try:
        run_checks(tmp, r, repo)
    finally:
        if a.keep:
            print("kept", tmp)
        else:
            shutil.rmtree(tmp, ignore_errors=True)
    print(f"generated-pages gate: {n_in} input files staged; " + ", ".join(f"{v} {k}" for k, v in counts.items()))
    for f in fails[:a.max_fails]:
        print("FAIL", f)
    if len(fails) > a.max_fails:
        print(f"... and {len(fails) - a.max_fails} more")
    print(f"generated-pages gate: {'FAILED' if fails else 'ok'} ({len(fails)} failures)")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
