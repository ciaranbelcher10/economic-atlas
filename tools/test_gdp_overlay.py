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
import series_guard  # noqa: E402
import fetch_ar  # noqa: E402
import fetch_za  # noqa: E402
import fetch_mx  # noqa: E402
import fetch_kr  # noqa: E402

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
    "MX": {"gdp_level": dict(BASE, PRICE_BASE="V", ADJUSTMENT="Y")},   # v1.9.25: nominal only; real GDP is current
    "KR": {"gdp_level": dict(BASE, PRICE_BASE="V", ADJUSTMENT="Y")},
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

    # Production, 25 Oct 2026: South Africa's series sits in two OECD tables (T0101, T0102) whose copies differ
    # by rounding in the last decimal. That is the same figure, not a conflict; the lower value is kept, and the
    # answer must not depend on row order.
    rnd = [dict(SEL, TIME_PERIOD="2012-Q2", OBS_VALUE="1048271.7", TABLE_IDENTIFIER="T0102"),
           dict(SEL, TIME_PERIOD="2012-Q2", OBS_VALUE="1048271.6", TABLE_IDENTIFIER="T0101")]
    check(go.select(rnd, **SEL) == {"2012-Q2": 1048271.6}, f"two tables, last-decimal rounding: {go.select(rnd, **SEL)}")
    check(go.select(list(reversed(rnd)), **SEL) == {"2012-Q2": 1048271.6}, "result must not depend on row order")
    inside = [dict(SEL, TIME_PERIOD="2012-Q2", OBS_VALUE="1048271.7"), dict(SEL, TIME_PERIOD="2012-Q2", OBS_VALUE="1048280.0")]
    check(go.select(inside, **SEL) == {"2012-Q2": 1048271.7}, "a difference just inside the rounding tolerance is the same figure")
    for far_v in ("1048283.0", "1058754.4"):    # just outside the tolerance, and 1% apart: real conflicts
        far = [dict(SEL, TIME_PERIOD="2012-Q2", OBS_VALUE="1048271.7"), dict(SEL, TIME_PERIOD="2012-Q2", OBS_VALUE=far_v)]
        try:
            go.select(far, **SEL)
            check(False, f"values 1048271.7 and {far_v} must be refused as a real conflict")
        except ValueError as exc:
            check("ambiguous" in str(exc) and "2012-Q2" in str(exc), f"the refusal must name the quarter: {exc}")

# ---------------------------------------------------------------- the fetchers' wiring
def run_overlay(mod, series, rows, iso, notes=None):
    """Run a fetcher's overlay with the OECD call mocked; assert it asked for the right country."""
    asked = []
    buf = io.StringIO()
    with mock.patch.object(go, "qna_rows", side_effect=lambda i: asked.append(i) or rows), redirect_stdout(buf):
        mod.overlay_gdp(series, notes)
    check(asked == [iso], f"{mod.__name__} asked the OECD for {asked}, expected [{iso!r}]")
    return buf.getvalue()


def mk(real, level, real_label, level_label):
    return {"gdp_real": {"label": real_label, "unit": "x", "freq": "quarters", "points": [list(p) for p in real]},
            "gdp_level": {"label": level_label, "unit": "x", "freq": "quarters", "points": [list(p) for p in level]}}


@case
def selectors_are_pinned():
    check(fetch_za.GDP_OVERLAY == EXPECTED_SEL["ZA"], f"fetch_za.GDP_OVERLAY selectors changed: {fetch_za.GDP_OVERLAY}")
    check(fetch_ar.GDP_OVERLAY == EXPECTED_SEL["AR"], f"fetch_ar.GDP_OVERLAY selectors changed: {fetch_ar.GDP_OVERLAY}")
    check(fetch_mx.GDP_OVERLAY == EXPECTED_SEL["MX"], f"fetch_mx.GDP_OVERLAY selectors changed: {fetch_mx.GDP_OVERLAY}")
    check(fetch_kr.GDP_OVERLAY == EXPECTED_SEL["KR"], f"fetch_kr.GDP_OVERLAY selectors changed: {fetch_kr.GDP_OVERLAY}")


