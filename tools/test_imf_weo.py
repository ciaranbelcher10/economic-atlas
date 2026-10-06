#!/usr/bin/env python3
"""Tests imf_weo.parse against replies built to the shape the live probe
returned (Sep 2026): series dims COUNTRY/INDICATOR/FREQUENCY, an
out-of-order TIME_PERIOD axis, COUNTRY_UPDATE_DATE as a series attribute.

    python3 tools/test_imf_weo.py

Checks: projections (years >= the update year) are never kept; values map
to the right year despite the scrambled axis; a stale edition, a missing
update date and a missing country all return None; and every fetch script
that used FRED's frozen WEO family now calls imf_weo instead.
"""
import glob, os, re, sys
from datetime import datetime, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
sys.path.insert(0, REPO)
import imf_weo  # noqa: E402

fails = 0
def check(cond, msg):
    global fails
    print(("  ok    " if cond else "  FAIL  ") + msg)
    fails += 0 if cond else 1

TIMES = ["1993", "2024", "2031", "2023", "2025", "1987", "2026"]  # scrambled on purpose
def reply(update="9/26/2025", country="AUS", ind="GGXCNL_NGDP", with_attr=True):
    obs = {"0": ["-4.7"], "1": ["-2.251354"], "2": ["-1.4"], "3": ["-1.26333"],
           "4": ["-2.782384"], "5": ["0.9"], "6": ["-2.43"]}
    return {"data": {"structures": [{
        "dimensions": {
            "series": [{"id": "COUNTRY", "values": [{"id": country}]},
                       {"id": "INDICATOR", "values": [{"id": ind}]},
                       {"id": "FREQUENCY", "values": [{"id": "A"}]}],
            "observation": [{"id": "TIME_PERIOD",
                             "values": [{"value": t} for t in TIMES]}]},
        "attributes": {"series": [
            {"id": "SCALE", "values": [{"value": "0"}]},
            {"id": "COUNTRY_UPDATE_DATE", "values": [{"value": update}]}]}}],
        "dataSets": [{"series": {"0:0:0": {
            "attributes": [0, 0] if with_attr else [0, None],
            "observations": obs}}}]}}

NOW = datetime(2026, 9, 29, tzinfo=timezone.utc)
pts, info = imf_weo.parse(reply(), "AUS", "GGXCNL_NGDP", NOW)
years = [p[0] for p in pts]
check(years == ["1987", "1993", "2023", "2024"], f"actual years only, sorted: {years}")
check(dict(pts)["2024"] == -2.251 and dict(pts)["2023"] == -1.263,
      "values land on the right year despite the scrambled axis")
check(info["dropped"] == 3, f"2025, 2026, 2031 dropped as projections ({info['dropped']})")
check(imf_weo.parse(reply("9/26/2024"), "AUS", "GGXCNL_NGDP", NOW)[0] is None,
      "edition updated 2024-09-26 (733 days) rejected as stale")
check(imf_weo.parse(reply("3/15/2026"), "AUS", "GGXCNL_NGDP", NOW)[0][-1][0] == "2025",
      "a 2026 edition keeps 2025 (the next edition moves forward by itself)")
check(imf_weo.parse(reply(with_attr=False), "AUS", "GGXCNL_NGDP", NOW)[0] is None,
      "missing update date: rejected, never guessed")
check(imf_weo.parse(reply(), "JPN", "GGXCNL_NGDP", NOW)[0] is None,
      "country absent from the reply: None")
check(imf_weo.parse(reply(), "AUS", "GGXWDG_NGDP", NOW)[0] is None,
      "indicator absent from the reply: None")

# The live WEO reply carried COUNTRY_UPDATE_DATE in a form the first
# parser did not read (every CI run on 30 Sep 2026 logged "rejected: no
# COUNTRY_UPDATE_DATE" after status=200). Every form SDMX-JSON allows must
# resolve to the same answer.
def reply_attr(attr, values):
    r = reply()
    st = r["data"]["structures"][0]
    st["attributes"]["series"][1]["values"] = values
    r["data"]["dataSets"][0]["series"]["0:0:0"]["attributes"] = [0, attr]
    return r
for label, attr, vals in [
        ("index as number", 0, [{"value": "9/26/2025"}]),
        ("index as text", "0", [{"value": "9/26/2025"}]),
        ("the date itself", "9/26/2025", []),
        ("date in a value object", {"value": "9/26/2025"}, []),
        ("index in a list", [0], [{"id": "9/26/2025"}]),
        ("localised name", 0, [{"name": {"en": "9/26/2025"}}])]:
    got = imf_weo.parse(reply_attr(attr, vals), "AUS", "GGXCNL_NGDP", NOW)[0]
    check(got is not None and got[-1][0] == "2024", f"update date given as {label}: kept to 2024")
check(imf_weo.parse(reply_attr("7", [{"value": "9/26/2025"}]), "AUS", "GGXCNL_NGDP", NOW)[0] is None,
      "index pointing past the value list: rejected, never guessed")

frozen = re.compile(r'"(GGGDTA|GGNLBA)[A-Z]{2}A188N"')
for f in sorted(glob.glob("fetch_*.py")):
    t = open(f, encoding="utf-8").read()
    check(not frozen.search(t), f"{f}: no frozen FRED WEO series wired")
wired = [f for f in sorted(glob.glob("fetch_*.py"))
         if "imf_weo.fetch(" in open(f, encoding="utf-8").read()]
check(len(wired) == 13, f"{len(wired)} fetch scripts call imf_weo.fetch (11 from v1.6.27, plus fetch_cn.py and fetch_my.py)")

print(f"\n{fails} failures")
sys.exit(1 if fails else 0)
