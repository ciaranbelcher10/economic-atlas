#!/usr/bin/env python3
"""GDP overlay (v1.9.9): OECD quarterly national accounts onto IMF IFS (via FRED), South Africa and Argentina.

Inputs are embedded constants: the stored IFS history 2023-Q4..2026-Q1 as it stood on 25 Oct 2026, and the
OECD values for 2026-Q1 and 2026-Q2 as a probe on that day reported them. Nothing here reads the repo's data
files, so the test does not drift when the bot refreshes them. No network: every OECD call is mocked.

Run from the repo root:  python3 tools/test_gdp_overlay.py
"""
import io
import sys
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import gdp_overlay as go  # noqa: E402
import oecd_turn  # noqa: E402
import fetch_ar  # noqa: E402
import fetch_za  # noqa: E402

fails = []


def check(cond, msg):
    if not cond:
        fails.append(msg)
        print("FAIL", msg)


def case(fn):
    """Run a test case now; an exception in it (a broken production path) is a FAIL, not a crash."""
    try:
        fn()
    except Exception as exc:  # noqa: BLE001
        fails.append(f"{fn.__name__} raised {type(exc).__name__}: {exc}")
        print("FAIL", f"{fn.__name__} raised {type(exc).__name__}: {exc}")
    return fn


# The selectors, as literals: the OECD columns that pin down each series. Rows below are built from THESE,
# not from the fetchers' own constants, so a wrong selector in a fetcher cannot hide.
BASE = dict(TRANSACTION="B1GQ", TRANSFORMATION="N", UNIT_MEASURE="XDC")
EXPECTED_SEL = {
    "ZA": {"gdp_real": dict(BASE, PRICE_BASE="Q", ADJUSTMENT="Y"), "gdp_level": dict(BASE, PRICE_BASE="V", ADJUSTMENT="Y")},
    "AR": {"gdp_real": dict(BASE, PRICE_BASE="Q", ADJUSTMENT="N"), "gdp_level": dict(BASE, PRICE_BASE="V", ADJUSTMENT="Y")},
}


ZA_REAL = [["2023-Q4", 1163448.0], ["2024-Q1", 1164447.9], ["2024-Q2", 1167433.1], ["2024-Q3", 1164042.3], ["2024-Q4", 1168684.4], ["2025-Q1", 1169274.0], ["2025-Q2", 1178624.5], ["2025-Q3", 1182149.3], ["2025-Q4", 1186552.8], ["2026-Q1", 1193022.7]]
ZA_LEVEL = [["2023-Q4", 1795197.3], ["2024-Q1", 1810621.8], ["2024-Q2", 1834603.3], ["2024-Q3", 1841357.0], ["2024-Q4", 1865867.5], ["2025-Q1", 1857562.3], ["2025-Q2", 1887886.8], ["2025-Q3", 1929740.3], ["2025-Q4", 1966604.0], ["2026-Q1", 2006137.3]]
AR_REAL = [["2023-Q4", 175135.8], ["2024-Q1", 167054.9], ["2024-Q2", 182477.3], ["2024-Q3", 178574.8], ["2024-Q4", 179880.8], ["2025-Q1", 177273.8], ["2025-Q2", 194370.6], ["2025-Q3", 184283.8], ["2025-Q4", 183800.5], ["2026-Q1", 181400.1]]
AR_LEVEL = [["2023-Q4", 71164886.8], ["2024-Q1", 112848475.9], ["2024-Q2", 134826137.6], ["2024-Q3", 159500922.9], ["2024-Q4", 177201474.6], ["2025-Q1", 190851303.0], ["2025-Q2", 201184060.4], ["2025-Q3", 221655447.3], ["2025-Q4", 236548987.5], ["2026-Q1", 254218928.4]]
# OECD, as reported by the 25 Oct 2026 probe (Q1 revised, Q2 new); earlier quarters equal IFS to 0.00%
OECD_NEW = {
    "ZA_REAL": {"2026-Q1": 1191559.5, "2026-Q2": 1188700.0},
    "ZA_LEVEL": {"2026-Q1": 2010391.3, "2026-Q2": 1972918.8},
    "AR_REAL": {"2026-Q1": 181540.8, "2026-Q2": 198200.1},
    "AR_LEVEL": {"2026-Q1": 254517163.1, "2026-Q2": 271170842.4},
}


def cand_for(base, new):
    d = {p: v for p, v in base if p < "2026-Q1"}
    d.update(new)
    return d