@case
def za_wiring():
    za_sel = EXPECTED_SEL["ZA"]
    za_rows = (rows_for(za_sel["gdp_real"], cand_for(ZA_REAL, OECD_NEW["ZA_REAL"]),
                        decoys=[(dict(za_sel["gdp_real"], ADJUSTMENT="N"), 12345.0)])
               + rows_for(za_sel["gdp_level"], cand_for(ZA_LEVEL, OECD_NEW["ZA_LEVEL"]),
                          decoys=[(dict(za_sel["gdp_level"], ADJUSTMENT="N"), 54321.0)]))
    # as in production: every figure also appears in a second OECD table, 0.1 higher after rounding
    za_rows = za_rows + [dict(r, TABLE_IDENTIFIER="T0102", OBS_VALUE=str(float(r["OBS_VALUE"]) + 0.1)) for r in za_rows]
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
        i_call, i_growth = src.find('overlay_gdp(out["series"], _overlay_notes)'), src.find('_growth_label("Real GDP growth')
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


@case
def guard_holds_growth_when_a_run_comes_back_a_quarter_behind():
    """Production, 27 Oct 2026: on a run outside the OECD turn, growth is re-derived from the IFS-only real series,
    which ends a quarter before the stored OECD-extended one. series_guard must keep the stored growth, for both
    countries, so growth never lags real GDP. (Argentina's fetcher used to exempt gdp_growth: it did not hold.)"""
    cases = ((fetch_za, ZA_REAL, OECD_NEW["ZA_REAL"], fetch_za.gdp_growth_from_level),
             (fetch_ar, AR_REAL, OECD_NEW["AR_REAL"], lambda pts: fetch_ar.yoy_from_level(pts, 4)))
    for mod, real, new, growth in cases:
        ext, rep = go.overlay(real, cand_for(real, new))
        assert rep["applied"], rep
        prev = {"gdp_real": {"label": "r", "unit": "x", "freq": "quarters", "points": [list(p) for p in ext]},
                "gdp_growth": {"label": "g", "unit": "%", "freq": "quarters", "points": growth(ext)}}
        out = {"gdp_real": {"label": "r", "unit": "x", "freq": "quarters", "points": [list(p) for p in real]},
               "gdp_growth": {"label": "g", "unit": "%", "freq": "quarters", "points": growth([list(p) for p in real])}}
        check(out["gdp_growth"]["points"][-1][0] == "2026-Q1" and prev["gdp_growth"]["points"][-1][0] == "2026-Q2",
              f"{mod.__name__}: test setup wrong")
        with mock.patch.object(series_guard, "_age_days", return_value=120):
            series_guard.apply_guard(out, prev, allow_shrink=mod.ALLOW_SHRINK, log=None)
        check(out["gdp_growth"]["points"] == prev["gdp_growth"]["points"],
              f"{mod.__name__}: guard let growth fall back to {out['gdp_growth']['points'][-1]} "
              f"(stored ends {prev['gdp_growth']['points'][-1][0]}); ALLOW_SHRINK={mod.ALLOW_SHRINK}")
        check(out["gdp_real"]["points"] == prev["gdp_real"]["points"], f"{mod.__name__}: guard let real GDP fall back")
        # and an on-turn run, which reaches 2026-Q2 again, is accepted as an update
        out2 = {k: {**v, "points": [list(p) for p in v["points"]]} for k, v in prev.items()}
        with mock.patch.object(series_guard, "_age_days", return_value=120):
            verdicts = series_guard.apply_guard(out2, prev, allow_shrink=mod.ALLOW_SHRINK, log=None)
        check(out2["gdp_growth"]["points"] == prev["gdp_growth"]["points"] and verdicts["gdp_growth"][0] != "kept",
              f"{mod.__name__}: an equal series must be accepted: {verdicts.get('gdp_growth')}")


