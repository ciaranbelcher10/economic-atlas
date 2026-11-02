"""v1.9.59: calendar round cal10. RBA decision time, Turkey (CBRT), Canada (BoC), Singapore (MAS).

    python3 tools/test_fetch_calendar_cal10.py   -> "N ok, 0 failed"

Fixtures are the raw pages saved by probe cal10 on 2 Nov 2026 (byte-for-byte, not rebuilt).
Offline: requests is replaced, every run writes into a temp folder, and the live
data-calendar-*.json files are checked unchanged at the end.
"""
import hashlib, io, json, os, re, sys, tempfile
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import requests  # noqa: E402
import fetch_calendar_au as AU, fetch_calendar_tr as TR, fetch_calendar_ca as CA, fetch_calendar_sg as SG  # noqa: E402

F = ROOT / "tools" / "fixtures" / "calendar"
def rd(n):
    with open(F / n, encoding="utf-8", newline="") as f:  # keep CRLFs exactly as served
        return f.read()
RBA_LIVE, TCMB, BOC, BOC_EV, MAS = (rd("rba_int_rate_decisions_202611_live.html"), rd("tcmb_calendar_202611.html"),
                                     rd("boc_key_interest_rate_202611.html"), rd("boc_upcoming_events_202611.html"),
                                     rd("mas_advance_release_calendar_202611.html"))
LIVE = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in ROOT.glob("data-calendar-*.json")}
ok = bad = 0
def check(c, n):
    global ok, bad
    if c: ok += 1
    else: bad += 1; print("FAIL", n)
def no_dash(ev): return all("\u2014" not in json.dumps(e, ensure_ascii=False) for e in ev)

# ---------- RBA time: the live page breaks the sentence over lines ----------
check(len(RBA_LIVE) > 20000, "RBA fixture is the real 28 KB page, not a rebuilt snippet")
check("after each\r\n\tBoard meeting" in RBA_LIVE, "fixture keeps the line break that broke v1.9.56")
check(AU.rba_time(RBA_LIVE) == "2:30pm Sydney time", f"time read from the live page: {AU.rba_time(RBA_LIVE)!r}")
check(AU.rba_time(rd("rba_int_rate_decisions_202611.html")) == "2:30pm Sydney time", "old one-line form still read")
check(AU.rba_time(RBA_LIVE.replace("2.30 pm", "2:30pm")) == "2:30pm Sydney time", "colon and no space accepted")
check(AU.rba_time(RBA_LIVE.replace("after each", "after some")) == "", "a different sentence gives no time")

# ---------- Turkey ----------
ev, pr = TR.parse(TCMB)
d = [e["date"] for e in ev]
check(pr == [], f"tr parses cleanly: {pr}")
check(d[:8] == ["2026-01-22", "2026-03-12", "2026-04-22", "2026-06-11", "2026-07-23", "2026-09-10", "2026-10-22", "2026-12-10"],
      f"tr: the eight 2026 decisions, same as the old hand-typed list: {d[:8]}")
check(d[8:] == ["2027-01-21", "2027-03-18", "2027-04-22", "2027-06-10"], f"tr: 2027 rows published so far: {d[8:]}")
check(not {"2026-01-29", "2026-02-12", "2026-05-22", "2026-11-27"} & set(d), "tr: summaries and reports left out")
check(all(e["concept"] == "rate_decision" and e["country"] == "Turkey" and e["time"] == "2:00pm TRT" and e["source"] == TR.SRC
          for e in ev) and no_dash(ev), "tr: event fields")
check(any("bot wall" in p for p in TR.parse("<html>Request Rejected</html>")[1]), "tr: wall page caught")
check(any("not 'Monetary Policy Committee Decision'" in p
          for p in TR.parse(TCMB.replace("<h3>Monetary Policy Committee Decision</h3>", "<h3>Inflation Report</h3>", 1))[1]),
      "tr: a reordered table is caught")