def rows_for(sel, cand, decoys=()):
    """OECD-style CSV rows: the wanted series plus decoys the selector must not pick up."""
    rows = [dict(sel, TIME_PERIOD=p, OBS_VALUE=str(v)) for p, v in cand.items()]
    for d_sel, d_val in decoys:
        rows += [dict(d_sel, TIME_PERIOD=p, OBS_VALUE=str(d_val)) for p in cand]
    return rows


# ---------------------------------------------------------------- overlay(): the checks
@case
def overlay_applies():
    m, rep = go.overlay(ZA_REAL, cand_for(ZA_REAL, OECD_NEW["ZA_REAL"]))
    check(rep["applied"], f"ZA real: expected applied, got {rep}")
    check(m[-1] == ["2026-Q2", 1188700.0] and len(m) == len(ZA_REAL) + 1, "ZA real: Q2 not added")
    check(dict(map(tuple, m))["2026-Q1"] == 1191559.5, "ZA real: Q1 not replaced by the revised vintage")
    check(rep["from"] == "2024-Q2" and rep["added"] == 1 and rep["replaced"] == 8, f"ZA real: window wrong {rep}")
    check(m[:2] == ZA_REAL[:2], "points before the window must be left exactly as fetched")
    g = {p: v for p, v in fetch_za.gdp_growth_from_level(m)}
    check(g["2026-Q2"] == -0.24 and g["2026-Q1"] == 0.422, f"ZA growth wrong: Q1 {g.get('2026-Q1')} Q2 {g.get('2026-Q2')}")
    naive = {p: v for p, v in fetch_za.gdp_growth_from_level(ZA_REAL + [["2026-Q2", 1188700.0]])}
    check(abs(naive["2026-Q2"] - (-0.362)) < 0.01, "sanity: a bare append gives the wrong Q2 rate (-0.36)")


@case
def overlay_refuses_level_break():
    bad = {p: v * 1.03 for p, v in cand_for(ZA_REAL, OECD_NEW["ZA_REAL"]).items()}
    m2, rep2 = go.overlay(ZA_REAL, bad)
    check(not rep2["applied"] and "differs" in rep2["reason"] and m2 == ZA_REAL, f"3% level break must be refused: {rep2}")


@case
def overlay_refuses_gaps():
    gap = cand_for(ZA_REAL, OECD_NEW["ZA_REAL"])
    del gap["2025-Q3"]
    m3, rep3 = go.overlay(ZA_REAL, gap)
    check(not rep3["applied"], f"a gap in the window must be refused: {rep3}")
    gap2 = cand_for(ZA_REAL, {"2026-Q2": 1188700.0})      # Q1 absent: Q2 arrives without its predecessor
    assert "2026-Q1" not in gap2
    m3b, rep3b = go.overlay(ZA_REAL, gap2)
    check(not rep3b["applied"] and "gap" in rep3b["reason"], f"a missing Q1 before Q2 must be refused: {rep3b}")


@case
def overlay_refuses_thin_or_old_or_odd_inputs():
    short = {p: v for p, v in cand_for(ZA_REAL, OECD_NEW["ZA_REAL"]).items() if p >= "2025-Q2"}
    m4, rep4 = go.overlay(ZA_REAL, short)
    check(not rep4["applied"] and "overlapping" in rep4["reason"], f"too little overlap must be refused: {rep4}")
    older = {p: v for p, v in cand_for(ZA_REAL, {}).items() if p <= "2025-Q4"}
    m5, rep5 = go.overlay(ZA_REAL, older)
    check(not rep5["applied"] and "before" in rep5["reason"], f"OECD ending before IFS must be refused: {rep5}")
    m6, rep6 = go.overlay([["2025", 1.0], ["2026", 2.0]], {"2026-Q1": 1.0})
    check(not rep6["applied"], "a non-quarterly base must be refused")
    m7, rep7 = go.overlay(ZA_REAL, {})
    check(not rep7["applied"], "an empty OECD series must be refused")
    same = {p: v for p, v in ZA_REAL}
    m8, rep8 = go.overlay(ZA_REAL, same)
    check(rep8["applied"] and rep8["added"] == 0 and m8 == ZA_REAL, "an OECD series equal to IFS should change nothing")