@case
def relabel_names_both_sources():
    """An overlaid series is still mostly IMF IFS, so its label must say IMF as well as OECD, once. A label that
    says only OECD made citation_provider.py report a provider mismatch once South Africa's overlay reached the data."""
    z = go.relabel("Real GDP, SA (NGDPRSAXDCZAQ)")
    check("IMF IFS" in z and go.RELABEL in z and z.startswith("Real GDP, SA (NGDPRSAXDCZAQ") and z.endswith("QNA)"),
          f"a label with no source named must gain both: {z}")
    a = go.relabel("Real GDP, constant prices, NSA (IMF IFS) (NGDPRNSAXDCARQ)")
    check(a.count("IMF") == 1 and go.RELABEL in a, f"a label that already names IMF must not repeat it: {a}")
    g = go.relabel("Real GDP growth, YoY (derived from NGDPRNSAXDCARQ, not seasonally adjusted)")
    check("IMF IFS" in g and go.RELABEL in g, f"a derived growth label must name both: {g}")
    check(go.relabel(z) == z and go.relabel(a) == a and go.relabel(g) == g, "relabel must be idempotent")


COUNTRIES_UNDER_TEST = (
    ("ZA", fetch_za, "ZAF", ZA_REAL, ZA_LEVEL, OECD_NEW["ZA_REAL"], OECD_NEW["ZA_LEVEL"]),
    ("AR", fetch_ar, "ARG", AR_REAL, AR_LEVEL, OECD_NEW["AR_REAL"], OECD_NEW["AR_LEVEL"]),
)


def _rows(code, base_real, base_level, new_real, new_level, break_level=False, conflict_real=False):
    sel = EXPECTED_SEL[code]
    real = rows_for(sel["gdp_real"], cand_for(base_real, new_real))
    lvl = rows_for(sel["gdp_level"], cand_for(base_level, new_level))
    if break_level:
        lvl = [dict(r, OBS_VALUE=str(float(r["OBS_VALUE"]) * 1.05)) for r in lvl]
    if conflict_real:     # two values for one quarter, 50% apart: the selector no longer pins one series
        real = real + [dict(real[-1], OBS_VALUE=str(float(real[-1]["OBS_VALUE"]) * 1.5))]
    return real + lvl


@case
def notes_record_every_decision():
    for code, mod, iso, br, bl, nr, nl in COUNTRIES_UNDER_TEST:
        who = mod.__name__
        n = {}
        run_overlay(mod, mk(br, bl, "r", "l"), _rows(code, br, bl, nr, nl), iso, n)
        check(set(n) == {"gdp_real", "gdp_level"} and all(v["status"] == "applied" and "max deviation" in v["detail"] for v in n.values()),
              f"{who}: both series applied must be recorded as applied with their deviation: {n}")
        n = {}
        run_overlay(mod, mk(br, bl, "r", "l"), _rows(code, br, bl, nr, nl, break_level=True), iso, n)
        check(n.get("gdp_real", {}).get("status") == "applied", f"{who}: real GDP must still apply: {n}")
        check(n.get("gdp_level", {}).get("status") == "refused" and "differs" in n["gdp_level"]["detail"],
              f"{who}: a level break must be recorded as refused, with the reason: {n.get('gdp_level')}")
        # one series failing (the FIRST one) must not stop the other
        n = {}
        s = mk(br, bl, "r", "l")
        run_overlay(mod, s, _rows(code, br, bl, nr, nl, conflict_real=True), iso, n)
        check(n.get("gdp_real", {}).get("status") == "refused" and "two different values for 2026-Q2" in n["gdp_real"]["detail"],
              f"{who}: a disagreement in the new quarter must be recorded as refused, naming the quarter: {n.get('gdp_real')}")
        check(n.get("gdp_level", {}).get("status") == "applied" and s["gdp_level"]["points"][-1][0] == "2026-Q2",
              f"{who}: nominal GDP must still apply when real GDP errors first: {n.get('gdp_level')}")
        # OECD unreachable: both recorded as errors, series untouched
        n = {}
        s = mk(br, bl, "r", "l")
        with mock.patch.object(oecd_turn, "check", return_value=None), mock.patch.object(go.time, "sleep", return_value=None), \
                mock.patch.object(go.requests, "get", side_effect=go.requests.ConnectionError("down")), redirect_stdout(io.StringIO()):
            mod.overlay_gdp(s, n)
        check(all(v["status"] == "error" and "OECD request failed" in v["detail"] for v in n.values()) and set(n) == {"gdp_real", "gdp_level"},
              f"{who}: an unreachable OECD must be recorded for both series: {n}")
        # off its turn: no decision, so nothing recorded
        n = {}
        with mock.patch.object(oecd_turn, "check", side_effect=oecd_turn.NotThisHour("turn")), redirect_stdout(io.StringIO()):
            mod.overlay_gdp(mk(br, bl, "r", "l"), n)
        check(n == {}, f"{who}: a run outside the OECD turn must record nothing: {n}")


