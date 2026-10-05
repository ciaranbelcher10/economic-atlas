"""v1.6.48 gate: sitemap lastmod moves only when a generated page changes.

Back-dates every generated URL in a copy of the repo, re-runs the generator
twice and checks: unchanged pages keep the back-dated lastmod; a page whose
data changed gets today's date; only the refresh stamp changing is not a
change; embeds stay noindex and unlisted.
    python3 tools/test_sitemap_lastmod.py   -> "N ok, 0 failed"
"""
import json, os, re, shutil, subprocess, sys, tempfile
from datetime import date
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ok = bad = 0
def check(name, cond, detail=""):
    global ok, bad
    if cond: ok += 1
    else: bad += 1; print("FAIL", name, detail)

tmp = tempfile.mkdtemp()
try:
    shutil.copytree(ROOT, os.path.join(tmp, "r"), ignore=shutil.ignore_patterns(".git", "node_modules", "og"))
    R = os.path.join(tmp, "r")
    run = lambda: subprocess.run([sys.executable, "generate_indicator_pages.py"], cwd=R, capture_output=True, text=True)
    r = run(); check("first run ok", r.returncode == 0, r.stderr[-300:])
    sm = os.path.join(R, "sitemap.xml")
    s = open(sm).read()
    s = re.sub(r"(<loc>https://theeconomicatlas\.com/(?:indicators|rankings)[^<]*</loc><lastmod>)[^<]+", r"\g<1>2000-01-01", s)
    open(sm, "w").write(s)
    # only the refresh stamp changes: bump "updated" in one data file
    f = os.path.join(R, "data-se.json"); d = json.load(open(f))
    d["updated"] = "2099-01-01T00:00:00Z"; json.dump(d, open(f, "w"))
    # a real change: move the latest UK unemployment point
    f2 = os.path.join(R, "data-uk.json"); u = json.load(open(f2))
    u["series"]["unemployment"]["points"][-1][1] += 0.3; json.dump(u, open(f2, "w"))
    r = run(); check("second run ok", r.returncode == 0, r.stderr[-300:])
    s = open(sm).read()
    lm = dict(re.findall(r"<loc>([^<]+)</loc><lastmod>([^<]+)</lastmod>", s))
    today = date.today().isoformat()
    base = "https://theeconomicatlas.com/"
    check("changed page dated today", lm.get(base + "indicators/uk-unemployment-rate") == today, lm.get(base + "indicators/uk-unemployment-rate"))
    check("refresh-stamp-only page keeps old date", lm.get(base + "indicators/sweden-gdp") == "2000-01-01", lm.get(base + "indicators/sweden-gdp"))
    check("unrelated page keeps old date", lm.get(base + "indicators/japan-gdp") == "2000-01-01", lm.get(base + "indicators/japan-gdp"))
    moved = [u for u, v in lm.items() if v == today and "/indicators/" in u]
    # UK pages show the new figure; other countries' unemployment pages show
    # their place in the ranking, which the UK's move can shift. Nothing else.
    stray = [u for u in moved if "/indicators/uk-" not in u and not u.endswith("-unemployment-rate")]
    check("only UK pages and unemployment rank neighbours moved", moved and not stray, stray[:5])
    check("no embed listed", not any("/embed/" in u for u in lm))
    eh = open(os.path.join(R, "embed", "uk-gdp.html")).read(4000)
    check("embed noindex", '<meta name="robots" content="noindex">' in eh)
finally:
    shutil.rmtree(tmp)
print(f"{ok} ok, {bad} failed")
sys.exit(1 if bad else 0)
