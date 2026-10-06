"""Offline tests for fetch_nz.py and tools/audit_nz.py (no network).

    python3 tools/test_fetch_nz.py

Fixtures mirror the OECD, BIS, IMF, World Bank and FRED shapes seen by
tools/probe_country.py on 6 Oct 2026. Each rule is tested both ways.
"""
from __future__ import annotations

import copy, io, json, os, sys, tempfile
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import fetch_nz as F   # noqa: E402
import audit_nz as A   # noqa: E402

FAILS, N = [], [0]


def check(ok, msg):
    N[0] += 1
    if not ok:
        FAILS.append(msg)
        print("FAIL ", msg)


# ---------------------------------------------------------------- fixtures
_t = date.today()
_m = _t.year * 12 + _t.month - 1 - 2
END_M = f"{_m // 12}-{_m % 12 + 1:02d}"
_q = (_t.year * 12 + _t.month - 1 - 4) // 3
END_Q = f"{_q // 4}-Q{_q % 4 + 1}"


def months(a, b):
    y, m = map(int, a.split("-")); out = []
    while f"{y}-{m:02d}" <= b:
        out.append(f"{y}-{m:02d}"); m += 1
        if m == 13: y, m = y + 1, 1
    return out


def quarters(a, b):
    y, q = int(a[:4]), int(a[-1]); out = []
    while (y, q) <= (int(b[:4]), int(b[-1])):
        out.append(f"{y}-Q{q}"); q += 1
        if q == 5: y, q = y + 1, 1
    return out


Q = quarters("1987-Q2", END_Q)
M = months("1985-01", END_M)


def csv_text(rows):
    cols = sorted({k for r in rows for k in r})
    lines = [",".join(cols)] + [",".join(str(r.get(c, "")) for c in cols) for r in rows]
    return "\n".join(lines)


def qna_rows():
    rows = []
    real, nom = 20000.0, 15000.0
    for i, p in enumerate(Q):
        real *= 1.006; nom *= 1.012
        base = dict(TRANSACTION="B1GQ", TIME_PERIOD=p)
        rows += [dict(base, TABLE_IDENTIFIER="T0102", PRICE_BASE="V", ADJUSTMENT="Y", TRANSFORMATION="N", UNIT_MEASURE="XDC", OBS_VALUE=round(nom, 1)),
                 dict(base, TABLE_IDENTIFIER="T0102", PRICE_BASE="V", ADJUSTMENT="N", TRANSFORMATION="N", UNIT_MEASURE="XDC", OBS_VALUE=1),  # distractor
                 dict(base, TABLE_IDENTIFIER="T0101", PRICE_BASE="L", ADJUSTMENT="Y", TRANSFORMATION="N", UNIT_MEASURE="XDC", OBS_VALUE=round(real, 1)),
                 dict(base, TABLE_IDENTIFIER="T0102", PRICE_BASE="L", ADJUSTMENT="Y", TRANSFORMATION="N", UNIT_MEASURE="XDC", OBS_VALUE=2)]  # distractor
    lv = [r for r in rows if r["TABLE_IDENTIFIER"] == "T0101" and r["TRANSFORMATION"] == "N"]
    for i in range(1, len(lv)):
        g = round((lv[i]["OBS_VALUE"] / lv[i - 1]["OBS_VALUE"] - 1) * 100, 3)
        rows.append(dict(TRANSACTION="B1GQ", TIME_PERIOD=lv[i]["TIME_PERIOD"], TABLE_IDENTIFIER="T0101", PRICE_BASE="L",
                         ADJUSTMENT="Y", TRANSFORMATION="G1", UNIT_MEASURE="PC", OBS_VALUE=g))
    for i in range(4, len(lv)):
        g = round((lv[i]["OBS_VALUE"] / lv[i - 4]["OBS_VALUE"] - 1) * 100, 3)
        rows.append(dict(TRANSACTION="B1GQ", TIME_PERIOD=lv[i]["TIME_PERIOD"], TABLE_IDENTIFIER="T0101", PRICE_BASE="L",
                         ADJUSTMENT="Y", TRANSFORMATION="GY", UNIT_MEASURE="PC", OBS_VALUE=g))
    return rows