@case
def notes_are_carried_forward():
    prev = {"gdp_level": {"status": "refused", "detail": "old reason", "run": "2026-10-27T21:29:12Z"}}
    new = {"gdp_real": {"status": "applied", "detail": "d"}}
    m = go.merge_notes(prev, new, "2026-10-28T09:00:00Z")
    check(m["gdp_level"] == prev["gdp_level"], "a series with no decision this run must keep its previous note")
    check(m["gdp_real"] == {"status": "applied", "detail": "d", "run": "2026-10-28T09:00:00Z"}, f"a new decision must be stamped with the run time: {m['gdp_real']}")
    check(go.merge_notes(prev, {}, "t") == prev and go.merge_notes(prev, None, "t") == prev, "an off-turn run (no decisions) must leave the notes exactly as they were")
    over = go.merge_notes(prev, {"gdp_level": {"status": "applied", "detail": "x"}}, "t2")
    check(over["gdp_level"]["status"] == "applied" and over["gdp_level"]["run"] == "t2", "a new decision replaces the old one for that series")
    check(go.merge_notes(None, {}, "t") == {} and go.merge_notes({}, None, "t") == {}, "no notes at all stays empty")
    check(prev["gdp_level"]["detail"] == "old reason", "merge_notes must not mutate its input")


@case
def fetchers_write_the_notes():
    for fn in ("fetch_za.py", "fetch_ar.py"):
        src = (ROOT / fn).read_text(encoding="utf-8")
        i_init, i_out = src.find("_overlay_notes: dict = {}"), src.find("    out = {")
        i_merge, i_dump = src.find('gdp_overlay.merge_notes(prev_full.get("overlay_notes"), _overlay_notes, now_iso)'), src.find("        json.dump(out, f)")
        check(0 < i_init < i_out, f"{fn}: _overlay_notes must be created before out is built")
        check(0 < i_merge < i_dump and 'out["overlay_notes"] = _notes' in src, f"{fn}: the notes must be merged and stored before the file is written")


