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
  8. copy: no "checked hourly" family of claims, no em dashes or double hyphens, no "illustrative"/"sample data".

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


def run_checks(tmp, r):
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

    # 7/8. visible text and copy rules on everything generated
    rules = [("hourly claim", re.compile(r"checked hourly|checks hourly|hourly against|updated hourly|from source every hour", re.I)),
             ("em dash", re.compile("\u2014")),
             ("double hyphen", re.compile(r"(?<![-\w])--(?![-\w>])")),
             ("illustrative / sample data", re.compile(r"illustrative|sample data", re.I)),
             ("NaN/undefined/Infinity", re.compile(r"\b(NaN|undefined|Infinity)\b"))]
    for f in ind_files + emb_files + rank_files:
        h = read(f)
        text, meta = visible(h), meta_text(h)
        for name, rx in rules:
            hit = rx.search(text) or rx.search(meta)
            check(not hit, f"{os.path.relpath(f, tmp)}: {name} ('{hit.group(0) if hit else ''}')")
    bump("pages scanned for copy", len(ind_files) + len(emb_files) + len(rank_files))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--generator")
    ap.add_argument("--repo")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()
    repo = os.path.abspath(a.repo) if a.repo else os.path.dirname(HERE)
    generator = os.path.abspath(a.generator) if a.generator else os.path.join(repo, "generate_indicator_pages.py")
    if not os.path.exists(generator):
        sys.exit(f"no generator at {generator}")
    tmp, r, n_in = stage(repo, generator)
    try:
        run_checks(tmp, r)
    finally:
        if a.keep:
            print("kept", tmp)
        else:
            shutil.rmtree(tmp, ignore_errors=True)
    print(f"generated-pages gate: {n_in} input files staged; " + ", ".join(f"{v} {k}" for k, v in counts.items()))
    for f in fails[:40]:
        print("FAIL", f)
    if len(fails) > 40:
        print(f"... and {len(fails) - 40} more")
    print(f"generated-pages gate: {'FAILED' if fails else 'ok'} ({len(fails)} failures)")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