LFS = [dict(MEASURE="UNE_LF_M", ADJUSTMENT=a, SEX="_T", AGE="Y_GE15", FREQ="Q", TIME_PERIOD=p, OBS_VALUE=v)
       for p in Q for a, v in (("Y", 4.5), ("N", 9.9))]
FIN = [dict(MEASURE=m, TIME_PERIOD=p, OBS_VALUE=v) for p in M for m, v in (("IRLT", 5.0), ("IR3TIB", 3.0))]
BCI = [dict(MEASURE=m, TIME_PERIOD=p, OBS_VALUE=v) for p in M for m, v in (("BCICP", 100.2), ("CCICP", 97.0))]
BIS = "TIME_PERIOD,OBS_VALUE\n" + "\n".join(f"{p},{9.0 if p < '1999-03' else 2.5}" for p in M)
ITG = csv_text([dict(INDICATOR=i, VALUATION=v, UNIT="USD", TIME_PERIOD=p.replace("-", "-M"), OBS_VALUE=x)
                for p in months("1995-01", END_M) for i, v, x in (("XG", "FOB", 3.0e9), ("MG", "CIF", 3.5e9))])
FX = {"observations": [{"date": p + "-28", "value": "0.6000"} for p in months("1971-01", END_M)]}
CPI_INDEX = []
_ix = 50.0
for i, p in enumerate(Q):
    _ix *= 1.006 if i % 3 else 1.011
    CPI_INDEX.append([p, round(_ix, 3)])


class Resp:
    def __init__(self, text="", js=None, code=200):
        self.text, self._js, self.status_code = text, js, code

    def json(self):
        return self._js

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def install():
    F.OECD_PAUSE = 0
    F._QNA.clear()

    def fake_get(url, timeout=None, headers=None):
        if "DF_QNA" in url: return Resp(csv_text(qna_rows()))
        if "DF_IALFS" in url: return Resp(csv_text(LFS))
        if "DF_FINMARK" in url: return Resp(csv_text(FIN))
        if "DF_CLI" in url: return Resp(csv_text(BCI))
        if "WS_CBPOL" in url: return Resp(BIS)
        if "ITG" in url: return Resp(ITG)
        if "worldbank" in url: return Resp(js=[{}, [{"date": str(y), "value": 2.0} for y in range(1990, 2025)]])
        if "stlouisfed" in url: return Resp(js=FX)
        raise RuntimeError("unexpected URL " + url)
    F.requests.get = fake_get
    F.oecd_prices.fetch_cpi_index = lambda areas, freq, label="": list(CPI_INDEX)
    F.imf_weo.fetch = lambda iso3, ind: [[str(y), 45.0 if ind == F.imf_weo.DEBT else -3.0] for y in range(1985, 2025)]
    F.series_guard.apply_guard = lambda *a, **k: None


# ---------------------------------------------------------------- unit checks
os.environ["OECD_TURN_GROUP"] = "ALL"
install()
with redirect_stdout(io.StringIO()):
    lvl, real = F.fetch_gdp_level(), F.fetch_gdp_real()
    g1, gy = F.fetch_gdp_rate("G1"), F.fetch_gdp_rate("GY")
    pr = F.fetch_policy_rate()
    yoy, qoq = F.fetch_cpi()
    une = F.fetch_unemployment()
check(lvl[0][1] != 1 and real[0][1] != 2, "QNA picks the SA current-price T0102 and SA volume T0101 series, not distractors")
check(all(v == 4.5 for _, v in une), "unemployment is the seasonally adjusted series")
check(pr[0][0] == "1999-04" and all(p >= "1999-04" for p, _ in pr), "OCR starts April 1999: no spliced overnight cash rate")
check(all(round(v, 1) == v for _, v in yoy + qoq), "CPI rates at Stats NZ's one decimal place")
check(yoy[0][0] == Q[4], "annual CPI rate starts four quarters in")
check(F.usd_to_nzd([["2026-01", 600.0]], {"2026-01": 0.6}, 0.6) == [["2026-01", 1000.0]],
      "US$ to NZ$ divides by US$ per NZ$")

