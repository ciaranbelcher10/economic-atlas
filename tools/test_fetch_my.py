"""Offline tests for fetch_my.py and tools/audit_my.py (no network).

    python3 tools/test_fetch_my.py

Fixtures mirror the OpenDOSM, BIS and BNM shapes seen by
tools/probe_country.py on 6 Oct 2026. Each data-quality rule is tested both
ways: the good case passes and a planted fault is caught.
"""
from __future__ import annotations

import copy, io, json, os, sys, tempfile
from contextlib import redirect_stdout
from pathlib import Path

# Tripwire (v1.7.15): the test must never touch the live data file.
import hashlib as _hl
_LIVE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data-my.json")
def _live_hash():
    return _hl.sha256(open(_LIVE, "rb").read()).hexdigest() if os.path.exists(_LIVE) else None
_LIVE_H0 = _live_hash()

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import fetch_my as F   # noqa: E402
import audit_my as A   # noqa: E402

FAILS = []
N = [0]


def check(ok, msg):
    N[0] += 1
    if not ok:
        FAILS.append(msg)
        print("FAIL ", msg)


# ---------------------------------------------------------------- fixtures
def months(a, b):
    y, m = map(int, a.split("-"))
    out = []
    while f"{y}-{m:02d}" <= b:
        out.append(f"{y}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


# Fixtures end two months / one quarter before today, so the currency rules
# in fetch_my (series too old to show) never make the tests rot.
from datetime import date
_t = date.today()
_e = (_t.year * 12 + _t.month - 1) - 2
END = f"{_e // 12}-{_e % 12 + 1:02d}"
_q = (_t.year * 12 + _t.month - 1) - 4 - ((_t.month - 1) % 3)
QEND = f"{_q // 12}-{_q % 12 + 1:02d}"
MON = months("2015-01", END)
QTRS = [f"{y}-{m:02d}-01" for y in range(2015, _t.year + 1) for m in (1, 4, 7, 10) if f"{y}-{m:02d}" <= QEND]


def cpi_rows():
    rows, ix = [], 110.0
    for i, p in enumerate(MON):
        ix = round(ix * (1.0015 if i % 5 else 1.004), 1)
        rows.append({"date": p + "-01", "index": ix, "division": "overall"})
        rows.append({"date": p + "-01", "index": 150.0, "division": "01"})
    return rows


def gdp_rows(seasonal):
    rows, lvl = [], 280000.0
    for i, d in enumerate(QTRS):
        lvl *= 1.012
        v = lvl * (1.03 if seasonal and i % 4 == 3 else 1.0)
        rows.append({"date": d, "value": round(v, 3), "series": "abs"})
    return rows


def add_growth(rows, sa_qoq):
    ab = [(r["date"], r["value"]) for r in rows if r["series"] == "abs"]
    out = list(rows)
    for i in range(1, len(ab)):
        q = 1.2 if sa_qoq else round((ab[i][1] / ab[i - 1][1] - 1) * 100, 1)
        out.append({"date": ab[i][0], "value": q, "series": "growth_qoq"})
    for i in range(4, len(ab)):
        out.append({"date": ab[i][0], "value": round((ab[i][1] / ab[i - 4][1] - 1) * 100, 1), "series": "growth_yoy"})
    return out


LFS = [{"date": p + "-01", "u_rate": 3.3, "p_rate": 70.5 + (2.9 if p >= "2010-12" else 0), "ep_ratio": 68.1, "lf": 17000.0}
       for p in months("2010-01", END)[:-1]]
LFS_SA = [{k: v for k, v in r.items() if k != "ep_ratio"} for r in LFS]   # the SA table has no ep_ratio
TRADE = ([{"date": p + "-01", "exports": 150e9 + i * 1e8, "imports": 130e9 + i * 1e8, "section": "overall"} for i, p in enumerate(MON[:-1])]
         + [{"date": p + "-01", "exports": 4e9, "imports": 5e9, "section": "0"} for p in MON[:-1]])
BIS_CSV = "TIME_PERIOD,OBS_VALUE\n" + "\n".join(
    f"{p},{3.0 if p < '2004-04' else 2.7 if p < '2005-11' else 2.75}" for p in months("1995-11", END))


class Resp:
    def __init__(self, text="", js=None, code=200):
        self.text, self._js, self.status_code = text, js, code

    def json(self):
        return self._js

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def install(datasets, missing=()):
    F._DOSM_CACHE.clear()
    F.DOSM_PAUSE = 0

    def fake_get(url, timeout=None, headers=None):
        if "data-catalogue" in url:
            ds = url.split("id=")[1]
            if ds in missing or ds not in datasets:
                return Resp(code=404)
            return Resp(js=datasets[ds])
        if "WS_CBPOL" in url:
            return Resp(text=BIS_CSV)
        if "worldbank" in url:
            return Resp(js=[{}, [{"date": str(y), "value": 1.0 + y % 3} for y in range(2000, 2025)]])
        raise RuntimeError("unexpected URL " + url)
    F.requests.get = fake_get
    F.imf_weo.fetch = lambda iso3, ind: [[str(y), 60.0 if ind == F.imf_weo.DEBT else -3.5] for y in range(1990, 2025)]


def base_sets(seasonal=True, sa_table=True, cpi_table=False):
    real = add_growth(gdp_rows(seasonal), sa_qoq=False)
    sets = {"cpi_headline": cpi_rows(), "gdp_qtr_nominal": add_growth(gdp_rows(seasonal), False), "gdp_qtr_real": real,
            "lfs_month": LFS, "lfs_month_sa": LFS_SA, "trade_sitc_1d": TRADE}
    if sa_table:
        sets["gdp_qtr_real_sa"] = gdp_rows(False)          # levels only, as OpenDOSM serves it
    if cpi_table:
        ix = [(r["date"], r["index"]) for r in sets["cpi_headline"] if r["division"] == "overall"]
        rows = []
        for i in range(12, len(ix)):
            rows.append({"date": ix[i][0], "division": "overall",
                         "inflation_yoy": round((ix[i][1] / ix[i - 12][1] - 1) * 100, 1),
                         "inflation_mom": round((ix[i][1] / ix[i - 1][1] - 1) * 100, 1)})
        sets["cpi_headline_inflation"] = rows
    return sets


# ---------------------------------------------------------------- helpers
check(F.quarter_of("2026-04-01") == "2026-Q2", "quarter_of maps April to Q2")
try:
    F.quarter_of("2026-05-01"); check(False, "quarter_of rejects a mid-quarter date")
except ValueError:
    check(True, "")
check(F.pct_change([["a", 100.0], ["b", 101.26]], 1) == [["b", 1.3]], "pct_change rounds to DOSM's one decimal")

# q/q basis: raw-level changes are recognised as not seasonally adjusted
lvl = [[f"2025-Q{i}", 100.0 * (1.02 ** i) * (1.05 if i == 4 else 1)] for i in range(1, 5)] + \
      [[f"2026-Q{i}", 120.0 * (1.02 ** i) * (1.05 if i == 4 else 1)] for i in range(1, 4)]
raw = [[p, v] for p, v in F.pct_change(lvl, 1)]
check(F.qoq_basis(raw, lvl) == "nsa", "q/q equal to the raw-level change is detected as NOT seasonally adjusted")
check(F.qoq_basis([[p, 1.0] for p, _ in raw], lvl) == "sa", "q/q unlike the raw-level change is treated as adjusted")

# ---------------------------------------------------------------- fetchers
install(base_sets())
with redirect_stdout(io.StringIO()):
    yoy, mom, how = F.fetch_cpi_rates()
check(how == "derived", "CPI falls back to deriving from DOSM's index when the rates table is absent")
check(all(round(v, 1) == v for _, v in yoy + mom), "derived CPI rates carry one decimal, like DOSM's")
install(base_sets(cpi_table=True))
with redirect_stdout(io.StringIO()):
    _, _, how = F.fetch_cpi_rates()
check(how == "published", "CPI uses DOSM's published rates when the table is served")

install(base_sets())
with redirect_stdout(io.StringIO()):
    pr = F.fetch_policy_rate()
check(pr[0][0] == "2004-05" and all(p >= "2004-05" for p, _ in pr), "policy rate cut at May 2004: no spliced earlier measure")

with redirect_stdout(io.StringIO()):
    tr = F.fetch_trade()
check(tr["exports"][0][1] == 150000.0, "trade converted from ringgit to RM millions")
check(all(abs(dict(tr["exports"])[p] - dict(tr["imports"])[p] - v) < 0.11 for p, v in tr["trade_balance"]),
      "trade balance is exports minus imports")
check(len(tr["exports"]) == len(MON) - 1, "trade uses the 'overall' section only")

with redirect_stdout(io.StringIO()):
    lab, basis = F.fetch_labour()
check(basis == {"unemployment": "sa", "participation": "sa", "employment": "nsa"},
      f"unemployment and participation adjusted, employment ratio unadjusted (not in the SA table): {basis}")
check(all(p >= "2011-01" for v in lab.values() for p, _ in v), "labour series start after the Dec 2010 survey break")
install(base_sets(), missing=("lfs_month_sa",))
with redirect_stdout(io.StringIO()):
    lab, basis = F.fetch_labour()
check(set(basis.values()) == {"nsa"} and "not seasonally adjusted" in F.LABOUR_LABEL[("unemployment", basis["unemployment"])],
      "without the SA table every label says not seasonally adjusted")
install(base_sets())
with redirect_stdout(io.StringIO()):
    g, b = F.fetch_gdp_growth()
lv = F.pts_from(base_sets()["gdp_qtr_real_sa"], "value", F.quarter_of, series="abs")
check(b == "sa_derived" and g == F.pct_change(lv, 1), "q/q computed from DOSM's seasonally adjusted levels")

install(base_sets(seasonal=True, sa_table=False))
with redirect_stdout(io.StringIO()):
    g, b = F.fetch_gdp_growth()
check(b == "nsa", "q/q from gdp_qtr_real that matches the raw level is labelled not seasonally adjusted")

# ---------------------------------------------------------------- main + audit (offline)
tmp = tempfile.mkdtemp()
cwd = os.getcwd()
os.chdir(tmp)
try:
    install(base_sets(cpi_table=True))
    os.environ.pop("FRED_API_KEY", None)
    F.series_guard.apply_guard = lambda *a, **k: None
    with redirect_stdout(io.StringIO()) as buf:
        rc = F.main()
    d = json.load(open("data-my.json"))
finally:
    os.chdir(cwd)
check(rc == 0, "fetch_my.main writes the file")
want = set(A.EXPECT)
check(set(d["series"]) == want, f"served keys exactly the expected 17: extra {set(d['series']) - want}, missing {want - set(d['series'])}")
check("bond_yield_10y" not in d["series"] and "business_confidence" not in d["series"], "unconfirmed series not served")
check(d["fx_to_usd"]["pair"] == "MYR/USD" and d["fx_to_usd"]["direction"] == "divide", "fx block shape")
check(all("\u2014" not in v["label"] for v in d["series"].values()), "no em dashes in labels")


def audit(dd):
    A.RESULTS.clear()
    p = os.path.join(tmp, "a.json")
    json.dump(dd, open(p, "w"))
    with redirect_stdout(io.StringIO()):
        rc = A.main(["audit_my.py", "--offline", p])
    return rc, [r for r in A.RESULTS if r[0] == "FAIL"]


# the fixture's FX is the World Bank stand-in (rate 2.0); give it a plausible ringgit rate for the audit
good = copy.deepcopy(d)
good["fx_to_usd"].update(rate=4.2, history=[[p, 4.2] for p in MON])
rc, fails = audit(good)
check(rc == 0, f"audit passes the good file: {fails[:3]}")

planted = {
    "wrong unit": lambda x: x["series"]["exports"].update(unit="MYRbn"),
    "spliced OPR": lambda x: x["series"]["policy_rate"]["points"].insert(0, ["2004-04", 2.7]),
    "two-decimal CPI": lambda x: x["series"]["cpi"]["points"][-1].__setitem__(1, 1.23),
    "bond served": lambda x: x["series"].__setitem__("bond_yield_10y", x["series"]["policy_rate"]),
    "fraction not percent": lambda x: x["series"]["unemployment"]["points"][-1].__setitem__(1, 0.033),
    "trade balance mismatch": lambda x: x["series"]["trade_balance"]["points"][-1].__setitem__(1, 1.0),
    "missing series": lambda x: x["series"].pop("participation"),
    "gap in series": lambda x: x["series"]["cpi"]["points"].pop(-5),
    "unexplained CPI jump": lambda x: x["series"]["cpi"]["points"][-3].__setitem__(1, 9.9),
    "em dash in label": lambda x: x["series"]["cpi"].update(label="CPI \u2014 all items"),
}
for name, fault in planted.items():
    bad = copy.deepcopy(good)
    fault(bad)
    rc, fails = audit(bad)
    check(rc == 1 and fails, f"audit catches planted fault: {name}")

check(_live_hash() == _LIVE_H0, "live data-my.json untouched by this test")
print(f"{N[0]} checks, {len(FAILS)} failures")
sys.exit(1 if FAILS else 0)
