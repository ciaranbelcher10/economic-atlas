#!/usr/bin/env python3
"""v1.9.127: the "Latest:" banner reserves its row; methodology themes; population is not money.

 1. generate_indicator_pages.mark_newdata_expected: marks the banner data-expect only when a series in the
    data file was first seen under 2 days ago; removes the mark when nothing is fresh; idempotent; touches
    nothing else on the page.
 2. style.css: the reserved banner is laid out but invisible; the banner is always one line.
 3. Every country page's renderNewDataBanner() releases the reservation first (migrate_v19127).
 4. methodology_by_economy.THEMES covers GDP per capita (Output) and Population.
 5. invariants_gate.js treats the population unit "people" as a count.
Measured in Chromium (1350px, a page with fresh data): UK page CLS 0.194 before, 0.060 after.
Run: python3 tools/test_v19127.py
"""
import datetime as dt, glob, json, os, re, subprocess, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import generate_indicator_pages as g   # noqa: E402
import methodology_by_economy as mbe   # noqa: E402
checks, fails = 0, []
def check(ok, msg):
    global checks; checks += 1
    if not ok: fails.append(msg)

page = open(os.path.join(ROOT, "uk.html"), encoding="utf-8").read()
data = json.load(open(os.path.join(ROOT, "data-uk.json"), encoding="utf-8"))
key = sorted(data["new_points_meta"])[0]
seen = dt.datetime.fromisoformat(data["new_points_meta"][key]["first_seen"].replace("Z", "+00:00"))
TAG, MARKED = '<div class="newdata" id="newdata" hidden>', '<div class="newdata" id="newdata" hidden data-expect="1">'
fresh = g.mark_newdata_expected(page.replace(MARKED, TAG), data, seen + dt.timedelta(hours=5))
check(fresh.count(MARKED) == 1, "fresh release (5 hours old): banner marked data-expect")
check(fresh.replace(MARKED, TAG) == page.replace(MARKED, TAG), "nothing else on the page changes")
check(g.mark_newdata_expected(fresh, data, seen + dt.timedelta(hours=5)) == fresh, "idempotent")
latest = max(dt.datetime.fromisoformat(m["first_seen"].replace("Z", "+00:00")) for m in data["new_points_meta"].values())
stale = g.mark_newdata_expected(fresh, data, latest + dt.timedelta(days=2, minutes=1))
check(MARKED not in stale and stale.count(TAG) == 1, "nothing under 2 days old: mark removed")
bad = json.loads(json.dumps(data)); bad["new_points_meta"] = {"not_a_series": {"first_seen": seen.isoformat()}}
check(MARKED not in g.mark_newdata_expected(page, bad, seen), "a key with no series does not count")
check(MARKED not in g.mark_newdata_expected(page, {"series": data["series"]}, seen), "no new_points_meta: not marked")

css = open(os.path.join(ROOT, "style.css"), encoding="utf-8").read()
check(".newdata[hidden][data-expect]{display:flex; visibility:hidden;}" in css, "reserved banner laid out but invisible")
check(re.search(r"\.newdata #newdataText\{flex-wrap:nowrap; white-space:nowrap; overflow-x:auto", css), "banner always one line")

pages = [f for f in glob.glob(os.path.join(ROOT, "*.html")) if "function renderNewDataBanner(meta){" in open(f, encoding="utf-8").read()]
check(len(pages) == 62, f"62 country pages carry the banner ({len(pages)})")
for f in pages:
    s = open(f, encoding="utf-8").read()
    i = s.index("function renderNewDataBanner(meta){")
    head = s[i:i + 260]
    check('_nd.removeAttribute("data-expect")' in head and head.index("removeAttribute") < head.index("if(!meta) return;"),
          os.path.basename(f) + ": reservation released before anything else")
    check('<div class="newdata" id="newdata" hidden' in s, os.path.basename(f) + ": banner markup the generator can find")
r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "migrate_v19127.py"), ROOT], capture_output=True, text=True)
check(r.stdout.strip() == "62 page(s) checked, 0 changed", "migrate_v19127 idempotent: " + r.stdout.strip())

theme = dict((s, n) for n, slugs in mbe.THEMES for s in slugs)
check(theme.get("gdp-per-capita") == "Output" and theme.get("population") == "Population", "methodology themes for GDP per capita and Population")
missing = [m["slug"] for m in g.METRICS if m["slug"] not in theme] if hasattr(g, "METRICS") else []
check(not missing, f"every metric has a methodology theme: {missing}")
gate = open(os.path.join(ROOT, "tools", "invariants_gate.js"), encoding="utf-8").read()
check('u === "people"' in gate, "invariants gate: population unit is a count")

print(f"test_v19127: {checks} checks, {len(fails)} failed")
for m in fails: print("  FAIL", m)
sys.exit(1 if fails else 0)