# off-turn: OECD series skipped (not failed), others kept. oecd_turn finds
# the script's group from sys.argv[0], so run as fetch_nz.py would.
sys.argv[0] = "fetch_nz.py"
os.environ["OECD_TURN_GROUP"] = "A"
install()
tmp = tempfile.mkdtemp(); cwd = os.getcwd(); os.chdir(tmp)
os.environ["FRED_API_KEY"] = "x"
try:
    with redirect_stdout(io.StringIO()) as buf:
        F.main()
    off = json.load(open("data-nz.json"))
finally:
    os.chdir(cwd)
log = buf.getvalue()
check("SKIP  gdp_level" in log and "FAIL  gdp_level" not in log, "off-turn OECD series are SKIPPED, not failures")
check("policy_rate" in off["series"] and "gdp_level" not in off["series"], "off-turn: BIS kept, OECD left for the guard")

# full run
os.environ["OECD_TURN_GROUP"] = "ALL"
install()
tmp = tempfile.mkdtemp(); os.chdir(tmp)
try:
    with redirect_stdout(io.StringIO()):
        rc = F.main()
    d = json.load(open("data-nz.json"))
    del os.environ["FRED_API_KEY"]
    os.remove("data-nz.json")
    with redirect_stdout(io.StringIO()):
        F.main()
    nokey = json.load(open("data-nz.json"))
finally:
    os.chdir(cwd)
want = set(A.EXPECT)
check(rc == 0 and set(d["series"]) == want, f"full run serves exactly the expected 17: {set(d['series']) ^ want}")
check(d["fx_to_usd"]["pair"] == "NZD/USD" and d["fx_to_usd"]["direction"] == "multiply", "fx block: US$ per NZ$, multiply")
check(d["series"]["exports"]["points"][-1][1] == 5000.0, "exports US$3.0bn at 0.60 -> NZ$5,000m")
check(not any(k in nokey["series"] for k in ("exports", "imports", "trade_balance")),
      "no exchange rate: trade left out rather than converted at a wrong rate")


def audit(dd):
    A.RESULTS.clear()
    p = os.path.join(tmp, "a.json")
    json.dump(dd, open(p, "w"))
    with redirect_stdout(io.StringIO()):
        rc = A.main(["audit_nz.py", "--offline", p])
    return rc, [r for r in A.RESULTS if r[0] == "FAIL"]


rc, fails = audit(d)
check(rc == 0, f"audit passes the good file: {fails[:3]}")
planted = {
    "fx quoted the wrong way": lambda x: x["fx_to_usd"].update(rate=1.72, direction="divide"),
    "spliced OCR": lambda x: x["series"]["policy_rate"]["points"].insert(0, ["1999-03", 4.5]),
    "monthly CPI served": lambda x: x["series"].__setitem__("cpi_mom", x["series"]["cpi_qoq"]),
    "two-decimal CPI": lambda x: x["series"]["cpi"]["points"][-1].__setitem__(1, 2.55),
    "wrong unit": lambda x: x["series"]["exports"].update(unit="$m"),
    "OCR off the 25bp grid": lambda x: x["series"]["policy_rate"]["points"][-1].__setitem__(1, 2.6),
    "fraction not percent": lambda x: x["series"]["unemployment"]["points"][-1].__setitem__(1, 0.045),
    "trade balance mismatch": lambda x: x["series"]["trade_balance"]["points"][-1].__setitem__(1, 1.0),
    "gap in series": lambda x: x["series"]["cpi"]["points"].pop(-5),
}
for name, fault in planted.items():
    bad = copy.deepcopy(d)
    fault(bad)
    rc, fails = audit(bad)
    check(rc == 1 and fails, f"audit catches planted fault: {name}")

print(f"{N[0]} checks, {len(FAILS)} failures")
sys.exit(1 if FAILS else 0)
