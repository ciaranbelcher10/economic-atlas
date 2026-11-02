"""v1.9.60: calendar round cal12. Pakistan (SBP MPC dates) and Argentina (INDEC headline releases).

    python3 tools/test_fetch_calendar_cal12.py   -> "N ok, 0 failed"

Fixtures are raw pages saved by probe cal12 on 2 Nov 2026 (byte-for-byte). Offline: requests
is replaced, runs write into a temp folder, live data-calendar-*.json files are checked unchanged.
"""
import hashlib, io, json, os, re, sys, tempfile
from contextlib import redirect_stdout, redirect_stderr
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import requests  # noqa: E402
import fetch_calendar_pk as PK, fetch_calendar_ar as AR  # noqa: E402

F = ROOT / "tools" / "fixtures" / "calendar"
def rd(n):
    with open(F / n, encoding="utf-8", newline="") as f:
        return f.read()
SBP, NOV, DEC = rd("sbp_monetary_policy_202611.html"), rd("indec_mes_noviembre_2026.html"), rd("indec_mes_diciembre_2026.html")
LIVE = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in ROOT.glob("data-calendar-*.json")}
ok = bad = 0
def check(c, n):
    global ok, bad
    if c: ok += 1
    else: bad += 1; print("FAIL", n)
def no_dash(ev): return all("\u2014" not in json.dumps(e, ensure_ascii=False) for e in ev)

# ---------- Pakistan ----------
check(len(SBP) > 100000, "SBP fixture is the real page")
ev, pr = PK.parse(SBP)
d = [e["date"] for e in ev]
check(pr == [], f"pk parses cleanly: {pr}")
check(d == ["2026-07-27", "2026-09-14", "2026-10-26", "2026-12-14", "2027-01-25", "2027-03-08", "2027-04-26", "2027-06-17"],
      f"pk: the eight FY27 MPC dates: {d}")
check(not {"2026-07-28", "2026-08-21", "2026-08-10", "2026-12-15", "2027-01-08"} & set(d), "pk: briefings, minutes and reports left out")
check(all(e["concept"] == "rate_decision" and e["country"] == "Pakistan" and e["time"] is None and e["source"] == PK.SRC
          for e in ev) and no_dash(ev), "pk: event fields, no invented time")
check(any("bot wall" in p for p in PK.parse("<html>Access denied</html>")[1]), "pk: wall page caught")
check(any("not 'MPC Meeting Date'" in p for p in PK.parse(SBP.replace("MPC Meeting Date", "Analyst Briefing", 1))[1]),
      "pk: a reordered table is caught")
check(any("not read" in p for p in PK.parse(SBP.replace("\n                14-Dec-26\n", "\n                Dec 14\n", 1))[1]), "pk: unreadable date caught")
check(any("impossible" in p for p in PK.parse(SBP.replace("\n                14-Dec-26\n", "\n                31-Feb-27\n", 1))[1]), "pk: impossible date caught")
check(any("order" in p for p in PK.parse(SBP.replace("\n                14-Dec-26\n", "\n                14-Dec-27\n", 1))[1]), "pk: out-of-order caught")
check(PK.parse(SBP.replace("\n                14-Dec-26\n", "\n", 1))[1] == [], "pk: a blank first cell is skipped")

# ---------- Argentina ----------
ev, pr = AR.parse_month(NOV, 2026, 11)
check(pr == [], f"ar nov parses: {pr}")
check([(e["date"], e["concept"]) for e in ev] == [("2026-11-12", "cpi"), ("2026-11-17", "ppi"), ("2026-11-19", "trade")],
      f"ar nov: CPI 12th, SIPM 17th, ICA 19th: {[(e['date'], e['concept']) for e in ev]}")
check(ev[0]["name"] == "INDEC consumer price index (IPC), October 2026" and ev[0]["time"] == "4:00pm Buenos Aires time", f"ar: name and time {ev[0]}")
ev2, pr2 = AR.parse_month(DEC, 2026, 12)
check(pr2 == [] and [(e["date"], e["concept"]) for e in ev2] == [("2026-12-15", "cpi"), ("2026-12-16", "gdp"), ("2026-12-17", "ppi"),
                                                                ("2026-12-18", "trade"), ("2026-12-18", "jobs")], f"ar dec: {pr2} {ev2}")
check(any(e["name"] == "INDEC GDP advance estimate, Q3 2026" for e in ev2), "ar: quarter written Q3 2026")
check(not any("EMAE" in e["name"] or "canasta" in e["name"].lower() for e in ev + ev2), "ar: EMAE and other releases left out")
check(all(e["country"] == "Argentina" and e["source"] == AR.SRC for e in ev + ev2) and no_dash(ev + ev2), "ar: event fields")
check(any("not the month asked for" in p for p in AR.parse_month(NOV, 2026, 12)[1]), "ar: wrong month caught")
check(any("not the month asked for" in p for p in AR.parse_month("<html>Request Rejected</html>", 2026, 11)[1]), "ar: wall caught")
check(any("CPI releases" in p for p in AR.parse_month(NOV.replace("&#205;ndice de precios al consumidor (IPC). Cobertura nacional", "IPC"), 2026, 11)[1]),
      "ar: a month without CPI is caught")
