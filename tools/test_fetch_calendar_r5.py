"""Tests for the v1.9.44 calendar fetchers: Switzerland (SNB), Thailand (BOT),
Indonesia (BI, rewritten) and Colombia (DANE).

    python3 tools/test_fetch_calendar_r5.py   -> "N ok, 0 failed"

Fixtures in tools/fixtures/calendar/, laid out as the live pages were on 1 Nov 2026
(probe rounds 6 and 7): snb_schedule_202611.html (the SNB list markup and titles),
bot_mpc_202611.html (the 2026 and 2027 schedule tables, the 2027 one also embedded
escaped in a data-layer attribute as on the live page), bi_kalender_2026.html (the
board meeting table with a non-breaking space between the day range and the month, the
markup that broke the old script) and dane_202612.html (a December month view whose grid
also shows 30 Nov and 2 Jan; the IPC, IPP, Importaciones, Balanza comercial and Mercado
laboral titles and their days are illustrative, as the probe only showed the links of the
first days). Offline; no data-calendar-*.json file is touched.
"""
import hashlib, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import calendar_common as C
import fetch_calendar_ch as CH, fetch_calendar_th as TH, fetch_calendar_id as ID, fetch_calendar_co as CO

F = ROOT / "tools" / "fixtures" / "calendar"
LIVE = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in ROOT.glob("data-calendar-*.json")}
ok = bad = 0
def check(cond, name):
    global ok, bad
    if cond: ok += 1
    else: bad += 1; print("FAIL", name)
def clean(evs):
    return all("\u2014" not in e["name"] and "--" not in e["name"] for e in evs)

# Switzerland
ev, pr = CH.parse((F / "snb_schedule_202611.html").read_text())
check(pr == [], f"ch: parses cleanly {pr}")
check([(e["date"], e["concept"]) for e in ev] == [("2026-12-10", "rate_decision"), ("2027-03-18", "rate_decision")],
      f"ch: exactly the two decisions, not the news conferences or other items: {[(e['date'], e['concept']) for e in ev]}")
check(all(e["time"] == "9:30am Swiss time" and e["country"] == "Switzerland" and e["source"].startswith("snb.ch") for e in ev), "ch: time, country, source")
check(clean(ev), "ch: no em dashes")
check(CH.time_label(14, 30) == "2:30pm Swiss time" and CH.time_label(12, 0) == "12:00pm Swiss time", "ch: time labels")
ev2, pr2 = CH.parse("<html><body>Access denied</body></html>")
check(ev2 == [] and pr2 and "no dated schedule items" in pr2[0], f"ch: empty page is a loud failure {pr2}")
few = (F / "snb_schedule_202611.html").read_text().split("</ul>")[0]
few = few[:few.index('<li class="col-12', few.index("Monetary policy assessment of 10 December 2026 (press release)"))] + "</ul>"
check(any("only 3 schedule items" in p for p in CH.parse(few)[1]), "ch: a page with only a few items fails")
nodec = (F / "snb_schedule_202611.html").read_text().replace("(press release)</h3>", "(statement)</h3>")
check(any("Monetary policy assessment" in p for p in CH.parse(nodec)[1]), "ch: a page with no decision item fails")

# Thailand
ev, pr = TH.parse((F / "bot_mpc_202611.html").read_text())
got = sorted({e["date"] for e in ev})
want = ["2026-02-25", "2026-04-29", "2026-06-24", "2026-08-26", "2026-10-28", "2026-12-23",
        "2027-03-03", "2027-04-28", "2027-06-23", "2027-08-25", "2027-10-27", "2027-12-22"]
check(pr == [], f"th: parses cleanly {pr}")
check(got == want, f"th: the 12 meeting dates only, never the minutes or report dates: {got}")
check(all(e["concept"] == "rate_decision" and e["time"] is None and e["country"] == "Thailand" for e in ev), "th: concept, no invented time, country")
check(clean(ev), "th: no em dashes")
check("no schedule rows" in TH.parse("<p>Just a moment</p>")[1][0], "th: empty page is a loud failure")
short = "<table>" + "".join(f"<tr><td></td><td>Wed. {d} Mar. 2027</td></tr>" for d in (3, 10, 17)) + "</table>"
check(any("only 3 schedule rows" in p for p in TH.parse(short)[1]), "th: a page with only a few rows fails")

# Indonesia
page = (F / "bi_kalender_2026.html").read_text()
check("&nbsp;" in page, "id: fixture carries the non-breaking space")
ev, pr = ID.parse(page)
check(pr == [], f"id: parses cleanly {pr}")
check(len(ev) == 12 and ev[10]["date"] == "2026-11-18" and ev[11]["date"] == "2026-12-16",
      f"id: 12 meetings, decision on the second day: {[e['date'] for e in ev][-2:]}")
