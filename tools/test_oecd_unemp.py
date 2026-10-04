#!/usr/bin/env python3
"""Offline checks for the OECD unemployment switch and the dashboard
explainer fix (v1.6.43).

    python3 tools/test_oecd_unemp.py     # prints "N ok", exits 1 on any failure
"""
import json, os, re, sys
from datetime import datetime

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import oecd_unemp, oecd_turn  # noqa: E402

CASES = {"South Korea": ("KOR", "fetch_kr.py", "southkorea.html", "LRHUTTTTKRM156S"),
         "Israel": ("ISR", "fetch_il.py", "israel.html", "LRHUTTTTILM156S"),
         "Turkey": ("TUR", "fetch_tr.py", "turkey.html", "LRHUTTTTTRM156S")}
ok, fails = 0, []


def check(cond, msg):
    global ok
    if cond:
        ok += 1
    else:
        fails.append(msg)


txt = ("STRUCTURE,REF_AREA,MEASURE,TIME_PERIOD,OBS_VALUE\n"
       "x,KOR,UNE_LF_M,2026-07,2.8\nx,KOR,UNE_LF_M,2026-08,2.7\n"
       "x,KOR,OTHER,2026-08,9\nx,KOR,UNE_LF_M,2026-Q2,3\nx,KOR,UNE_LF_M,2026-09,\n")
check(oecd_unemp.parse(txt) == [["2026-07", 2.8], ["2026-08", 2.7]], "parse keeps monthly UNE_LF_M only")
check(".UNE_LF_M.._Z.Y._T.Y_GE15..M" in oecd_unemp.url("KOR"), "key: measure, SA, total, 15+, monthly")

# off-turn raises NotThisHour before any request
os.environ["OECD_TURN_GROUP"] = "A"
sys.argv = ["fetch_kr.py"]
try:
    oecd_unemp.fetch("KOR"); check(False, "off-turn fetch should raise NotThisHour")
except oecd_turn.NotThisHour:
    check(True, "")
del os.environ["OECD_TURN_GROUP"]

src = json.load(open(os.path.join(REPO, "data-metric-sources.json"), encoding="utf-8"))
compare = open(os.path.join(REPO, "compare.html"), encoding="utf-8").read()
for country, (iso, script, page, fred) in CASES.items():
    s = open(os.path.join(REPO, script), encoding="utf-8").read()
    check(f'oecd_unemp.fetch("{iso}")' in s, f"{country}: script calls oecd_unemp.fetch")
    check(re.search(r"except oecd_turn\.NotThisHour as exc:\n.*\n\s+skip_fred\.add\(\"unemployment\"\)", s),
          f"{country}: off-turn skips FRED so the guard carries over")
    check(re.search(r"FRED_SERIES\.items\(\):\n\s+if name in skip_fred:\n\s+continue", s),
          f"{country}: FRED loop honours skip_fred")
    check(s.index("oecd_unemp.fetch(") < s.index("FRED_SERIES.items():"), f"{country}: OECD before FRED")
    check("DF_IALFS_UNE_M" in src[country]["unemployment"]["source"], f"{country}: popover cites OECD")
    blk = re.search(r'\n  "?%s"?: \{(.*?)\n  \}' % re.escape(country), compare, re.S)
    check(blk and "DF_IALFS_UNE_M" in re.search(r'unemployment: "([^"]*)"', blk.group(1)).group(1),
          f"{country}: Compare block cites OECD")
    html = open(os.path.join(REPO, page), encoding="utf-8").read()
    check(fred not in html, f"{country}: page no longer cites {fred}")
    check(html.count("OECD DF_IALFS_UNE_M") == 2, f"{country}: tile and info panel cite OECD")

dash = open(os.path.join(REPO, "dashboard.html"), encoding="utf-8").read()
check("explainerOf(it.key, it.country)" in dash, "dashboard picker passes the country")
check("function explainerOf(key, country)" in dash, "dashboard explainer is per country")

for f in fails:
    print("FAIL", f)
print(f"{ok} ok")
sys.exit(1 if fails else 0)
