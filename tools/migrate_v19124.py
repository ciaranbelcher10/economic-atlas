#!/usr/bin/env python3
"""v1.9.124: one US$ GDP per person on every surface.

With Per capita and Convert to USD$ both on (nominal GDP), the country page GDP tile now shows the
calendar-year local-currency figure per person converted at THAT YEAR's average rate. That is the
same number as the GDP per capita tile, Compare, the Dashboard and the indicator page (UK 2025:
$57,861). v1.9.122 converted each quarter at its own rate first, which gave $57,871.

Idempotent: run twice, expect "62 changed" then "0 changed" (pages without the v1.9.122 block are
an error, not skipped).
Usage: python3 tools/migrate_v19124.py [repo_root]
"""
import glob, os, sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
MARK = "v1.9.124 per capita US$"
SKIP = {"chartmaker.html", "compare.html", "dashboard.html"}

DECL_OLD = "let PC_DROPPED = [], PC_GDP_SERIES = null;"
DECL_NEW = "let PC_DROPPED = [], PC_GDP_SERIES = null, PC_GDP_CAL = null;"

RESET_OLD = "  PC_APPLIED.clear(); PC_DROPPED = []; PC_GDP_SERIES = null;"
RESET_NEW = "  PC_APPLIED.clear(); PC_DROPPED = []; PC_GDP_SERIES = null; PC_GDP_CAL = null;"

SET_OLD = '    if(PC_APPLIED.has("gdp_level")) PC_GDP_SERIES = {...out.gdp_level, pcRolling};   // the per person series the page shows\n'
SET_NEW = SET_OLD + '''    // MARK: nominal GDP per person in US$ = the calendar-year local figure at that year's average
    // rate (the GDP per capita tile's own conversion), not a sum of quarters each at its own rate.
    if(PC_GDP_SERIES && TOGGLE_STATE.dollar && !TOGGLE_STATE.real && PAGE_DATA.fx_to_usd){
      const g0 = (pcRolling && rawSeries.gdp_level_annual) ? rawSeries.gdp_level_annual : rawSeries.gdp_level;
      if(g0 && isCurrencyUnit(g0.unit) && !isAlreadyUSD(g0.unit, "gdp_level") && !foreignCurrencyOf(g0.unit, PAGE_DATA.fx_to_usd)){
        const cal = pcCalendarYears({...pcSeries(g0).series, pcRolling});
        // whole local units first, as the stored GDP per capita series is, so the dollar figure matches to the dollar
        if(cal.freq === "years") PC_GDP_CAL = {...convertSeriesToUSD({...cal, unit: "\\u00a4", points: cal.points.map(([p, v]) => [p, Math.round(v)])}, PAGE_DATA.fx_to_usd), unit: "$ per person"};
      }
    }
'''.replace("MARK", MARK)

TILE_OLD = "    series = pcCalendarYears(PC_GDP_SERIES || series);"
TILE_NEW = "    series = PC_GDP_CAL || pcCalendarYears(PC_GDP_SERIES || series);"


def migrate(s):
    if MARK in s:
        return s, False
    for old, new, label in ((DECL_OLD, DECL_NEW, "decl"), (RESET_OLD, RESET_NEW, "reset"),
                            (SET_OLD, SET_NEW, "set"), (TILE_OLD, TILE_NEW, "tile")):
        n = s.count(old)
        if n != 1:
            raise SystemExit(f"anchor {label!r} found {n} times")
        s = s.replace(old, new)
    return s, True


def main():
    pages = sorted(f for f in glob.glob(os.path.join(ROOT, "*.html"))
                   if os.path.basename(f) not in SKIP and 'id="toggleCapita"' in open(f, encoding="utf-8").read())
    changed = 0
    for f in pages:
        s = open(f, encoding="utf-8").read()
        new, did = migrate(s)
        if did:
            open(f, "w", encoding="utf-8").write(new)
            changed += 1
    print(f"{len(pages)} page(s) checked, {changed} changed")


if __name__ == "__main__":
    main()
