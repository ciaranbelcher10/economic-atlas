"""Tests for fetch_calendar_nz.py and the OpenDOSM JSON path in fetch_calendar_my.py (v1.7.32).

    python3 tools/test_fetch_calendar_nz.py   -> "N ok, 0 failed"

Fixtures: statsnz_release-calendar.ics (three events verbatim from the Stats NZ
export, plus the key releases in the same format with titles and dates
verbatim from probe_exports of 8 Oct 2026) and opendosm_next_data.html
(pageProps.cal_pubs verbatim from the same probe). Offline, in a temp dir;
the live data-calendar-*.json files are never touched.
"""
import hashlib, json, os, sys, tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import fetch_calendar_nz as N
import fetch_calendar_my as M

F = ROOT / "tools" / "fixtures" / "calendar"
ICS = (F / "statsnz_release-calendar.ics").read_text()
ND = (F / "opendosm_next_data.html").read_text()
GRID = (F / "opendosm_oct2026.html").read_text()
LIVE = [ROOT / "data-calendar-nz.json", ROOT / "data-calendar-my.json"]
H0 = {p: hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None for p in LIVE}

ok = bad = 0
def check(cond, name):
    global ok, bad
    if cond: ok += 1
    else: bad += 1; print("FAIL", name)

# ---- New Zealand parser
ev, pr = N.parse(ICS)
got = {(e["date"], e["concept"]) for e in ev}
check(pr == [], f"Stats NZ export parses cleanly: {pr}")
check(("2026-10-22", "cpi") in got and ("2027-01-27", "cpi") in got, "CPI 22 Oct 2026 and 27 Jan 2027")
check(("2026-11-04", "jobs") in got and ("2026-12-17", "gdp") in got, "labour market 4 Nov, GDP 17 Dec")
check(("2026-10-19", "trade") in got and ("2026-11-18", "ppi") in got, "trade 19 Oct, business price indexes 18 Nov")
check(not any("Selected price" in e["name"] or "Employment indicators" in e["name"] or "migration" in e["name"] for e in ev),
      "other releases (selected prices, employment indicators, migration) excluded")
check(all(e["time"] == "10:45am NZ time" for e in ev), "times read from DTSTART (10:45am NZ time)")
folded = ICS.replace("SUMMARY:Consumers price index: September 2026 quarter", "SUMMARY:Consumers price index: Septem\r\n ber 2026 quarter")
check(any(e["name"] == "Consumers price index (September 2026 quarter)" for e in N.parse(folded)[0]), "folded iCal lines are joined")
check(N.parse("<html>Incapsula incident</html>")[1] != [], "planted fault caught: bot wall instead of iCal")
check(any("Pacific/Auckland" in p for p in N.parse(ICS.replace("TZID=Pacific/Auckland:20261022", "TZID=UTC:20261022"))[1]),
      "planted fault caught: start not in New Zealand time")
check(any("no Consumers price index" in p for p in N.parse(ICS.replace("Consumers price index", "Consumer prices"))[1]),
      "planted fault caught: CPI missing")

# ---- OpenDOSM JSON path
jev, jpr = M.parse_dosm_json(ND)
gev, _ = M.parse_dosm(GRID)
key = lambda L: sorted((e["date"], e["concept"], e["name"]) for e in L)
check(jpr == [] and len(jev) == 8, f"cal_pubs parses to 8 releases: {len(jev)} {jpr}")
check(key(jev) == key(gev), "JSON and rendered grid give identical releases")
check(M.parse_dosm_json(GRID) == (None, []), "page without embedded data -> grid fallback")
bad_nd = ND.replace('"2026-10-19"', '"19 Oct"')
check(any("not a date" in p for p in M.parse_dosm_json(bad_nd)[1]), "planted fault caught: cal_pubs key is not a date")

# ---- end to end, offline
class R:
    def __init__(self, body="", status=200):
        self.status_code, self.text, self.content, self.url = status, body, body.encode(), ""
    def raise_for_status(self):
        if self.status_code >= 400: raise N.requests.HTTPError(str(self.status_code))

class FixedDT(datetime):
    @classmethod
    def now(cls, tz=None): return datetime(2026, 10, 8, 12, tzinfo=timezone.utc)

N.datetime = M.datetime = FixedDT
old = os.getcwd(); os.chdir(tempfile.mkdtemp())
try:
    N.requests.get = lambda url, timeout=0, headers=None: R(ICS)
    rc = N.main(); out = json.loads(Path(N.OUT).read_text())
    check(rc == 0 and len(out["events"]) == 11 and out["country"] == "New Zealand", f"NZ end to end: rc {rc}, {len(out['events'])} events")
    before = Path(N.OUT).read_text()
    N.requests.get = lambda url, timeout=0, headers=None: R("<html>Incapsula incident</html>")
    check(N.main() == 1 and Path(N.OUT).read_text() == before, "NZ bot wall: file untouched")
    N.requests.get = lambda url, timeout=0, headers=None: R("", 403)
    check(N.main() == 1 and Path(N.OUT).read_text() == before, "NZ 403: file untouched")

    class S:
        def __init__(self, pages): self.pages, self.headers = pages, {}
        def get(self, url, timeout=0):
            v = self.pages.get(url)
            return R(status=404) if v is None else R(v)
    M.requests.Session = lambda: S({M.BNM_SEED: (F / "bnm_mps_06112025.html").read_text(), M.DOSM_URL: ND})
    rc = M.main(); out = json.loads(Path(M.OUT).read_text())
    kinds = {e["concept"] for e in out["events"]}
    check(rc == 0 and {"rate_decision", "cpi", "gdp", "jobs", "trade", "ppi"} <= kinds, f"Malaysia via JSON end to end: {sorted(kinds)}")
finally:
    os.chdir(old)

for p in LIVE:
    h = hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None
    check(h == H0[p], f"live {p.name} untouched")
print(f"{ok} ok, {bad} failed")
sys.exit(1 if bad else 0)