check(any("not followed by a weekday" in p for p in AR.parse_month(NOV.replace("MARTES", "XYZ", 1), 2026, 11)[1]), "ar: broken day row caught")
check(any("no time line" in p for p in AR.parse_month(NOV.replace("16:00hs", "later", 1), 2026, 11)[1]), "ar: missing time caught")
check(AR.period_en("Primer trimestre de 2027") == "Q1 2027" and AR.period_en("Enero de 2027") == "January 2027" and AR.period_en("Año 2025") == "",
      "ar: period translation")
check(AR.months_from(date(2026, 11, 2)) == [(2026, 11), (2026, 12), (2027, 1)], "ar: three months, across the year end")

# ---------- main(): writes on success, keeps the file and warns on failure, never fails ----------
class R:
    def __init__(s, text, code=200): s.content, s.status_code = text.encode(), code
    def raise_for_status(s):
        if s.status_code != 200: raise requests.HTTPError(str(s.status_code))
class Sess:
    def __init__(s, m): s.m, s.headers = m, {}
    def get(s, url, timeout=None, headers=None):
        v = s.m.get(url, R("", 404))
        if isinstance(v, Exception): raise v
        return v
def run(mod, pages, existing=None):
    old_get, old_sess = requests.get, requests.Session
    requests.get = lambda url, headers=None, timeout=None: Sess(pages).get(url)
    requests.Session = lambda: Sess(pages)
    cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        if existing is not None:
            Path(mod.OUT).write_text(existing)
        out, err = io.StringIO(), io.StringIO()
        try:
            with redirect_stdout(out), redirect_stderr(err):
                rc = mod.main()
            body = Path(mod.OUT).read_text() if Path(mod.OUT).exists() else None
        finally:
            os.chdir(cwd); requests.get, requests.Session = old_get, old_sess
    return rc, body, out.getvalue(), err.getvalue()

OLD = '{"events": [{"date": "2026-12-14", "name": "kept"}]}'
rc, body, out, err = run(PK, {PK.URL: R(SBP)}, OLD)
check(rc == 0 and body != OLD and json.loads(body)["events"][0]["date"] >= "2026-11-02" and "SBP:" in out, f"pk: good page writes: {out}{err}")
for bad_page in [R("", 403), R("<html>blocked</html>"), requests.ConnectionError("x")]:
    rc, body, out, err = run(PK, {PK.URL: bad_page}, OLD)
    check(rc == 0 and body == OLD and err.startswith("WARNING SBP:"), f"pk: failure keeps file and warns: {err}")
rc, body, out, err = run(PK, {PK.URL: R("", 500)}, None)
check(rc == 0 and body is None and "WARNING SBP" in err, "pk: failed first run writes nothing")

today = date.today()
months = AR.months_from(today)
def ar_pages(fail_index=None):
    pages = {}
    for k, (y, m) in enumerate(months):
        src = NOV.replace("Noviembre 2026", f"{AR.MESES[m]} {y}", 1)
        pages[AR.URL.format(mes=AR.MESES[m], year=y)] = R("", 503) if k == fail_index else R(src)
    return pages
rc, body, out, err = run(AR, ar_pages(), OLD)
check(rc == 0 and body != OLD and "INDEC:" in out, f"ar: three good months write: {out}{err}")
rc, body, out, err = run(AR, ar_pages(fail_index=2), OLD)
check(rc == 0 and body == OLD and err.startswith("WARNING INDEC:"), f"ar: one bad month keeps the whole file: {err}")
rc, body, out, err = run(AR, ar_pages(fail_index=0), None)
check(rc == 0 and body is None, "ar: failed first run writes nothing")

# ---------- wiring ----------
html = (ROOT / "calendar.html").read_text(encoding="utf-8")
yml = (ROOT / ".github" / "workflows" / "update-calendar.yml").read_text()
files = re.search(r"var CALENDAR_DATA_FILES = \[([\s\S]*?)\];", html).group(1)
picker = re.search(r"var COUNTRIES_WITH_DATA = \[([\s\S]*?)\]", html).group(1)
asia = re.search(r'\{name: "Asia", countries: \[([^\]]*)\]', html).group(1)
check('"data-calendar-pk.json"' in files and '"data-calendar-ar.json"' in files, "both files loaded by the page")
check('"Pakistan"' in picker and '"Argentina"' in picker, "both countries in the picker")
check('"Pakistan"' in asia, "Pakistan in the Asia region")
check('Pakistan:"#DE481E"' in html, "Pakistan has the sitewide colour")
check(yml.index("fetch_calendar_sg.py") < yml.index("python fetch_calendar_pk.py") < yml.index("python fetch_calendar_ar.py") < yml.index("calendar_history.py"),
      "pk and ar steps run before past events are restored")
for n, h in LIVE.items():
    check(hashlib.sha256((ROOT / n).read_bytes()).hexdigest() == h, f"{n} untouched")
# v1.9.60: no "file must not exist" check here; once the workflow runs, the bot commits that file.
# The hash loop above already proves the test never writes a live data-calendar-*.json.
print(f"{ok} ok, {bad} failed")
sys.exit(1 if bad else 0)