@case
def disagreeing_tables_matter_only_where_the_overlay_works():
    """Production, 28 Oct 2026: South Africa's nominal GDP was refused entirely because the OECD's two tables disagree
    by 0.14% in 2010-Q1 (735904.9 against 736905.0). That quarter can never be used. A disagreement blocks the overlay
    only from the start of the validated window (here 2024-Q2) onward, and older ones are reported, not hidden."""
    cand = cand_for(ZA_REAL, OECD_NEW["ZA_REAL"])
    window_start = "2024-Q2"
    gap = lambda p: (cand[p], cand[p] * 1.0014)
    # strict select still refuses, so nothing else can hide a disagreement
    rows = rows_for(EXPECTED_SEL["ZA"]["gdp_real"], cand)
    rows.append(dict(rows[0], OBS_VALUE=str(float(rows[0]["OBS_VALUE"]) * 1.0014)))
    oldest = rows[0]["TIME_PERIOD"]
    try:
        go.select(rows, **EXPECTED_SEL["ZA"]["gdp_real"])
        check(False, "select must stay strict")
    except ValueError:
        pass
    c2, conf = go.select_checked(rows, **EXPECTED_SEL["ZA"]["gdp_real"])
    check(list(conf) == [oldest] and c2[oldest] == min(conf[oldest]), f"select_checked must report the disagreeing quarter and keep the lower copy: {conf}")
    # 1. an OLD disagreement does not block, and is reported
    m, rep = go.overlay(ZA_REAL, c2, conflicts=conf)
    check(rep["applied"] and rep["ignored"] == [oldest], f"an old disagreement must be ignored and reported: {rep}")
    check(m[0] == ZA_REAL[0] and rep["from"] == window_start, "points before the window must be untouched")
    n = {}
    s = mk(ZA_REAL, ZA_LEVEL, "r", "l")
    run_overlay(fetch_za, s, rows + rows_for(EXPECTED_SEL["ZA"]["gdp_level"], cand_for(ZA_LEVEL, OECD_NEW["ZA_LEVEL"])), "ZAF", n)
    check(n["gdp_real"]["status"] == "applied" and "ignored 1 older quarters" in n["gdp_real"]["detail"] and oldest in n["gdp_real"]["detail"],
          f"the note must say how many older quarters were ignored and the earliest: {n.get('gdp_real')}")
    # 2. a disagreement exactly AT the window start, inside it, or in the new quarter refuses
    for per in (window_start, "2025-Q1", "2026-Q2"):
        lo, hi = gap(per)
        m2, rep2 = go.overlay(ZA_REAL, c2, conflicts={per: (lo, hi)})
        check(not rep2["applied"] and per in rep2["reason"] and "two different values" in rep2["reason"] and m2 == ZA_REAL,
              f"a disagreement in {per} must refuse and name it: {rep2}")
    # 3. nothing to report: the report carries an empty list
    m3, rep3 = go.overlay(ZA_REAL, cand_for(ZA_REAL, OECD_NEW["ZA_REAL"]))
    check(rep3["applied"] and rep3["ignored"] == [], f"no disagreements, nothing ignored: {rep3}")


# ---------------------------------------------------------------- v1.9.25: Mexico and South Korea, nominal GDP only
MX_LEVEL = [["2023-Q4", 8162216.2], ["2024-Q1", 8192966.4], ["2024-Q2", 8282881.2], ["2024-Q3", 8509755.6], ["2024-Q4", 8558602.4], ["2025-Q1", 8716280.0], ["2025-Q2", 8810432.3], ["2025-Q3", 8844688.6], ["2025-Q4", 8937704.2], ["2026-Q1", 9008762.6]]
KR_LEVEL = [["2023-Q4", 617070800.0], ["2024-Q1", 635775600.0], ["2024-Q2", 639523000.0], ["2024-Q3", 639304200.0], ["2024-Q4", 649601500.0], ["2025-Q1", 652725700.0], ["2025-Q2", 661714900.0], ["2025-Q3", 670117800.0], ["2025-Q4", 692116300.0], ["2026-Q1", 764882300.0]]


def level_only(level, label):
    return {"gdp_level": {"label": label, "unit": "x", "freq": "quarters", "points": [list(p) for p in level]},
            "gdp_real": {"label": "Real GDP, SA", "unit": "x", "freq": "quarters", "points": [["2026-Q2", 1.0]]}}