# ---------------------------------------------------------------- select(): precision and ambiguity
@case
def select_precision_and_ambiguity():
    SEL = dict(TRANSACTION="B1GQ", PRICE_BASE="Q", ADJUSTMENT="Y", TRANSFORMATION="N", UNIT_MEASURE="XDC")
    rows = rows_for(SEL, {"2026-Q1": 1.0, "2026-Q2": 2.0},
                    decoys=[(dict(SEL, PRICE_BASE="V"), 99.0), (dict(SEL, ADJUSTMENT="N"), 77.0),
                            (dict(SEL, TRANSFORMATION="G1", UNIT_MEASURE="PC"), 5.0)])
    check(go.select(rows, **SEL) == {"2026-Q1": 1.0, "2026-Q2": 2.0}, "select picked up a decoy series")
    amb = rows + [dict(SEL, TIME_PERIOD="2026-Q2", OBS_VALUE="3.0")]
    try:
        go.select(amb, **SEL)
        check(False, "an ambiguous selector must raise")
    except ValueError:
        pass
    dup_same = rows + [dict(SEL, TIME_PERIOD="2026-Q2", OBS_VALUE="2.0")]
    check(go.select(dup_same, **SEL)["2026-Q2"] == 2.0, "identical duplicate rows are harmless")
    check(go.select([dict(SEL, TIME_PERIOD="2026-M05", OBS_VALUE="1")], **SEL) == {}, "non-quarterly periods ignored")

# ---------------------------------------------------------------- the fetchers' wiring
def run_overlay(mod, series, rows, iso):
    """Run a fetcher's overlay with the OECD call mocked; assert it asked for the right country."""
    asked = []
    buf = io.StringIO()
    with mock.patch.object(go, "qna_rows", side_effect=lambda i: asked.append(i) or rows), redirect_stdout(buf):
        mod.overlay_gdp(series)
    check(asked == [iso], f"{mod.__name__} asked the OECD for {asked}, expected [{iso!r}]")
    return buf.getvalue()


def mk(real, level, real_label, level_label):
    return {"gdp_real": {"label": real_label, "unit": "x", "freq": "quarters", "points": [list(p) for p in real]},
            "gdp_level": {"label": level_label, "unit": "x", "freq": "quarters", "points": [list(p) for p in level]}}


@case
def selectors_are_pinned():
    check(fetch_za.GDP_OVERLAY == EXPECTED_SEL["ZA"], f"fetch_za.GDP_OVERLAY selectors changed: {fetch_za.GDP_OVERLAY}")
    check(fetch_ar.GDP_OVERLAY == EXPECTED_SEL["AR"], f"fetch_ar.GDP_OVERLAY selectors changed: {fetch_ar.GDP_OVERLAY}")


@case
def za_wiring():
    za_sel = EXPECTED_SEL["ZA"]
    za_rows = (rows_for(za_sel["gdp_real"], cand_for(ZA_REAL, OECD_NEW["ZA_REAL"]),
                        decoys=[(dict(za_sel["gdp_real"], ADJUSTMENT="N"), 12345.0)])
               + rows_for(za_sel["gdp_level"], cand_for(ZA_LEVEL, OECD_NEW["ZA_LEVEL"]),
                          decoys=[(dict(za_sel["gdp_level"], ADJUSTMENT="N"), 54321.0)]))
    s = mk(ZA_REAL, ZA_LEVEL, "Real GDP, SA (NGDPRSAXDCZAQ)", "GDP nominal, SA (NGDPSAXDCZAQ)")
    out = run_overlay(fetch_za, s, za_rows, "ZAF")
    check(s["gdp_real"]["points"][-1] == ["2026-Q2", 1188700.0], f"ZA wiring: real Q2 wrong: {s['gdp_real']['points'][-2:]}")
    check(s["gdp_level"]["points"][-1] == ["2026-Q2", 1972918.8], f"ZA wiring: nominal Q2 wrong: {s['gdp_level']['points'][-2:]}")
    check(go.RELABEL in s["gdp_real"]["label"] and s["gdp_real"]["label"].startswith("Real GDP, SA (NGDPRSAXDCZAQ"),
          f"ZA wiring: label {s['gdp_real']['label']}")
    check(go.relabel(s["gdp_real"]["label"]) == s["gdp_real"]["label"], "relabel must be idempotent")
    check("ok  gdp_real" in out and "ok  gdp_level" in out, f"ZA wiring: log lines missing: {out}")



