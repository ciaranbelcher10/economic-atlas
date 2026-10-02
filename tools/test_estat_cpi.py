#!/usr/bin/env python3
"""Tests fetch_jp's e-Stat CPI parser against a reply built to the shape
the live 2025-base table returned (probe, 2 Oct 2026, table 0004052037):
class tab 1=index / 2=month on month / 3=year on year, cat01 0001=all
items, area 00000=national, time codes like 2026000808 named 2026年8月.

    python3 tools/test_estat_cpi.py

Checks: the three kinds of figure are kept apart (an index must never be
read as a rate, or the reverse); other regions, other categories and
annual periods are ignored; the published rates are used as published;
when published rates are missing the rates are derived from the index;
and a reply whose 0001 is not all items is refused.
"""
import importlib.util, os, sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
sys.path.insert(0, REPO)
spec = importlib.util.spec_from_file_location("fetch_jp", "fetch_jp.py")
jp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(jp)

fails = 0
def check(cond, msg):
    global fails
    print(("  ok    " if cond else "  FAIL  ") + msg)
    fails += 0 if cond else 1

def reply(values, all_items_name="0001 総合"):
    times = [("2025000606", "2025年6月"), ("2026000606", "2026年6月"),
             ("2026000707", "2026年7月"), ("2026000808", "2026年8月"), ("2025000000", "2025年")]
    return {"GET_STATS_DATA": {"RESULT": {"STATUS": 0}, "STATISTICAL_DATA": {
        "CLASS_INF": {"CLASS_OBJ": [
            {"@id": "tab", "CLASS": [{"@code": "1", "@name": "指数"},
                                     {"@code": "2", "@name": "前月比・前年比・前年度比"},
                                     {"@code": "3", "@name": "前年同月比"}]},
            {"@id": "cat01", "CLASS": [{"@code": "0001", "@name": all_items_name},
                                       {"@code": "0002", "@name": "0002 食料"}]},
            {"@id": "area", "CLASS": [{"@code": "00000", "@name": "全国"},
                                      {"@code": "13100", "@name": "東京都区部"}]},
            {"@id": "time", "CLASS": [{"@code": c, "@name": n} for c, n in times]}]},
        "DATA_INF": {"VALUE": values}}}}

def v(tab, time, val, cat="0001", area="00000"):
    return {"@tab": tab, "@cat01": cat, "@area": area, "@time": time, "$": str(val)}

full = [v("1", "2025000606", 100.0), v("1", "2026000606", 101.6), v("1", "2026000707", 102.0),
        v("1", "2026000808", 102.2),
        v("3", "2026000606", 1.6), v("3", "2026000707", 1.9), v("3", "2026000808", 1.9),
        v("2", "2026000707", 0.4), v("2", "2026000808", 0.2),
        # noise that must be ignored
        v("1", "2026000808", 999.0, cat="0002"), v("3", "2026000808", 9.9, area="13100"),
        v("2", "2025000000", 3.2)]
p = jp._estat_cpi_parse(reply(full))
check(p["index"][-1] == ["2026-08", 102.2], f"index kept apart: latest {p['index'][-1]}")
check(p["yoy"] == [["2026-06", 1.6], ["2026-07", 1.9], ["2026-08", 1.9]],
      f"published year-on-year used as published (June 1.6, not 1.70 recalculated): {p['yoy']}")
check(p["mom"] == [["2026-07", 0.4], ["2026-08", 0.2]], f"published month-on-month kept apart: {p['mom']}")
check(all(x[1] < 200 for x in p["index"]), "food category (0002) ignored")
check(dict(p["yoy"]).get("2026-08") == 1.9, "Tokyo (area 13100) ignored")
check("2025" not in dict(p["mom"]), "annual period (2025年) ignored")
check(jp._estat_cpi_parse(reply(full, all_items_name="0001 食料")) is None,
      "a reply whose 0001 is not all items is refused, never guessed")

# Fallback: published rates missing -> derived from the index, with a log line.
jp._ESTAT_CACHE.clear()
jp._ESTAT_CACHE["parsed"] = jp._estat_cpi_parse(reply([x for x in full if x["@tab"] == "1"]))
derived = jp.fetch_estat_cpi()
# The fixture holds June 2025 only, so June 2026 is the one year-on-year
# rate the index can give: 101.6 / 100.0 - 1 = 1.6%.
check(derived == [["2026-06", 1.6]], f"no published rates: derived from the index instead ({derived})")
jp._ESTAT_CACHE.clear()
jp._ESTAT_CACHE["parsed"] = jp._estat_cpi_parse(reply(full))
check(jp.fetch_estat_cpi() == [["2026-06", 1.6], ["2026-07", 1.9], ["2026-08", 1.9]],
      "published rates present and current: used directly")
# Published rates that start later than the index must not shorten the
# series (the shrink guard would then keep the old table's figures for good):
# earlier periods are filled from the index, published values win where present.
jp._ESTAT_CACHE.clear()
idx = [v("1", f"{y}00{m:02d}{m:02d}", 100.0 + (y - 2024) * 2 + m * 0.1) for y in (2024, 2025, 2026) for m in (6, 7, 8)]
pub = [v("3", "2026000808", 1.9)]
r = reply(idx + pub)
r["GET_STATS_DATA"]["STATISTICAL_DATA"]["CLASS_INF"]["CLASS_OBJ"][3]["CLASS"] = [
    {"@code": f"{y}00{m:02d}{m:02d}", "@name": f"{y}年{m}月"} for y in (2024, 2025, 2026) for m in (6, 7, 8)]
jp._ESTAT_CACHE["parsed"] = jp._estat_cpi_parse(r)
got = dict(jp.fetch_estat_cpi())
check(set(got) == {"2025-06", "2025-07", "2025-08", "2026-06", "2026-07", "2026-08"} and got["2026-08"] == 1.9,
      f"published rates start late: earlier periods filled from the index, published value kept ({len(got)} periods)")
check(jp.ESTAT_CPI_STATS_DATA_ID == "0004052037", "wired to the 2025-base table")

print(f"\n{fails} failures")
sys.exit(1 if fails else 0)
