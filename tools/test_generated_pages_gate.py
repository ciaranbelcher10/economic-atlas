#!/usr/bin/env python3
"""Tests for tools/generated_pages_gate.py (v1.9.13).

A gate that has never been seen to fail proves nothing, so this feeds it deliberately broken generators and
doctored data and requires, for each, a non-zero exit and a failure message naming the right problem. A crash
does not count as a catch: the gate must exit 1 with a FAIL line, not a traceback.

  - positive control: the repo's own generator passes;
  - 15 generator mutations, one per class of problem the gate exists to catch;
  - doctored data: a rolling UK range that crosses a year boundary, and a UK series whose previous month
    differs from three months ago (so the ranking's comparison basis shows). The repo's generator must pass
    both; the generator with the v1.9.13 ranking fix reverted must fail the second.

Each gate run takes about six seconds. Run from the repo root:  python3 tools/test_generated_pages_gate.py
"""
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GATE = ROOT / "tools" / "generated_pages_gate.py"
GEN = (ROOT / "generate_indicator_pages.py").read_text(encoding="utf-8")
fails = []
ran = 0


def check(cond, msg):
    if not cond:
        fails.append(msg)
        print("FAIL", msg)


def run_gate(gen_text=None, repo=None):
    tmp = Path(tempfile.mkdtemp(prefix="tgg_"))
    args = [sys.executable, str(GATE)]
    if gen_text is not None:
        g = tmp / "generate_indicator_pages.py"
        g.write_text(gen_text, encoding="utf-8")
        args += ["--generator", str(g)]
    if repo is not None:
        args += ["--repo", str(repo)]
    r = subprocess.run(args, capture_output=True, text=True, timeout=300, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    shutil.rmtree(tmp, ignore_errors=True)
    global ran
    ran += 1
    return r


def mutate(old, new):
    assert GEN.count(old) == 1, f"anchor not unique ({GEN.count(old)}): {old[:70]!r}"
    return GEN.replace(old, new)


def caught(name, r, expect):
    out = r.stdout + r.stderr
    fl = [ln for ln in out.splitlines() if ln.startswith("FAIL")]
    match = (lambda ln: expect.search(ln)) if hasattr(expect, "search") else (lambda ln: expect in ln)
    ok = r.returncode == 1 and "Traceback" not in r.stderr and any(match(ln) for ln in fl)
    check(ok, f"{name}: expected exit 1 with a FAIL line containing {expect!r}; got rc={r.returncode}, "
              f"{len(fl)} FAIL lines, first: {fl[0][:150] if fl else out[-200:]!r}")


def repo_copy(edit):
    d = Path(tempfile.mkdtemp(prefix="tgr_"))
    for pat in ("*.json", "*.html", "*.py"):
        for f in glob.glob(str(ROOT / pat)):
            shutil.copy(f, d / os.path.basename(f))
    # the methodology page links to the site's css, js and images: link them in so the gate's link check can resolve them
    for f in ROOT.iterdir():
        if f.is_file() and not (d / f.name).exists():
            os.symlink(f, d / f.name)
    edit(d)
    return d


# the v1.9.13 ranking fix, reverted (the generator as it was in v1.9.12)
FIX_COMPARE = re.compile(r'            if is_rolling3m\(country, key\) and freq == "months" and len\(pts\) >= 4:\n(?:                #.*\n)+'
                         r'                prev_p, prev = pts\[-4\]\n')
FIX_TIP_NEW = ('(fmt_rolling3m if is_rolling3m(r["country"], r.get("key")) and r.get("freq") == "months" '
               'else fmt_period_label)(r.get("prev_period", ""))')
FIX_TIP_OLD = 'fmt_period_label(r.get("prev_period", ""))'
assert FIX_COMPARE.search(GEN) and GEN.count(FIX_TIP_NEW) == 1, "the v1.9.13 ranking fix is not in generate_indicator_pages.py"
V1912 = FIX_COMPARE.sub("", GEN, count=1).replace(FIX_TIP_NEW, FIX_TIP_OLD)

# ---------------------------------------------------------------- positive control
r = run_gate()
check(r.returncode == 0 and "ok (0 failures)" in r.stdout, f"positive control: the repo's generator must pass: {r.stdout[-400:]} {r.stderr[-200:]}")
check("976 indicator pages" in r.stdout or re.search(r"\d+ indicator pages", r.stdout), "positive control: no page counts reported")

# ---------------------------------------------------------------- generator mutations
VS = 'vs {esc(plab(prev_p))}</span></p>'
MUTS = [
    ("UK rolling labels dropped", mutate('ROLLING_3M_MID = {("UK", "unemployment"), ("UK", "employment"), ("UK", "inactivity"), ("UK", "unemployment_1624")}',
                                         'ROLLING_3M_MID = set()'), "title says"),
    ("ranking tooltip back to a plain month (v1.9.12)", GEN.replace(FIX_TIP_NEW, FIX_TIP_OLD), "UK change tooltip"),
    ("hourly claim in visible copy", mutate(VS, 'vs {esc(plab(prev_p))} (checked hourly)</span></p>'), "hourly claim"),
    ("em dash in visible copy", mutate(VS, 'vs {esc(plab(prev_p))} \u2014 x</span></p>'), "em dash"),
    ("double hyphen in visible copy", mutate(VS, 'vs {esc(plab(prev_p))} -- x</span></p>'), "double hyphen"),
    ("'illustrative' in visible copy", mutate(VS, 'vs {esc(plab(prev_p))} (illustrative)</span></p>'), "illustrative"),
    ("NaN in visible copy", mutate(VS, 'vs {esc(plab(prev_p))} NaN</span></p>'), "NaN/undefined/Infinity"),
    ("embedded series loses its last point", mutate("points=pts, realPoints=real_pts", "points=pts[:-1], realPoints=real_pts"), "differs from"),
    ("canonical link wrong", mutate('href="{canonical}">', 'href="{canonical}/">'), "canonical is"),
    ("JSON-LD truncated", mutate("\n{jsonld}\n</script>", "\n{jsonld[:-5]}\n</script>"), "JSON-LD does not parse"),
    ("rankings missing from the sitemap", mutate("        if u not in seen:\n            seen.add(u)\n",
                                                 '        if u not in seen and "/rankings/" not in u:\n            seen.add(u)\n'), "sitemap lacks rankings/"),
    ("embed shows a plain month for the UK", mutate('latest_period=esc((fmt_rolling3m if is_rolling3m(country, entry["key"]) else fmt_period_label)(lp[0]))',
                                                    "latest_period=esc(fmt_period_label(lp[0]))"), "does not show"),
    ("summary line overstates the embeds", mutate('{generated} embeds and', '{generated + 1} embeds and'), "summary says"),
    ("generator crashes", mutate("def main():\n", "def main():\n    raise SystemExit(3)\n"), "generator exited 3"),
    ("consent.js script dropped from generated pages", mutate('<script src="../consent.js?v=1" defer></script>', ''), "consent.js must be loaded exactly once"),
    ("consent.js loses defer", mutate('consent.js?v=1" defer>', 'consent.js?v=1">'), "consent.js must be loaded exactly once"),
    ("cookie banner dropped from generated pages", mutate('{CONSENT_HTML}\n<script src="../consent', '<script src="../consent'), 'expected exactly one id="cookieBanner"'),
    ("banner loses its Privacy button", mutate(' <a class="btn ghost" href="../privacy">Privacy</a>\n', ''), "banner has no Privacy button"),
    ("hyperlink inside the banner text", mutate('either way.</p>', 'either way. <a href="../privacy">Privacy</a></p>'), "must not contain a hyperlink"),
    ("generated page names Google Analytics itself", mutate('<script src="../consent.js?v=1" defer>', '<script>gtag("config","G-PJSXJN5H6G")</script><script src="../consent.js?v=1" defer>'), "must not load or name Google Analytics"),
    ("reject button id missing", mutate('id="cookieReject"', 'id="cookieNo"'), 'expected exactly one id="cookieReject"'),
    ("generated pages lose the About banner item", mutate('<a class="item" href="../about">About</a>', ''), "top banner items are"),
    ("generated pages point About at the wrong page", mutate('href="../about">About</a>', 'href="../abouts">About</a>'), "top banner items are"),
    ("about.html left out of the sitemap", mutate('SITEMAP_ROOT_SKIP = {"404.html"}', 'SITEMAP_ROOT_SKIP = {"404.html", "about.html"}'), "sitemap.xml does not list /about"),
    ("methodology page loses its generated-on date", mutate('    <p class="rk-note">Generated from the site\'s data files on {built}.</p>\n', ''), "expected one generated-on date line"),
    ("methodology page shows a stale generated-on date", mutate("    built_on = date.today()\n", "    built_on = date(2020, 1, 1)\n"), "not today"),
    ('data status page not written', mutate('    write_page("data-status.html", render_data_status_page(catalogue_by_country))\n', ''), 'data-status.html was not generated'),
    ('data status summary off by one', mutate("{cur} up to date, {wait} awaiting", "{cur + 1} up to date, {wait} awaiting"), 'data-status: summary says'),
    ('data status freshness rule ignored', mutate('            if is_fresh(measured, freq):\n                cur += 1', '            if True:\n                cur += 1'), 'behind-schedule rows differ'),
    ('key figures show a stale value', mutate('f\'<td class="kf-v">{esc(fmt_num(e["pts"][-1][1]', 'f\'<td class="kf-v">{esc(fmt_num(e["pts"][-2][1]'), 'its page says'),
    ('key figures Dataset date wrong', mutate('f\'"dateModified": "{stamp}"\', text, count=1)', 'f\'"dateModified": "1999-01-01"\', text, count=1)'), 'dateModified does not match'),
    ('v1.9.28 duplicate date left in place', mutate('    text = re.sub(r\'\\n  "dateModified": "\\d{4}-\\d{2}-\\d{2}",(?=\\n  "isAccessibleForFree")\', "", text, count=1)\n', ''), 'dateModified keys'),
    ('key figures block written twice', mutate('        text = page_html[:old.start()] + block + page_html[old.end():]', '        text = page_html[:old.start()] + block + block + page_html[old.end():]'), 'blocks'),
    ('feed publisher differs from the page', mutate('        pub, code = kf_publisher(src), short_source(src)[1]', '        pub, code = short_source(src)'), 'feed and page disagree'),
    ('llms.txt drops an economy', mutate('    for country, name, cslug in sorted(done, key=lambda t: t[1]):', '    for country, name, cslug in sorted(done, key=lambda t: t[1])[1:]:'), 'llms.txt economies differ'),
    ('awaiting registry ignored', mutate('                if (country, e["key"]) in slow and awaiting_ok(', '                if False and awaiting_ok('), 'awaiting rows differ'),
    ('awaiting ignores the confirmed-recently rule', mutate('AWAITING_CONFIRM_DAYS = 3   ', 'AWAITING_CONFIRM_DAYS = -1  '), 'awaiting rows differ'),
    ('awaiting ignores the cap', mutate('    return (today - period_end_date(period_from)).days <= AWAITING_CAP_DAYS.get(freq, 0)', '    return True'), 'awaiting rows differ'),
    ('awaiting count missing from the summary', mutate("{wait} awaiting the publisher's next release", "{wait + 1} awaiting the publisher's next release"), 'data-status: summary says'),
    ('economy row loses its awaiting count', mutate('<td>{r["current"]}</td><td>{r["awaiting"]}</td><td>{r["late"]}</td>', '<td>{r["current"]}</td><td>0</td><td>{r["late"] + r["awaiting"]}</td>'), 'row says'),
    ('data status drops an economy', mutate('        cur = late = wait = 0\n        upcoming = []\n', '        if country == "UK":\n            continue\n        cur = late = wait = 0\n        upcoming = []\n'), 'does not list exactly the published economies'),
    ('data status last-checked time wrong', mutate('esc(fmt_utc(r["updated"]))', 'esc(fmt_utc(None))'), 'last checked'),
    ('data status overlay rows dropped', mutate('for key, note in sorted((data.get("overlay_notes") or {}).items()):', 'for key, note in []:'), 'overlay rows'),
    ('data status loses its generated-on date', mutate('    <p class="rk-note">Generated from the site\'s data files on {generated}.</p>\n    <div class="doc-actions"><a class="btn" href="../contact">Report a problem</a>', '<div class="doc-actions"><a class="btn" href="../contact">Report a problem</a>'), 'data-status.html: expected one generated-on date line'),
    ("rolling three-month figures measured from their middle month again", mutate('    if freq == "months" and is_rolling3m(country, key):\n        y, mo', '    if False:\n        y, mo'), "dot is"),
    ("indicator pages ignore the rolling-window rule", mutate('    fresh = is_fresh(freshness_period(country, key, latest_p, freq), freq)', '    fresh = is_fresh(latest_p, freq)'), "indicator page dot is"),
    ("rankings ignore the rolling-window rule", mutate('        fresh = is_fresh(freshness_period(c, r.get("key"), r["latest_period"], r["freq"]), r["freq"])', '        fresh = is_fresh(r["latest_period"], r["freq"])'), "its indicator page says"),
    ("data status page gets an outline button", mutate('<a class="btn" href="../methodology-by-economy">Methodology by economy</a>', '<a class="btn ghost" href="../methodology-by-economy">Methodology by economy</a>'), "data-status.html: an outline button"),
    ("methodology-by-economy gets an outline button", mutate('class="btn" href="methodology">General methodology', 'class="btn ghost" href="methodology">General methodology'), "methodology-by-economy.html: an outline button"),
    ("generated pages back to Methodology before About", mutate('<a class="item" href="../about">About</a>\n <a class="item" href="../methodology">Methodology</a>', '<a class="item" href="../methodology">Methodology</a>\n <a class="item" href="../about">About</a>'), "top banner items are"),
    ("generator prints no summary", mutate('print(f"Generated {generated} indicator pages', 'print(f"Built {generated} indicator pages'), "printed no"),
]
for name, text, expect in MUTS:
    caught(name, run_gate(text), expect)

# ---------------------------------------------------------------- doctored data
def cross_year(d):
    p = d / "data-uk.json"
    j = json.loads(p.read_text(encoding="utf-8"))
    pts = j["series"]["unemployment"]["points"]
    # the latest rolling value is now centred on December: November 2026 to January 2027
    pts.append(["2026-08", 4.8]), pts.append(["2026-09", 4.8]), pts.append(["2026-10", 4.7]), pts.append(["2026-11", 4.7]), pts.append(["2026-12", 4.6])
    p.write_text(json.dumps(j), encoding="utf-8")


def basis_shows(d):
    p = d / "data-uk.json"
    j = json.loads(p.read_text(encoding="utf-8"))
    pts = j["series"]["unemployment"]["points"]
    assert pts[-2][0] == "2026-06" and pts[-4][0] == "2026-04", f"data moved on: {pts[-4:]}"
    pts[-2][1] = round(pts[-4][1] + 0.7, 1)       # the previous month now differs from three months ago
    p.write_text(json.dumps(j), encoding="utf-8")


for name, edit in (("cross-year rolling range", cross_year), ("ranking comparison basis", basis_shows)):
    d = repo_copy(edit)
    try:
        r = run_gate(repo=d)
        check(r.returncode == 0, f"{name}: the repo's generator must pass doctored data: {r.stdout[-300:]} {r.stderr[-200:]}")
        if name == "ranking comparison basis":
            # the VALUE message ("UK change -0.6, expected -0.2"), not the tooltip one ("UK change tooltip is ...")
            caught(f"{name} with the ranking fix reverted", run_gate(V1912, repo=d), re.compile(r"UK change -?\d"))
        else:
            wrong_year = mutate("    ey, em = (y, m + 1) if m < 12 else (y + 1, 1)\n", "    ey, em = (y, m + 1) if m < 12 else (y, 1)\n")
            caught(f"{name} with a wrong year rollover", run_gate(wrong_year, repo=d), "title says")
    finally:
        shutil.rmtree(d, ignore_errors=True)

# ---------------------------------------------------------------- consent.js and root pages (v1.9.19-20)
CJS = (ROOT / "consent.js").read_text(encoding="utf-8")


def cjs_edit(old, new):
    assert CJS.count(old) == 1, f"consent.js anchor not unique: {old[:60]!r}"

    def edit(d):
        (d / "consent.js").unlink()                      # repo_copy symlinks it: replace the link with a changed copy
        (d / "consent.js").write_text(CJS.replace(old, new), encoding="utf-8")
    return edit


def page_edit(name, old, new):
    src = (ROOT / name).read_text(encoding="utf-8")
    assert src.count(old) >= 1, f"{name}: anchor missing: {old[:60]!r}"

    def edit(d):
        (d / name).unlink()
        (d / name).write_text(src.replace(old, new, 1), encoding="utf-8")
    return edit


PRIV = '<a href="privacy">Privacy</a> &middot; '
REPO_MUTS = [
    ("consent.js: GA loads on every page load", cjs_edit('if (consent === "granted") {\n    loadGA();', 'loadGA();\n  if (consent === "granted") {\n    loadGA();'), "calls loadGA()"),
    ("consent.js: a denied choice also loads GA", cjs_edit('consent === "granted"', 'consent !== "x"'), "not guarded by a saved 'granted'"),
    ("consent.js: Accept no longer loads GA", cjs_edit('    if (banner) banner.classList.remove("show");\n    loadGA();', '    if (banner) banner.classList.remove("show");'), "calls loadGA()"),
    ("consent.js: file missing its measurement ID", cjs_edit('"G-PJSXJN5H6G"', '"G-XXXXXXXXXX"'), "measurement ID"),
    ("markets.html: Privacy link removed", page_edit("markets.html", PRIV, ""), "markets.html: footer has no Privacy link"),
    ("contact.html: Privacy link removed", page_edit("contact.html", PRIV, ""), "contact.html: footer has no Privacy link"),
    ("index.html: footer removed", page_edit("index.html", "<footer", "<div"), "index.html: footer has no Privacy link"),
    ("markets.html: hourly claim back in meta", page_edit("markets.html", "updated automatically, no", "checked hourly, no"), "markets.html: hourly-update claim"),
    ("calendar.html: hourly claim in visible text", page_edit("calendar.html", "<footer>The Economic Atlas", "<footer>Data updated hourly. The Economic Atlas"), "calendar.html: hourly-update claim"),
]
import re as _re


def data_edit(fname, rx, new):
    src = (ROOT / fname).read_text(encoding="utf-8")
    assert _re.search(rx, src), f"{fname}: pattern missing"

    def edit(d):
        (d / fname).unlink()
        (d / fname).write_text(_re.sub(rx, new, src), encoding="utf-8")
    return edit


def drop_page(name):
    def edit(d):
        (d / name).unlink()
    return edit


NAV2 = '<a class="item" href="about">About</a>\n <a class="item" href="methodology">Methodology</a>'
REPO_MUTS += [
    ("uk.html: About item removed from the banner", page_edit("uk.html", NAV2, '<a class="item" href="methodology">Methodology</a>'), "uk.html: top banner items"),
    ("terms.html: banner items out of order", page_edit("terms.html", NAV2, '<a class="item" href="methodology">Methodology</a>\n <a class="item" href="about">About</a>'), "terms.html: top banner items"),
    ("index.html: the About dropdown is back", page_edit("index.html", '<a class="item" href="methodology">Methodology</a>', '<button id="aboutBtn"></button><a class="item" href="methodology">Methodology</a>'), "index.html: the About dropdown is still present"),
    ("about.html: file missing", drop_page("about.html"), "about.html is missing"),
    ("about.html: wrong title", page_edit("about.html", "<title>About \u00b7 The Economic Atlas</title>", "<title>About us \u00b7 The Economic Atlas</title>"), "title is wrong"),
    ("about.html: About not the active item", page_edit("about.html", '<a class="item active" href="about">About</a>', '<a class="item" href="about">About</a>'), "not the active banner item"),
    ("about.html: corrections button not at the top", page_edit("about.html", 'class="btn" href="contact">Report a correction</a> <a class="btn" href="methodology">Methodology</a>', ''), "corrections button is not at the top"),
    ("about.html: caveat no longer first", page_edit("about.html", 'id="not-our-numbers"', 'id="x-numbers"'), "caveat is not the first section"),
    ("about.html: caveat loses 'provided as is'", page_edit("about.html", "provided as is", "provided"), "caveat is missing 'provided as is'"),
    ("about.html: caveat says views, not datapoints", page_edit("about.html", "datapoints are calculated by us", "views are calculated by us"), "caveat is missing 'datapoints are calculated by us'"),
    ("about.html: counts span id lost", page_edit("about.html", 'id="aboutCount"', 'id="aboutCnt"'), 'expected exactly one id="aboutCount"'),
    ("about.html: fallback shows a number", page_edit("about.html", "economic indicators across dozens of economies", "976 indicators across 62 economies"), "fallback for the counts must not contain a number"),
    ("about.html: counts no longer read from the manifest", page_edit("about.html", 'fetch("indicators/manifest.json")', 'fetch("indicators/manifests.json")'), "counts are not read from"),
    ("about.html: hyperlink inside running text", page_edit("about.html", "Tell us through the Contact page.", 'Tell us through the <a href="contact">Contact</a> page.'), "hyperlink sits inside running text"),
    ("about.html: UN Comtrade named", page_edit("about.html", "including Eurostat,", "including UN Comtrade, Eurostat,"), "UN Comtrade must not be named"),
    ("about.html: an unchecked publisher named", page_edit("about.html", "the Bank of England,", "the Bank of England, the Bank of Japan,"), "names publishers outside the checked list"),
    ("about.html: a checked publisher dropped", page_edit("about.html", "the Bank of England, the Bank of Canada and other", "the Bank of England and other"), "names publishers outside the checked list"),
    ("about.html: em dash in copy", page_edit("about.html", "no opinion.", "no opinion \u2014 x."), "copy rule broken"),
    ("about.html: hourly claim", page_edit("about.html", "refreshed automatically throughout the day", "refreshed hourly"), "about.html: copy rule broken ('hourly')"),
    ("index.html: hourly claim back in its JSON-LD", page_edit("index.html", '"description": "Economic data taken only from official sources', '"description": "Hourly updating economic data taken only from official sources'), "index.html: hourly-update claim"),
    ("style.css: top banner colour drifts again", page_edit("style.css", "nav.top a.item{\n  color:#F2F8FD;", "nav.top a.item{\n  color:#D8E4EF;"), "banner label colours differ"),
    ("style.css: Country Breakdowns colour drifts", page_edit("style.css", ".dropbtn{\n  color:#F2F8FD;", ".dropbtn{\n  color:#D8E4EF;"), "banner label colours differ"),
    ("style.css: current page highlighted again", page_edit("style.css", "nav.top a.item.active{background:none; color:#F2F8FD;}", "nav.top a.item.active{background:var(--navy-2); color:#F2F8FD;}"), "item is highlighted"),
    ("style.css: current page recoloured", page_edit("style.css", "nav.top a.item.active{background:none; color:#F2F8FD;}", "nav.top a.item.active{background:none; color:#fff;}"), "item changes colour"),
    ("style.css: right-push back on the old dropdown", page_edit("style.css", "#navLinks > :first-child{margin-left:auto;}", "#navLinks > .dropdown:first-child{margin-left:auto;}"), "not pushed to the right"),
    ("style.css: alignment pull removed", page_edit("style.css", "@media (min-width:901px){ nav.sub .wrap > :first-child{margin-left:-18px;} }", ""), "not pulled left by exactly"),
    ("style.css: alignment pull off by a few pixels", page_edit("style.css", "margin-left:-18px;} }", "margin-left:-12px;} }"), "not pulled left by exactly"),
    ("style.css: button padding changes but pull does not", page_edit("style.css", "  padding:14px 18px; display:flex; align-items:center; gap:7px;", "  padding:14px 22px; display:flex; align-items:center; gap:7px;"), "not pulled left by exactly"),
    ("style.css: logo gains left padding", page_edit("style.css", "padding:14px 18px 14px 0; margin-right:10px;", "padding:14px 18px 14px 6px; margin-right:10px;"), "the logo has left padding"),
    ("about.html: Data status button removed", page_edit("about.html", '<div class="doc-actions"><a class="btn" href="data-status">Data status</a></div>\n', ''), "no Data status button"),
    ("about.html: an outline button back in the content", page_edit("about.html", '<a class="btn" href="data-status">Data status</a>', '<a class="btn ghost" href="data-status">Data status</a>'), "an outline button in the page content"),
    ("methodology.html: an outline button back in the content", page_edit("methodology.html", 'class="btn" href="contact">Get in touch', 'class="btn ghost" href="contact">Get in touch'), "methodology.html: an outline button"),
    ("doc.css: text capped in width again", page_edit("doc.css", "color:var(--ink);}   /* v1.9.25: full panel width */", "color:var(--ink); max-width:68ch;}"), "capped in width again"),
    ("data files stop mentioning BEA while About names it", data_edit("data-metric-sources.json", r"(?<![A-Za-z])BEA(?![A-Za-z])", "XYZ"), "no data file mentions BEA"),
]
for name, edit, expect in REPO_MUTS:
    d = repo_copy(edit)
    try:
        caught(name, run_gate(repo=d), expect)
    finally:
        shutil.rmtree(d, ignore_errors=True)

print(f"test_generated_pages_gate: {'FAILED' if fails else 'ok'} ({len(fails)} failures, {ran} gate runs)")
sys.exit(1 if fails else 0)
