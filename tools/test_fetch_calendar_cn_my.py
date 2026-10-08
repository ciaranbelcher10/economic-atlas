"""Tests for fetch_calendar_cn.py and fetch_calendar_my.py (v1.7.30).

    python3 tools/test_fetch_calendar_cn_my.py   -> "N ok, 0 failed"

Fixtures in tools/fixtures/calendar/ are trimmed from the real pages saved by
tools/probe_calendar.py on 8 Oct 2026. Runs offline (requests is mocked) in a
temporary directory; the live data-calendar-*.json files are never touched
(checked at the end).
"""
import hashlib, json, os, sys, tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import fetch_calendar_cn as C
import fetch_calendar_my as M

F = ROOT / "tools" / "fixtures" / "calendar"
NBS, IDX = (F / "nbs_2026.html").read_text(), (F / "nbs_index.html").read_text()
BNM, DOSM = (F / "bnm_mps_06112025.html").read_text(), (F / "opendosm_oct2026.html").read_text()
LIVE = [ROOT / "data-calendar-cn.json", ROOT / "data-calendar-my.json"]
H0 = {p: hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None for p in LIVE}

ok = bad = 0
def check(cond, name):
    global ok, bad
    if cond: ok += 1
    else: bad += 1; print("FAIL", name)

# ---- China: parser
ev, pr = C.parse_year(NBS, 2026, "src")
by = {(e["date"], e["concept"]) for e in ev}
check(pr == [] and len(ev) == 28, f"NBS 2026 parses cleanly to 28 events: {len(ev)} {pr}")
check(("2026-10-19", "gdp") in by, "Q3 GDP on 19 Oct 2026")
check(("2026-10-14", "cpi") in by and ("2026-10-14", "ppi") in by, "CPI and PPI on 14 Oct 2026")
check(not any(c == "gdp" and d[5:7] not in ("01", "04", "07", "10") for d, c in by), "GDP only in Jan/Apr/Jul/Oct (monthly activity is not GDP)")
check({c for _, c in by} == {"gdp", "cpi", "ppi"}, "only gdp/cpi/ppi (no PMI)")
check(sorted(C.year_links(IDX))[-1] == 2026, "index lists the 2026 table")
_, pr = C.parse_year(NBS.replace("14/Wed", "14/Thu", 1), 2026, "src")
check(any("table says Thu" in p for p in pr), "planted fault caught: weekday does not match date")
_, pr = C.parse_year(NBS.replace("Consumer Price Index", "Consumer Prices", 1), 2026, "src")
check(any("row not found" in p for p in pr), "planted fault caught: CPI row missing")

# ---- Malaysia: parsers
d, pr = M.parse_bnm(BNM)
check(pr == [] and [x.isoformat() for x in d] == ["2026-01-22", "2026-03-05", "2026-05-07", "2026-07-09", "2026-09-03", "2026-11-05"], f"BNM 2026 schedule: {d} {pr}")
check(M.BNM_URL.format(d=max(d)).endswith("monetary-policy-statement-05112026"), "chain to the 5 Nov 2026 statement")
_, pr = M.parse_bnm(BNM.replace("5 November 2026 (Thursday)", "5 November 2026 (Friday)"))
check(any("table says Friday" in p for p in pr), "planted fault caught: BNM weekday mismatch")
check(M.parse_bnm("<p>Monetary Policy Statement with no schedule</p>") == ([], []), "statement without a schedule: no dates, no error")
ev, pr = M.parse_dosm(DOSM)
got = [(e["date"], e["concept"]) for e in ev]
check(pr == [] and ("2026-10-19", "cpi") in got and ("2026-10-16", "gdp") in got and ("2026-10-09", "jobs") in got, f"OpenDOSM October releases: {got}")
check(("2026-09-28", "trade") in got and not any(x[0] == "2026-10-28" and x[1] == "trade" and "Aug" in e["name"] for x, e in zip(got, ev)), "dim cells before the 1st belong to September")
check(not any("Indices" in e["name"] or "Rubber" in e["name"] for e in ev), "unrelated releases (trade indices, rubber) excluded")
_, pr = M.parse_dosm(DOSM.replace("October 2026", "Octobre 2026"))
check(pr != [], "planted fault caught: OpenDOSM month label missing")

# ---- end to end, offline, in a temp dir
class R:
    def __init__(self, body=None, status=200, url=""):
        self.status_code, self.text, self.url = status, body or "", url
        self.content = (body or "").encode()
    def raise_for_status(self):
        if self.status_code >= 400: raise C.requests.HTTPError(str(self.status_code))

class S:
    def __init__(self, pages): self.pages, self.headers = pages, {}
    def get(self, url, timeout=0):
        v = self.pages.get(url)
        if v is None: return R(status=404, url=url)
        if isinstance(v, int): return R(status=v, url=url)
        return R(v, url=url)

class FixedDT(datetime):
    @classmethod
    def now(cls, tz=None): return datetime(2026, 10, 8, 12, tzinfo=timezone.utc)

C.datetime = M.datetime = FixedDT
nbs_url = C.INDEX + "202512/t20251226_1962154.html"
old = os.getcwd(); tmp = tempfile.mkdtemp(); os.chdir(tmp)
try:
    C.requests.Session = lambda: S({C.INDEX: IDX, nbs_url: NBS})
    rc = C.main(); out = json.loads(Path(C.OUT).read_text())
    check(rc == 0 and all(e["date"] >= "2026-10-08" for e in out["events"]) and len(out["events"]) == 7, f"China end to end: rc {rc}, {len(out['events'])} upcoming events")
    before = Path(C.OUT).read_text()
    C.requests.Session = lambda: S({C.INDEX: IDX, nbs_url: NBS.replace("14/Wed", "14/Thu", 1)})
    check(C.main() == 1 and Path(C.OUT).read_text() == before, "China: bad table is not written; previous file kept")

    pages = {M.BNM_SEED: BNM, M.DOSM_URL: DOSM}
    M.requests.Session = lambda: S(pages)
    rc = M.main(); out = json.loads(Path(M.OUT).read_text())
    kinds = {e["concept"] for e in out["events"]}
    check(rc == 0 and {"rate_decision", "cpi", "gdp", "jobs", "trade", "ppi"} <= kinds, f"Malaysia end to end: {sorted(kinds)}")
    check([e["date"] for e in out["events"] if e["concept"] == "rate_decision"] == ["2026-11-05"], "only the upcoming MPC date (5 Nov) is kept")
    M.requests.Session = lambda: S({M.BNM_SEED: 500, M.DOSM_URL: DOSM})
    rc = M.main(); out = json.loads(Path(M.OUT).read_text())
    check(rc == 0 and any(e["concept"] == "rate_decision" for e in out["events"]), "BNM down: previous BNM events carried forward")
    before = Path(M.OUT).read_text()
    M.requests.Session = lambda: S({M.BNM_SEED: 500, M.DOSM_URL: 500})
    check(M.main() == 1 and Path(M.OUT).read_text() == before, "both sources down: file untouched")
finally:
    os.chdir(old)

for p in LIVE:
    h = hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None
    check(h == H0[p], f"live {p.name} untouched by the test")
print(f"{ok} ok, {bad} failed")
sys.exit(1 if bad else 0)
