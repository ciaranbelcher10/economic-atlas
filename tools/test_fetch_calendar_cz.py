"""Offline tests for fetch_calendar_cz.py (v1.7.33), against saved copies of
the official pages. Run: python3 tools/test_fetch_calendar_cz.py

Fixtures (tools/fixtures/calendar/):
  cnb_bank_board.html       the CNB Bank Board page exactly as served, 8 Oct 2026
  czso_udalosti_synth.json  CZSO events API reply rebuilt from the live reply of
                            8 Oct 2026 (same keys and values; titles and dates as
                            listed that day, cut to Oct 2026 - Mar 2027)
  czso_udalosti_*.json      if present, the raw live reply is parsed too
"""
from __future__ import annotations

import copy, io, json, os, sys, tempfile
from contextlib import redirect_stderr, redirect_stdout
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
FIX = ROOT / "tools" / "fixtures" / "calendar"
LIVE = ROOT / "data-calendar-cz.json"
import hashlib
H0 = hashlib.sha256(LIVE.read_bytes()).hexdigest() if LIVE.exists() else None

import fetch_calendar_cz as F  # noqa: E402

OK, BAD = [0], []
def check(cond, msg):
    if cond: OK[0] += 1
    else: BAD.append(msg); print("FAIL", msg)

CNB = (FIX / "cnb_bank_board.html").read_text(encoding="utf-8")
CZSO = json.loads((FIX / "czso_udalosti_synth.json").read_text(encoding="utf-8"))
TODAY = date(2026, 10, 8)

# --- CNB
ev, prob = F.parse_cnb(CNB)
check(not prob, f"CNB page parses cleanly: {prob}")
check([e["date"] for e in ev] == ["2026-02-05", "2026-03-19", "2026-05-07", "2026-06-18",
                                   "2026-08-06", "2026-09-17", "2026-11-05", "2026-12-17"],
      f"CNB: the eight 2026 monetary policy meetings: {[e['date'] for e in ev]}")
check(all(e["concept"] == "rate_decision" and e["time"] == "2:30pm Prague time" for e in ev), "CNB events are 2:30pm rate decisions")
_, p = F.parse_cnb(CNB.replace("on monetary policy", "on other matters"))
check(p and "no monetary policy meeting" in p[0], "CNB: a table without policy meetings is refused")
_, p = F.parse_cnb("<html>moved</html>")
check(p and "no Bank Board meeting table" in p[0], "CNB: a page without the table is refused")
_, p = F.parse_cnb(CNB.replace("5 November 2026", "7 November 2026"))
check(any("not a weekday" in x for x in p), f"CNB: a weekend date is refused: {p}")
_, p = F.parse_cnb(CNB.replace("17 December 2026", "31 February 2026"))
check(any("impossible date" in x for x in p), "CNB: an impossible date is refused")
ev2, _ = F.parse_cnb(CNB.replace("<td style=\"text-align: right;\">5 November 2026</td>",
                                 "<!-- <td>5 November 2026</td><td>Bank Board meeting on monetary policy</td> -->"
                                 "<td style=\"text-align: right;\">5 November 2026</td>"))
check(len(ev2) == 8, "CNB: commented-out markup is ignored, not counted twice")

# --- CZSO
ev, prob = F.parse_czso(CZSO)
check(not prob, f"CZSO reply parses cleanly: {prob}")
by = {}
for e in ev:
    by.setdefault(e["concept"], []).append(e["date"])
check(by.get("cpi") == ["2026-10-13", "2026-11-04", "2026-11-10", "2026-12-04", "2026-12-10", "2027-01-07", "2027-01-13"],
      f"CZSO cpi: CPI and flash estimates: {by.get('cpi')}")
check(by.get("gdp") == ["2026-10-30", "2026-12-01", "2027-01-29"], f"CZSO gdp: {by.get('gdp')}")
check(by.get("jobs") == ["2026-10-30", "2026-12-01", "2027-01-07"], f"CZSO jobs: {by.get('jobs')}")
check(by.get("trade") == ["2026-11-06", "2026-12-07", "2027-01-06", "2027-03-09"],
      f"CZSO trade: goods trade only, not trade price indices: {by.get('trade')}")
check(by.get("ppi") == ["2026-10-16", "2026-11-16", "2026-12-16", "2027-01-19"], f"CZSO ppi: {by.get('ppi')}")
check(set(by) == {"cpi", "gdp", "jobs", "trade", "ppi"}, f"no retail, industry or fiscal releases: {set(by)}")
names = {e["date"]: e["name"] for e in ev if e["concept"] == "cpi"}
check(names["2026-10-13"] == "Consumer price indices (September 2026)" and names["2026-11-04"] == "CPI flash estimate (October 2026)",
      f"CZSO names carry the reference period: {names['2026-10-13']!r}, {names['2026-11-04']!r}")