check(any("not read" in p for p in TR.parse(TCMB.replace(">December 10, 2026<", ">10 Dec 2026<"))[1]), "tr: an unreadable date is caught")
check(any("impossible" in p for p in TR.parse(TCMB.replace(">December 10, 2026<", ">February 30, 2026<"))[1]), "tr: impossible date caught")
check(any("order" in p for p in TR.parse(TCMB.replace(">October 22, 2026<", ">December 22, 2026<", 1))[1]), "tr: out-of-order dates caught")
blank = re.sub(r'(<td style="text-align: center;">)(\w+ \d{1,2}, 20\d\d)(</td>\s*<td[^>]*>\w+ \d{1,2}, 20\d\d</td>)', r"\1&nbsp;\3", TCMB)
check(any("no decision dates" in p for p in TR.parse(blank)[1]), "tr: a table with no decisions is caught")
nb = TCMB.replace('<td style="text-align: center;">March 12, 2026</td>', '<td style="text-align: center;">&nbsp;</td>', 1)
check(TR.parse(nb)[1] == [] and "2026-03-12" not in [e["date"] for e in TR.parse(nb)[0]], "tr: a blank decision cell is skipped")

# ---------- Canada ----------
lab = CA.boc_time(BOC_EV)
check(lab == "9:45am ET", f"ca: time from the upcoming-events page: {lab!r}")
check(CA.boc_time("<p>Nothing here</p>") == "", "ca: no time line, no time")
check(CA.boc_time(BOC_EV.replace("09:45 (ET)", "13:30 (ET)")) == "1:30pm ET", "ca: afternoon times converted")
ev, pr = CA.parse(BOC, lab)
d = [e["date"] for e in ev]
check(pr == [], f"ca parses cleanly: {pr}")
check(d[:8] == ["2026-01-28", "2026-03-18", "2026-04-29", "2026-06-10", "2026-07-15", "2026-09-02", "2026-10-28", "2026-12-09"],
      f"ca: 2026 matches the old hand-typed list: {d[:8]}")
check(d[8:] == ["2027-01-27", "2027-03-03", "2027-04-28", "2027-06-02", "2027-07-21", "2027-09-08", "2027-10-27", "2027-12-08"],
      f"ca: 2027 now published and read: {d[8:]}")
check(all(e["concept"] == "rate_decision" and e["country"] == "Canada" and e["time"] == "9:45am ET" for e in ev) and no_dash(ev),
      "ca: event fields")
check(all("time" not in e for e in CA.parse(BOC, "")[0]), "ca: without the time page, dates only")
check(any("bot wall" in p for p in CA.parse("<html>Access denied</html>")[1]), "ca: wall page caught")
check(any("not read" in p for p in CA.parse(BOC.replace("<td>December\xa09</td>", "<td>TBC</td>"))[1]), "ca: unreadable date caught")
check(any("announcements; the Bank holds 8" in p
          for p in CA.parse(BOC.replace("Interest rate announcement", "Speech", 4))[1]), "ca: a year with too few dates caught")
check(any("impossible" in p for p in CA.parse(BOC.replace("<td>December\xa09</td>", "<td>February 30</td>"))[1]), "ca: impossible date caught")

# ---------- Singapore ----------
ev, pr = SG.parse(MAS)
check(pr == [] and [e["date"] for e in ev] == ["2027-01-29"], f"sg: the next statement, 29 Jan 2027: {pr} {ev}")
check(ev and ev[0]["name"] == SG.NAME_NLT and ev[0]["time"] is None and ev[0]["country"] == "Singapore"
      and ev[0]["concept"] == "rate_decision" and no_dash(ev), "sg: 'no later than' named, no invented time")
check(SG.parse(MAS.replace("NLT 29 Jan 2027", "29 Jan 2027"))[0][0]["name"] == SG.NAME, "sg: an exact date is named plainly")
check(any("bot wall" in p for p in SG.parse("<html>Blocked</html>")[1]), "sg: wall page caught")
check(any("not followed by" in p for p in SG.parse(MAS.replace("Statement for Jan 2027", "Issue for Jan 2027"))[1]),
      "sg: a date not tied to a statement is caught")
check(any("no date under" in p for p in SG.parse(MAS.replace("NLT 29 Jan 2027", "To be announced"))[1]), "sg: no date caught")
check(any("impossible" in p for p in SG.parse(MAS.replace("NLT 29 Jan 2027", "NLT 30 Feb 2027"))[1]), "sg: impossible date caught")