check(not any("12-31" in e["date"] for e in ev), "id: the embedded release-calendar data is not read as a meeting")
check("no 'Tuesday-Wednesday" in ID.parse("<html></html>")[1][0], "id: empty page is a loud failure")
check(any("only 2 meeting rows" in p for p in ID.parse("<td>Tuesday-Wednesday, 17-18 November 2026</td><td>Tuesday-Wednesday, 15-16 December 2026</td>")[1]),
      "id: a page with only a few meetings fails")

# Colombia
ev, pr = CO.parse_month((F / "dane_202612.html").read_text(), 2026, 12)
got = sorted((e["date"], e["concept"], e["name"]) for e in ev)
want = [("2026-12-03", "trade", "Exports"), ("2026-12-05", "cpi", "Consumer price index (IPC)"),
        ("2026-12-05", "ppi", "Producer price index (IPP)"), ("2026-12-15", "trade", "Imports"),
        ("2026-12-15", "trade", "Trade balance"), ("2026-12-30", "jobs", "Labour market (GEIH)")]
check(pr == [], f"co: parses cleanly {pr}")
check(got == want, f"co: served releases only (no SIPSA bulletins, annexes or ESAG): {got}")
check(not any(e["date"].startswith(("2026-11", "2027-01")) for e in ev), "co: neighbouring months' days are left to their own views")
check(all(e["time"] is None and e["country"] == "Colombia" and e["source"].startswith("dane.gov.co") for e in ev), "co: no invented time, country, source")
check(clean(ev), "co: no em dashes")
check(any("only 2 release links" in p for p in CO.parse_month(
    '<a href="/index.php/calendario/icalrepeat.detail/2026/12/03/1/-/x">Exportaciones</a>'
    '<a href="/index.php/calendario/icalrepeat.detail/2026/12/05/2/-/y">Mercado laboral</a>', 2026, 12)[1]), "co: a month with only a few links fails")
check(CO.fold("Índice de Precios") == "indice de precios", "co: accent folding")
check(list(CO.months_from("2026-11-01")) == [(2026, 11), (2026, 12), (2027, 1)], "co: three months across a year end")
check("no release links" in CO.parse_month("<html></html>", 2026, 12)[1][0], "co: empty page is a loud failure")

class Resp:
    def __init__(self, text, code=200): self.text, self.status_code = text, code
    def raise_for_status(self):
        if self.status_code >= 400: raise C.requests.HTTPError(str(self.status_code))
class Sess:
    def __init__(self, pages): self.pages, self.urls = pages, []
    def get(self, url, timeout=None):
        self.urls.append(url)
        return self.pages.get(url, Resp("", 503))
dec = (F / "dane_202612.html").read_text()
nov = dec.replace("/2026/12/", "/2026/11/")
s = Sess({CO.BASE.format(y=2026, m=11): Resp(nov), CO.BASE.format(y=2026, m=12): Resp(dec)})
ev = CO.fetch_events(s, "2026-11-01")
check(len(s.urls) == 3 and {e["date"][:7] for e in ev} == {"2026-11", "2026-12"}, "co: a failing third month is skipped, the first two kept")
try:
    CO.fetch_events(Sess({}), "2026-11-01"); check(False, "co: first month failing must raise")
except ValueError as e:
    check(str(e).startswith("2026-11:"), f"co: first month failing raises at once: {e}")
noc = dec.replace("(IPC)", "").replace("Exportaciones", "Otra").replace("Índice de Precios al Consumidor", "Otro").replace("Importaciones", "x").replace("Balanza comercial", "y")
try:
    CO.fetch_events(Sess({CO.BASE.format(y=2026, m=11): Resp(noc.replace("/2026/12/", "/2026/11/"))}), "2026-11-01")
    check(False, "co: no CPI or trade must raise")
except ValueError as e:
    check("no CPI or trade" in str(e), "co: no CPI or trade raises")

# keep-the-old-file rule holds for every new script
for mod, name in [(CH, "ch"), (TH, "th"), (ID, "id")]:
    check(C.run_single("/tmp/never-written.json", "X", lambda s, t: mod.fetch_events(Sess({}), t), name) == 1
          and not Path("/tmp/never-written.json").exists(), f"{name}: a failed fetch writes nothing")

check(all(hashlib.sha256(p.read_bytes()).hexdigest() == h for p, h in LIVE.items()), "live calendar files untouched")
print(f"{ok} ok, {bad} failed")
sys.exit(1 if bad else 0)
