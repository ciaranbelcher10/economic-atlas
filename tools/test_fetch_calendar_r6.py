"""Tests for the v1.9.45 calendar fetchers: South Korea (BOK), Denmark (DST) and
South Africa (SARB).

    python3 tools/test_fetch_calendar_r6.py   -> "N ok, 0 failed"

Fixtures in tools/fixtures/calendar/, laid out as the live pages were on 1 Nov 2026
(probe round 8): bok_cldr_2026.html (the BOK table rows, tabs, <p> titles and one linked
title as served; the GDP and producer price titles are illustrative, as the probe showed
the November rows around them), dst_planlagte_202611.html (the DST rows with their
non-breaking hyphens, News and Table rows, including a Table row whose title would match) and sarb_home_202611.html (the Upcoming Events
panel, which the live page shows twice). Offline; no data-calendar-*.json file is touched.
"""
import hashlib, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import calendar_common as C
import fetch_calendar_kr as KR, fetch_calendar_dk as DK, fetch_calendar_za as ZA

F = ROOT / "tools" / "fixtures" / "calendar"
LIVE = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in ROOT.glob("data-calendar-*.json")}
ok = bad = 0
def check(cond, name):
    global ok, bad
    if cond: ok += 1
    else: bad += 1; print("FAIL", name)
def clean(evs):
    return all("\u2014" not in e["name"] and "--" not in e["name"] for e in evs)

# South Korea
ev, pr = KR.parse((F / "bok_cldr_2026.html").read_text())
got = [(e["date"], e["concept"], e["time"]) for e in ev]
check(pr == [], f"kr: parses cleanly {pr}")
check(got == [("2026-10-23", "gdp", "8:00am Korea time"), ("2026-11-20", "ppi", "6:00am Korea time"),
              ("2026-12-03", "gdp", "8:00am Korea time")],
      f"kr: GDP and producer prices only, never trade price indexes or BoP: {got}")
check(ev[1]["name"] == "Producer Price Indices in October 2026", f"kr: title kept as published {ev[1]['name']!r}")
check(all(e["country"] == "South Korea" and e["source"].startswith("bok.or.kr") for e in ev) and clean(ev), "kr: country, source, no em dashes")
check(KR.time_label(12, 0) == "12:00pm Korea time" and KR.time_label(14, 30) == "2:30pm Korea time", "kr: time labels")
check("no 'date | time | title' rows" in KR.parse("<html>blocked</html>")[1][0], "kr: empty page is a loud failure")
few = "".join(f"<tr><td>2026-11-{d:02d}</td><td>8:00</td><td class='title'>Producer Price Indices</td></tr>" for d in range(1, 4))
check(any("only 3 rows" in p for p in KR.parse(few)[1]), "kr: a page with only a few rows fails")
nogdp = (F / "bok_cldr_2026.html").read_text().replace("Gross Domestic Product", "Gross Output").replace("Producer Price Indices", "Prices")
check(any("no GDP or producer price" in p for p in KR.parse(nogdp)[1]), "kr: no GDP or PPI row fails")

# Denmark
ev, pr = DK.parse((F / "dst_planlagte_202611.html").read_text())
got = [(e["date"], e["concept"]) for e in ev]
check(pr == [], f"dk: parses cleanly {pr}")
check(got == [("2026-11-10", "cpi"), ("2026-11-10", "cpi"), ("2026-11-12", "ppi"), ("2026-11-13", "trade"),
              ("2026-11-27", "jobs"), ("2026-11-30", "gdp"), ("2026-11-30", "jobs")],
      f"dk: News rows only, served concepts only: {got}")
check(ev[0]["name"] == "Consumer price index (October 2026)", f"dk: name carries the period {ev[0]['name']!r}")
check(ev[0]["time"] == "8:00am Danish time" and ev[-1]["time"] is None, "dk: morning time kept, an afternoon time left out rather than mislabelled")
check(all(e["country"] == "Denmark" and e["source"].startswith("dst.dk") for e in ev) and clean(ev), "dk: country, source, no em dashes")
check("no dated release rows" in DK.parse("<html></html>")[1][0], "dk: empty page is a loud failure")
fewdk = "<table>" + "".join(f"<tr><td>0{d}&#8209;11&#8209;2026</td><td>08:00</td><td>News</td><td>Consumer price index</td><td>x</td><td>y</td></tr>" for d in range(1, 4)) + "</table>"
check(any("only 3 release rows" in p for p in DK.parse(fewdk)[1]), "dk: a page with only a few rows fails")
nocore = (F / "dst_planlagte_202611.html").read_text()
for t in ["Consumer price index", "Harmonised index of consumer prices", "International trade in goods", "GDP, quarterly national accounts"]:
    nocore = nocore.replace(f'<td class="SchLeft">{t}</td>', '<td class="SchLeft">Other</td>')
pr_nc = DK.parse(nocore)[1]
check(any("no CPI, trade or GDP" in p for p in pr_nc), "dk: a page with no CPI, trade or GDP row fails")
check(any("News titles seen: 05-11-2026 Bankruptcies;" in p and "Registered unemployment" in p for p in pr_nc), f"dk: the failure names the News titles it saw {pr_nc}")

# South Africa
ev, pr = ZA.parse((F / "sarb_home_202611.html").read_text())
check(pr == [] and [e["date"] for e in ev] == ["2026-11-19", "2026-11-19"], f"za: the next MPC date read from the panel {pr} {[e['date'] for e in ev]}")
check(all(e["concept"] == "rate_decision" and e["time"] is None and e["country"] == "South Africa" for e in ev) and clean(ev), "za: concept, no invented time, country")
check(any("no 'Upcoming Events' panel" in p for p in ZA.parse("<html>Request Rejected</html>")[1]), "za: blocked page is a loud failure")
check(ZA.parse("<div>Upcoming Events</div><p>Nothing scheduled</p>") == ([], []), "za: a panel with no MPC date gives no events (run_single then keeps the old file)")

class Sess:
    def __init__(self, text=None): self.text = text
    def get(self, url, timeout=None):
        class R: pass
        r = R(); r.text = self.text or ""; r.status_code = 200 if self.text else 503
        r.raise_for_status = (lambda: None) if self.text else (lambda: (_ for _ in ()).throw(C.requests.HTTPError("503")))
        return r
for mod, name in [(KR, "kr"), (DK, "dk"), (ZA, "za")]:
    check(C.run_single("/tmp/never-written.json", "X", lambda s, t: mod.fetch_events(Sess(), t), name) == 1
          and not Path("/tmp/never-written.json").exists(), f"{name}: a failed fetch writes nothing")
check(C.run_single("/tmp/never-written.json", "X", lambda s, t: ZA.fetch_events(Sess("<div>Upcoming Events</div>"), t), "za") == 1
      and not Path("/tmp/never-written.json").exists(), "za: no upcoming date writes nothing")
check(all(hashlib.sha256(p.read_bytes()).hexdigest() == h for p, h in LIVE.items()), "live calendar files untouched")
print(f"{ok} ok, {bad} failed")
sys.exit(1 if bad else 0)