# ---------- main(): writes on success, keeps the file and warns on failure, never fails ----------
class R:
    def __init__(s, text, code=200): s.content, s.status_code = text.encode(), code
    def raise_for_status(s):
        if s.status_code != 200: raise requests.HTTPError(str(s.status_code))
class Sess:
    def __init__(s, m): s.m, s.headers = m, {}
    def get(s, url, timeout=None, headers=None):
        v = s.m[url]
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

OLD = '{"events": [{"date": "2026-12-10", "name": "kept"}]}'
for mod, tag, ok_pages, bad_pages in [
    (TR, "CBRT", {TR.URL: R(TCMB)}, {TR.URL: R("", 403)}),
    (CA, "BoC", {CA.URL: R(BOC), CA.TIME_URL: R(BOC_EV)}, {CA.URL: R("<html>Access denied</html>"), CA.TIME_URL: R(BOC_EV)}),
    (SG, "MAS", {SG.URL: R(MAS)}, {SG.URL: requests.ConnectionError("down")}),
]:
    rc, body, out, err = run(mod, ok_pages, OLD)
    data = json.loads(body)
    check(rc == 0 and data["events"] and all(e["date"] >= "2026-11-02" for e in data["events"]) and f"{tag}:" in out,
          f"{tag}: a good page writes upcoming dates: {out} {err}")
    rc, body, out, err = run(mod, bad_pages, OLD)
    check(rc == 0 and body == OLD and err.startswith(f"WARNING {tag}:") and "kept" in err,
          f"{tag}: a failed read keeps the file, warns, exits 0: {err}")
    rc, body, out, err = run(mod, bad_pages, None)
    check(rc == 0 and body is None and f"WARNING {tag}:" in err, f"{tag}: a failed first run writes nothing")

past = TCMB
for m in re.findall(r">(\w+ \d{1,2}, 2027)<", TCMB):
    past = past.replace(f">{m}<", ">" + m.replace("2027", "2025") + "<")
rc, body, out, err = run(TR, {TR.URL: R(past.replace(", 2026<", ", 2024<"))}, OLD)
check(body == OLD and "WARNING CBRT" in err, "tr: a table with only past dates keeps the file")
rc, body, out, err = run(CA, {CA.URL: R(BOC), CA.TIME_URL: requests.ConnectionError("x")}, OLD)
check(body != OLD and "time" not in json.loads(body)["events"][0] and "dates only" in out, "ca: time page down, dates still written")

# ---------- wiring ----------
html = (ROOT / "calendar.html").read_text(encoding="utf-8")
yml = (ROOT / ".github" / "workflows" / "update-calendar.yml").read_text()
files = re.search(r"var CALENDAR_DATA_FILES = \[([\s\S]*?)\];", html).group(1)
check('"data-calendar-sg.json"' in files, "sg file is loaded by the calendar page")
check('"Singapore"' in re.search(r"var COUNTRIES_WITH_DATA = \[([\s\S]*?)\]", html).group(1), "Singapore is in the picker")
check("python fetch_calendar_sg.py" in yml and yml.index("fetch_calendar_za.py") < yml.index("fetch_calendar_sg.py") < yml.index("calendar_history.py"),
      "sg step runs before past events are restored")
check("not yet confirmed against tcmb.gov.tr" not in yml, "stale Turkey log note gone")
for n in ["fetch_calendar_tr.py", "fetch_calendar_ca.py"]:
    src = (ROOT / n).read_text()
    check("hardcoded" not in src.lower() and "date(2026," not in src, f"{n}: no hand-typed dates left")
for n, h in LIVE.items():
    check(hashlib.sha256((ROOT / n).read_bytes()).hexdigest() == h, f"{n} untouched")
# v1.9.60: no "file must not exist" check here; once the workflow runs, the bot commits that file.
# The hash loop above already proves the test never writes a live data-calendar-*.json.
print(f"{ok} ok, {bad} failed")
sys.exit(1 if bad else 0)