@case
def ar_wiring():
    ar_sel = EXPECTED_SEL["AR"]
    ar_rows = (rows_for(ar_sel["gdp_real"], cand_for(AR_REAL, OECD_NEW["AR_REAL"]),
                        decoys=[(dict(ar_sel["gdp_real"], ADJUSTMENT="Y"), 186992.5)])
               + rows_for(ar_sel["gdp_level"], cand_for(AR_LEVEL, OECD_NEW["AR_LEVEL"]),
                          decoys=[(dict(ar_sel["gdp_level"], ADJUSTMENT="N"), 281834873.0)]))
    s = mk(AR_REAL, AR_LEVEL, "Real GDP, constant prices, NSA (IMF IFS) (NGDPRNSAXDCARQ)",
           "Nominal GDP, current prices, seasonally adjusted (IMF IFS) (NGDPSAXDCARQ)")
    out = run_overlay(fetch_ar, s, ar_rows, "ARG")
    check(s["gdp_real"]["points"][-1] == ["2026-Q2", 198200.1], f"AR wiring: real Q2 wrong: {s['gdp_real']['points'][-2:]}")
    check(s["gdp_level"]["points"][-1] == ["2026-Q2", 271170842.4], f"AR wiring: nominal Q2 wrong")
    yoy = {p: v for p, v in fetch_ar.yoy_from_level(s["gdp_real"]["points"], 4)}
    check(abs(yoy["2026-Q2"] - 1.97) < 0.02, f"AR year-on-year for Q2 should be about 1.97, got {yoy.get('2026-Q2')}")



@case
def failed_validation_keeps_ifs():
    za_sel = EXPECTED_SEL["ZA"]
    za_rows = (rows_for(za_sel["gdp_real"], cand_for(ZA_REAL, OECD_NEW["ZA_REAL"]))
               + rows_for(za_sel["gdp_level"], cand_for(ZA_LEVEL, OECD_NEW["ZA_LEVEL"])))
    s = mk(ZA_REAL, ZA_LEVEL, "r", "l")
    broken = [dict(r, OBS_VALUE=str(float(r["OBS_VALUE"]) * 1.05)) for r in za_rows]
    out = run_overlay(fetch_za, s, broken, "ZAF")
    check(s["gdp_real"]["points"] == [list(p) for p in ZA_REAL] and "WARN" in out and "not applied" in out,
          f"a failed check must keep IFS and warn: {out}")



@case
def off_turn_skips():
    for mod in (fetch_za, fetch_ar):
        s = mk(ZA_REAL, ZA_LEVEL, "r", "l")
        buf = io.StringIO()
        with mock.patch.object(oecd_turn, "check", side_effect=oecd_turn.NotThisHour("OECD turn is group C")), \
                mock.patch.object(go.requests, "get", side_effect=AssertionError("must not call OECD off-turn")), \
                redirect_stdout(buf):
            mod.overlay_gdp(s)
        check(s["gdp_real"]["points"] == [list(p) for p in ZA_REAL] and "SKIP" in buf.getvalue() and "WARN" not in buf.getvalue(),
              f"{mod.__name__}: off-turn must SKIP without warning or request: {buf.getvalue()!r}")



@case
def oecd_unreachable_warns():
    for mod in (fetch_za, fetch_ar):
        s = mk(ZA_REAL, ZA_LEVEL, "r", "l")
        buf = io.StringIO()
        with mock.patch.object(oecd_turn, "check", return_value=None), \
                mock.patch.object(go.time, "sleep", return_value=None), \
                mock.patch.object(go.requests, "get", side_effect=go.requests.ConnectionError("down")), \
                redirect_stdout(buf):
            mod.overlay_gdp(s)
        check(s["gdp_real"]["points"] == [list(p) for p in ZA_REAL] and "WARN" in buf.getvalue(),
              f"{mod.__name__}: an unreachable OECD must warn and keep IFS: {buf.getvalue()!r}")



@case
def overlay_runs_before_growth():
    for fn in ("fetch_za.py", "fetch_ar.py"):
        src = (ROOT / fn).read_text(encoding="utf-8")
        i_call, i_growth = src.find('overlay_gdp(out["series"])'), src.find('_growth_label("Real GDP growth')
        check(0 < i_call < i_growth, f"{fn}: overlay_gdp must run before gdp_growth is derived")


@case
def growth_label_follows_real_series():
    for mod, lab in ((fetch_za, "Real GDP growth, QoQ, SA (derived from NGDPRSAXDCZAQ)"),
                     (fetch_ar, "Real GDP growth, YoY (derived from NGDPRNSAXDCARQ, not seasonally adjusted)")):
        plain = {"gdp_real": {"label": "Real GDP (X)"}}
        over = {"gdp_real": {"label": go.relabel("Real GDP (X)")}}
        check(mod._growth_label(lab, plain) == lab, f"{mod.__name__}: growth label must be unchanged without an overlay")
        check(go.RELABEL in mod._growth_label(lab, over) and mod._growth_label(lab, over).startswith(lab[:-1]),
              f"{mod.__name__}: growth label must carry the overlay note when the real series does")


print("test_gdp_overlay:", "FAILED" if fails else "ok", f"({len(fails)} failures)")
sys.exit(1 if fails else 0)