check(all(e["time"] == "9:00am Prague time" for e in ev), "CZSO releases at 9:00am Prague time (summer and winter offsets)")
check(F.period_of("Consumer price indices -inflation - September 2026") == "September 2026", "period read despite CZSO's uneven dashes")
bad = copy.deepcopy(CZSO); bad["seznam"][2]["udalosti"][0]["zacatek"] = "2026-10-13T09:00:00+05:00"
_, p = F.parse_czso(bad)
check(any("Prague time" in x for x in p), "CZSO: a non-Prague offset is refused")
bad = copy.deepcopy(CZSO); bad["seznam"][2]["udalosti"][0]["kategorie"][0]["kod"] = "vyznamne-terminy"
_, p = F.parse_czso(bad)
check(any("news-release category" in x for x in p), "CZSO: an event outside the news-release category is refused")
_, p = F.parse_czso({"error": "Unauthorized"})
check(p and "not the events list" in p[0], "CZSO: an error reply is refused")
none_cpi = {"seznam": [d for d in CZSO["seznam"] if not any("price indices - inflation" in u["nazev"] or "Flash" in u["nazev"] for u in d["udalosti"])]}
_, p = F.parse_czso(none_cpi)
check(any("no consumer price release" in x for x in p), "CZSO: a reply with no CPI release is refused")
for live in sorted(FIX.glob("czso_udalosti_2*.json")):
    lev, lp = F.parse_czso(json.loads(live.read_text(encoding="utf-8")))
    check(not lp and any(e["concept"] == "cpi" for e in lev), f"live reply {live.name} parses: {lp}")


# --- main(): merge, carry-forward, refusal to write
class R:
    def __init__(self, body=b"", js=None, code=200):
        self.content, self._js, self.status_code = body, js, code
    def json(self): return self._js
    def raise_for_status(self):
        if self.status_code >= 400:
            raise F.requests.HTTPError(str(self.status_code))

def fake(cnb_ok=True, czso_ok=True):
    def get(url, **kw):
        if "cnb.cz" in url:
            return R(CNB.encode()) if cnb_ok else R(code=403)
        if "csu.gov.cz" in url:
            assert "datumOd=2026-10-08" in url and "kategorieKod=rychle-informace" in url, url
            return R(js=CZSO) if czso_ok else R(code=503)
        raise AssertionError(url)
    return get

def run(prev=None, **kw):
    tmp = tempfile.mkdtemp(); cwd = os.getcwd()
    try:
        os.chdir(tmp)
        if prev is not None: Path(F.OUT).write_text(json.dumps(prev))
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as err:
            rc = F.main(today=TODAY, get=fake(**kw))
        d = json.loads(Path(F.OUT).read_text()) if Path(F.OUT).exists() else None
        return rc, d, err.getvalue()
    finally:
        os.chdir(cwd)

rc, d, _ = run()
check(rc == 0 and d["country"] == "Czechia", "clean run writes data-calendar-cz.json")
dates = [(e["date"], e["concept"]) for e in d["events"]]
check(("2026-11-05", "rate_decision") in dates and ("2026-12-17", "rate_decision") in dates
      and not any(c == "rate_decision" and x < "2026-10-08" for x, c in dates), "only upcoming CNB meetings")
check(len(d["events"]) == 23, f"2 CNB + 21 CZSO events: {len(d['events'])}")
check(d["events"] == sorted(d["events"], key=lambda e: (e["date"], e["concept"], e["name"])), "events sorted")
rc2, d2, err2 = run(prev=d, czso_ok=False)
check(rc2 == 0 and len(d2["events"]) == 23 and "carrying forward previous CZSO" in err2, "CZSO down: previous CZSO events carried forward")
rc3, d3, err3 = run(prev=d, cnb_ok=False)
check(rc3 == 0 and sum(e["concept"] == "rate_decision" for e in d3["events"]) == 2, "CNB blocked: previous CNB events carried forward")
rc4, d4, _ = run(prev={"events": [{"date": "2026-12-01", "concept": "x", "name": "keep", "source": "s"}]}, cnb_ok=False, czso_ok=False)
check(rc4 == 1 and d4["events"][0]["name"] == "keep", "both down: exits 1, existing file untouched")
rc5, d5, _ = run(cnb_ok=False, czso_ok=False)
check(rc5 == 1 and d5 is None, "both down with no previous file: nothing written")

check(F.__doc__ and "CNB" in F.__doc__ and "CZSO" in F.__doc__ and "no token" in F.__doc__, "docstring names both sources")
check((hashlib.sha256(LIVE.read_bytes()).hexdigest() if LIVE.exists() else None) == H0, "live data-calendar-cz.json untouched")
print(f"{OK[0]} ok, {len(BAD)} failed")
sys.exit(1 if BAD else 0)
