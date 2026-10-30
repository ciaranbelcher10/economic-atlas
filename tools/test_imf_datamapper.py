"""Behavioural tests for imf_datamapper.py.   python3 tools/test_imf_datamapper.py"""
import os, sys
from datetime import date
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import imf_datamapper as dm

n = fails = 0
def check(name, got, want):
    global n, fails
    n += 1
    if got != want:
        fails += 1
        print(f"FAIL {name}: got {got!r}, want {want!r}")

OCT = date(2026, 10, 30)
MAR = date(2026, 3, 1)
check("cutoff from May is last year", dm.last_actual_year(OCT), 2025)
check("cutoff before May is two years back", dm.last_actual_year(MAR), 2024)
check("cutoff in May", dm.last_actual_year(date(2026, 5, 1)), 2025)
check("cutoff in April", dm.last_actual_year(date(2026, 4, 30)), 2024)

pay = {"values": {"GGXCNL_NGDP": {"CHL": {"2023": -2.4, "2024": -2.9, "2025": -2.1, "2026": -1.6, "2030": -0.5, "x": 1, "2022": None}}}}
check("parse drops projections and junk", dm.parse(pay, "GGXCNL_NGDP", "CHL", OCT), [["2023", -2.4], ["2024", -2.9], ["2025", -2.1]])
check("parse before May stops at 2024", dm.parse(pay, "GGXCNL_NGDP", "CHL", MAR), [["2023", -2.4], ["2024", -2.9]])
check("parse wrong country is empty", dm.parse(pay, "GGXCNL_NGDP", "COL", OCT), [])
check("parse empty payload", dm.parse({}, "GGXCNL_NGDP", "CHL", OCT), [])
check("parse rounds", dm.parse({"values": {"I": {"C": {"2020": 1.23456}}}}, "I", "C", OCT), [["2020", 1.235]])

check("gap over shared years", dm.max_gap([["2023", 1.0], ["2024", 2.0]], [["2023", 1.5], ["2024", 2.1], ["2025", 9]]), (0.5, 2))
check("gap with nothing shared", dm.max_gap([["2023", 1.0]], [["2020", 1.0]]), (None, 0))

FRED = [["2022", 1.36], ["2023", -2.273], ["2024", -2.739]]
def make(pts):
    return lambda ind, iso, today=None: pts

s = {"deficit": {"label": "old", "unit": "%", "freq": "years", "points": list(FRED)}}
note = dm.overlay(s, "deficit", "GGXCNL_NGDP", "CHL", "NEW", fetcher=make([["2022", 1.4], ["2023", -2.3], ["2024", -2.8], ["2025", -2.1]]))
check("agreeing series applied", s["deficit"]["points"][-1], ["2025", -2.1])
check("label replaced", s["deficit"]["label"], "NEW")
check("note says applied", note.startswith("deficit: IMF DataMapper applied, 2022 to 2025"), True)

s = {"deficit": {"label": "old", "points": list(FRED)}}
note = dm.overlay(s, "deficit", "I", "C", "NEW", fetcher=make([["2023", 0.0], ["2024", -2.7], ["2025", -2.0]]))
check("disagreeing series rejected", s["deficit"]["label"], "old")
check("disagreement note", "FRED copy kept" in note and "2.27 points" in note, True)

s = {"deficit": {"label": "old", "points": list(FRED)}}
note = dm.overlay(s, "deficit", "I", "C", "NEW", fetcher=make(None))
check("unavailable keeps FRED", (s["deficit"]["label"], note), ("old", "deficit: DataMapper unavailable, FRED copy kept"))

s = {"deficit": {"label": "old", "points": list(FRED)}}
dm.overlay(s, "deficit", "I", "C", "NEW", fetcher=make([["2019", 1.0]]))
check("no shared years keeps FRED", s["deficit"]["label"], "old")

s = {"deficit": {"label": "old", "points": list(FRED)}}
dm.overlay(s, "deficit", "I", "C", "NEW", fetcher=make([["2022", 1.36], ["2023", -2.273]]))
check("shorter DataMapper keeps FRED", s["deficit"]["label"], "old")

s = {}
dm.overlay(s, "deficit", "I", "C", "NEW", fetcher=make([["2024", -2.7], ["2025", -2.0]]))
check("FRED missing: DataMapper used", s["deficit"]["points"], [["2024", -2.7], ["2025", -2.0]])

edge = list(FRED)
s = {"deficit": {"label": "old", "points": edge}}
dm.overlay(s, "deficit", "I", "C", "NEW", fetcher=make([["2024", -2.739 + dm.TOLERANCE], ["2025", 0]]))
check("gap exactly at tolerance accepted", s["deficit"]["label"], "NEW")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for f, k, ind, iso in [("fetch_cl.py", "deficit", "GGXCNL_NGDP", "CHL"), ("fetch_co.py", "deficit", "GGXCNL_NGDP", "COL"),
                       ("fetch_ma.py", "debt_gdp", "GGXWDG_NGDP", "MAR")]:
    src = open(os.path.join(ROOT, f)).read()
    check(f"{f} asks the DataMapper for {k}", f'imf_datamapper.overlay(out["series"], "{k}", "{ind}", "{iso}"' in src, True)
    check(f"{f} asks after the FRED copy is fetched", src.find("imf_datamapper.overlay(") > src.find("FRED_SERIES.items()") > 0 or f == "fetch_ma.py", True)
check("Morocco sets the 2011 World Bank series aside", "_wb_stale" in open(os.path.join(ROOT, "fetch_ma.py")).read(), True)

print(f"test_imf_datamapper: {n} checks, {fails} failures")
sys.exit(1 if fails else 0)
