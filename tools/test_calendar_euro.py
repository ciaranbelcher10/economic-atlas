"""Euro members see the ECB's rate decisions on their calendar (v1.7.29).

    python3 tools/test_calendar_euro.py   -> "N ok, 0 failed"

Checks, against the real files:
  1. calendar.html ECB_MEMBERS equals fx_config.EURO_MEMBERS (one source of truth).
  2. Every member is in the picker (COUNTRIES_WITH_DATA) and the Europe region.
  3. The page's calCountryMatch (run in node): a member's calendar shows Eurozone
     rate decisions and nothing else of the Eurozone's.
  4. send_calendar_alerts.matching_upcoming_events applies the same rule.
Planted faults check that 3 and 4 would catch a broken rule.
"""
import json, re, subprocess, sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import fx_config
import send_calendar_alerts as A

ok = bad = 0
def check(cond, name):
    global ok, bad
    if cond: ok += 1
    else: bad += 1; print("FAIL", name)

html = (ROOT / "calendar.html").read_text()
m = re.search(r"var ECB_MEMBERS = (\[[^\]]*\]);", html)
check(m is not None, "calendar.html defines ECB_MEMBERS")
members = json.loads(m.group(1)) if m else []
check(set(members) == set(fx_config.EURO_MEMBERS), f"ECB_MEMBERS equals fx_config.EURO_MEMBERS: {sorted(set(members) ^ set(fx_config.EURO_MEMBERS))}")
check(len(members) == len(set(members)), "ECB_MEMBERS has no duplicates")
check(".concat(ECB_MEMBERS)" in html, "members are in the picker (COUNTRIES_WITH_DATA)")
europe = json.loads(re.search(r'\{name: "Europe", countries: (\[[^\]]*\])\}', html).group(1))
check(not set(members) - set(europe), f"members in the Europe region: missing {sorted(set(members) - set(europe))}")

fn = re.search(r"function calCountryMatch\(e\)\{.*?\n\}", html, re.S).group(0)
EVENTS = [
    {"country": "Eurozone", "concept": "rate_decision"},
    {"country": "Eurozone", "concept": "cpi"},
    {"country": "US", "concept": "rate_decision"},
]
CASES = [  # tracked, expected visibility of each event above
    (["Greece"], [True, False, False]),
    (["Eurozone"], [True, True, False]),
    (["Poland"], [False, False, False]),
    (["US", "Finland"], [True, False, True]),
]

def run_js(body):
    js = (f"var ECB_MEMBERS={json.dumps(members)};var trackedCountries;{body}\n"
          f"var out=[];{json.dumps(CASES)}.forEach(function(c){{trackedCountries=c[0];"
          f"out.push({json.dumps(EVENTS)}.map(calCountryMatch));}});console.log(JSON.stringify(out));")
    r = subprocess.run(["node", "-e", js], capture_output=True, text=True)
    return json.loads(r.stdout) if r.returncode == 0 else None

got = run_js(fn)
check(got == [c[1] for c in CASES], f"page rule: {got}")
broken = fn.replace('e.concept === "rate_decision"', "true")
check(run_js(broken) != [c[1] for c in CASES], "planted fault caught: page shows all Eurozone events to members")

def alerts(tracked):
    evs = [dict(e, date="2026-10-29", name="x") for e in EVENTS]
    prefs = {"calendar_tracked_countries": tracked, "calendar_tracked_metrics": ["rate_decision", "cpi"]}
    got = A.matching_upcoming_events(evs, prefs, date(2026, 10, 1), date(2026, 11, 1))
    return [e in [{k: v for k, v in g.items() if k in ("country", "concept")} for g in got] for e in EVENTS]

check([alerts(c[0]) for c in CASES] == [c[1] for c in CASES], f"alerts rule: {[alerts(c[0]) for c in CASES]}")
saved = A.EURO_MEMBERS
A.EURO_MEMBERS = set()
check([alerts(c[0]) for c in CASES] != [c[1] for c in CASES], "planted fault caught: alerts ignore euro members")
A.EURO_MEMBERS = saved

print(f"{ok} ok, {bad} failed")
sys.exit(1 if bad else 0)
