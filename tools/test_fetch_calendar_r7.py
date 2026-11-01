"""Tests for v1.9.48: Denmark (DST) reads 3 months of News through the page's form.

    python3 tools/test_fetch_calendar_r7.py   -> "N ok, 0 failed"

Fixture tools/fixtures/calendar/dst_planlagte_news_3m_202611.html holds the 81 News rows
the live form returned for "3 months, News only" on 1 Nov 2026 (probe dk3), in the live
markup (non-breaking hyphens, seven cells). Offline; no data-calendar-*.json file is touched.
"""
import hashlib, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import calendar_common as C
import fetch_calendar_dk as DK

F = ROOT / "tools" / "fixtures" / "calendar"
PAGE = (F / "dst_planlagte_news_3m_202611.html").read_text()
LIVE = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in ROOT.glob("data-calendar-*.json")}
ok = bad = 0
def check(cond, name):
    global ok, bad
    if cond: ok += 1
    else: bad += 1; print("FAIL", name)

ev, pr = DK.parse(PAGE)
got = [(e["date"], e["concept"]) for e in ev]
want = [("2026-11-09", "trade"), ("2026-11-10", "cpi"), ("2026-11-20", "gdp"), ("2026-11-25", "jobs"),
        ("2026-11-30", "jobs"), ("2026-12-09", "trade"), ("2026-12-10", "cpi"), ("2026-12-22", "gdp"),
        ("2027-01-07", "jobs"), ("2027-01-11", "cpi"), ("2027-01-11", "trade"), ("2027-01-29", "jobs")]
check(pr == [], f"parses cleanly {pr}")
check(sorted(got) == sorted(want), f"the twelve headline releases in 3 months, nothing else: {sorted(got)}")
names = {e["name"] for e in ev}
check("Consumer price index and net retail price index (Oktober 2026)" in names, f"title and period kept as published {sorted(names)[:3]}")
check(not any("by sector" in n or "organic" in n or "enterprise" in n or "immigrants" in n for n in names),
      "National accounts by sector, organic trade, trade by enterprise and immigrant labour left out")
check(all(e["time"] == "8:00am Danish time" and e["country"] == "Denmark" for e in ev), "time, country")
check(all("\u2014" not in e["name"] and "--" not in e["name"] for e in ev), "no em dashes")

# the form
GET = ('<form method="post" action="/en/Statistik/planlagte" id="ctl00">'
       '<input type="hidden" name="__VIEWSTATE" id="__VIEWSTATE" value="abc&#43;1" />'
       '<input type="hidden" name="__EVENTVALIDATION" id="__EVENTVALIDATION" value="xyz" /></form>')
f = DK.form_fields(GET)
check(f["__VIEWSTATE"] == "abc+1" and f["__EVENTVALIDATION"] == "xyz", f"hidden fields copied and unescaped {f}")
check(f[DK.FIELD + "Periode"] == "c" and f[DK.FIELD + "Produkt"] == "1" and f[DK.FIELD + "UpdateBtn"] == "Select",
      "3 months, News only, Select pressed")
try:
    DK.form_fields("<html>Pardon Our Interruption</html>"); check(False, "no form is a loud failure")
except ValueError as e:
    check("form was not found" in str(e), "no form is a loud failure")

check(DK.check_filtered(PAGE) == [], "filtered page passes the filter check")
unfiltered = PAGE.replace('<td class="SchLeft SchNowrap">News</td>', '<td class="SchLeft SchNowrap">Table</td>', 1)
check(any("filter was not applied" in p for p in DK.check_filtered(unfiltered)), "a Table row means the filter did not apply")
check(any("Showing" in p for p in DK.check_filtered(PAGE.replace("Showing 1 to 82 of 82", ""))), "no Showing line fails")
check(DK.check_filtered(PAGE.replace("Showing 1 to 82 of 82", "Showing 1 to 100 of 120")) == [], "a cut-off page is a note, not a failure")

class R:
    def __init__(self, text, code=200): self.text, self.status_code = text, code
    def raise_for_status(self):
        if self.status_code != 200: raise C.requests.HTTPError(str(self.status_code))
class Sess:
    def __init__(self, get, post): self.g, self.p, self.posted = get, post, None
    def get(self, url, timeout=None): return self.g
    def post(self, url, data=None, timeout=None): self.posted = data; return self.p
s = Sess(R(GET), R(PAGE))
evs = DK.fetch_events(s, "2026-11-01")
check(len(evs) == 12 and s.posted and s.posted["__VIEWSTATE"] == "abc+1", "fetch_events posts the form and returns the twelve")
for label, sess in [("post 503", Sess(R(GET), R("", 503))),
                    ("filter ignored", Sess(R(GET), R(unfiltered))),
                    ("wall instead of form", Sess(R("<html>Pardon Our Interruption</html>"), R(PAGE)))]:
    out = Path("/tmp/never-written-dk.json")
    out.unlink(missing_ok=True)  # a leftover from an earlier run must not decide this check
    check(C.run_single(str(out), "Denmark", lambda _s, t: DK.fetch_events(sess, t), "Denmark") == 1 and not out.exists(),
          f"{label}: nothing written, old file kept")
check(all(hashlib.sha256(p.read_bytes()).hexdigest() == h for p, h in LIVE.items()), "live calendar files untouched")
print(f"{ok} ok, {bad} failed")
sys.exit(1 if bad else 0)