@case
def mx_kr_wiring():
    for mod, iso, code, level in ((fetch_mx, "MEX", "MX", MX_LEVEL), (fetch_kr, "KOR", "KR", KR_LEVEL)):
        sel = EXPECTED_SEL[code]["gdp_level"]
        q1 = dict(level)["2026-Q1"]
        cand = {p: v for p, v in level}
        cand["2026-Q2"] = round(q1 * 1.012, 1)
        rows = rows_for(sel, cand, decoys=[(dict(sel, ADJUSTMENT="N"), q1 * 3)])
        s = level_only(level, f"GDP nominal, SA (NGDPSAXDC{code}Q)")
        real_before = [list(p) for p in s["gdp_real"]["points"]]
        notes = {}
        out = run_overlay(mod, s, rows, iso, notes)
        check(s["gdp_level"]["points"][-1] == ["2026-Q2", cand["2026-Q2"]], f"{code}: nominal Q2 not added: {s['gdp_level']['points'][-2:]}")
        check(go.RELABEL in s["gdp_level"]["label"], f"{code}: label not marked as OECD-extended: {s['gdp_level']['label']}")
        check(s["gdp_real"]["points"] == real_before, f"{code}: real GDP must not be touched")
        check(notes.get("gdp_level", {}).get("status") == "applied" and "gdp_real" not in notes, f"{code}: notes {notes}")
        # a level break must be refused and the IFS series kept
        s2 = level_only(level, "l")
        broken = rows_for(sel, {p: v * 1.05 for p, v in cand.items()})
        out2 = run_overlay(mod, s2, broken, iso, {})
        check(s2["gdp_level"]["points"] == [list(p) for p in level] and "WARN" in out2, f"{code}: a 5% break must be refused: {out2}")
        # FRED failed this run: no gdp_level in the output, the overlay must not invent one
        s3 = {"gdp_real": {"label": "r", "unit": "x", "freq": "quarters", "points": [["2026-Q2", 1.0]]}}
        n3 = {}
        out3 = run_overlay(mod, s3, rows, iso, n3)
        check("gdp_level" not in s3, f"{code}: overlay created a series FRED did not return")
        check(n3 == {} and "WARN" not in out3, f"{code}: a series FRED did not return must be skipped quietly, not noted as an error: {n3} {out3!r}")


@case
def mx_kr_off_turn_skips():
    for mod in (fetch_mx, fetch_kr):
        s = level_only(MX_LEVEL, "l")
        buf = io.StringIO()
        with mock.patch.object(oecd_turn, "check", side_effect=oecd_turn.NotThisHour("not this group")), \
                mock.patch.object(go.requests, "get", side_effect=AssertionError("must not call OECD off-turn")), \
                redirect_stdout(buf):
            notes = {"gdp_level": {"status": "applied", "detail": "from the last turn"}}
            mod.overlay_gdp(s, notes)
        check(s["gdp_level"]["points"] == [list(p) for p in MX_LEVEL] and "SKIP" in buf.getvalue() and "WARN" not in buf.getvalue(),
              f"{mod.__name__}: off-turn must SKIP without a request or a warning: {buf.getvalue()!r}")
        check(notes == {"gdp_level": {"status": "applied", "detail": "from the last turn"}},
              f"{mod.__name__}: off-turn must leave the previous notes untouched: {notes}")


@case
def mx_kr_main_wiring():
    import inspect
    for mod, df in ((fetch_mx, "data-mx.json"), (fetch_kr, "data-kr.json")):
        src = inspect.getsource(mod.main)
        fred = src.find("for name, (sid, freq, label, unit, tf, scale) in FRED_SERIES.items():")
        call = src.find('overlay_gdp(out["series"], _overlay_notes)')
        write = src.find(f'with open("{df}", "w") as f:')
        merge = src.find('_notes = gdp_overlay.merge_notes(prev_full.get("overlay_notes"), _overlay_notes, now_iso)')
        dump = src.find("json.dump(out, f)", write)
        check(src.count('overlay_gdp(out["series"], _overlay_notes)') == 1 and -1 < fred < call,
              f"{mod.__name__}: main() must call overlay_gdp once, after the FRED fetch")
        check(-1 < write < merge < dump and 'out["overlay_notes"] = _notes' in src[merge:dump],
              f"{mod.__name__}: main() must save the overlay notes into {df}")


print("test_gdp_overlay:", "FAILED" if fails else "ok", f"({len(fails)} failures)")
sys.exit(1 if fails else 0)
