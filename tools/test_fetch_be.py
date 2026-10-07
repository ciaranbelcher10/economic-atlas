"""Offline tests for fetch_be.py (v1.7.16). Every rule tested both ways, with
planted faults. Run: python3 tools/test_fetch_be.py"""
from __future__ import annotations

import copy, io, json, os, sys, tempfile
from contextlib import redirect_stdout

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

# Tripwire: the test must never touch the live data file.
import hashlib as _hl
_LIVE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data-be.json")
def _live_hash():
    return _hl.sha256(open(_LIVE, "rb").read()).hexdigest() if os.path.exists(_LIVE) else None
_LIVE_H0 = _live_hash()

import fetch_be as F  # noqa: E402

N, FAILS = [0], []
def check(ok, msg):
    N[0] += 1
    if not ok:
        FAILS.append(msg); print("FAIL ", msg)

def months(a, b):
    y, m = int(a[:4]), int(a[5:]); out = []
    while f"{y}-{m:02d}" <= b:
        out.append(f"{y}-{m:02d}"); m += 1
        if m == 13: y, m = y + 1, 1
    return out

M = months("1999-01", "2026-08")
Q = [f"{y}-Q{q}" for y in range(1995, 2027) for q in range(1, 5)][:-2]   # to 2026-Q2
SEEN = []

class Resp:
    def __init__(self, js=None, code=200): self._js, self.status_code, self.text = js, code, ""
    def json(self): return self._js
    def raise_for_status(self):
        if self.status_code >= 400: raise RuntimeError(f"HTTP {self.status_code}")

def fred_obs(sid):
    if sid == "ECBDFR": return [{"date": f"{p}-15", "value": "2.5"} for p in months("1999-01", "2026-10")]
    if sid == "DEXUSEU": return [{"date": f"{p}-15", "value": "1.10"} for p in M] + [{"date": "2026-10-02", "value": "1.1259"}]
    if sid.startswith("CP0000"): return [{"date": f"{p}-01", "value": str(100 + i * 0.2)} for i, p in enumerate(M)]
    if sid.endswith("Q156S"): return [{"date": f"{p[:4]}-{(int(p[-1]) - 1) * 3 + 1:02d}-01", "value": "65.0"} for p in Q[16:]]
    if sid.startswith("XTNTVA01"): return [{"date": f"{p}-01", "value": "1000000000"} for p in M]
    return [{"date": f"{p}-01", "value": "3.0"} for p in M]

DOWN = set()
def install():
    def fake_get(url, timeout=None, headers=None, **kw):
        SEEN.append(url)
        for tag in DOWN:
            if tag in url: return Resp(code=503)
        if "stlouisfed" in url:
            sid = url.split("series_id=")[1].split("&")[0]
            return Resp(js={"observations": fred_obs(sid)})
        raise RuntimeError("unexpected URL " + url)
    F.requests.get = fake_get
    F.eurostat_gdp.fetch_levels = lambda geo, cur, lab: {} if "eurostat-gdp" in DOWN else {
        "gdp_level": {"label": "GDP nominal, current prices, SA (Eurostat namq_10_gdp, CP_MEUR)", "unit": "\u20acm", "freq": "quarters",
                      "points": [[p, 100000.0 + i * 500] for i, p in enumerate(Q)]},
        "gdp_real": {"label": "Real GDP, chain-linked volume, SA (Eurostat namq_10_gdp, CLV20_MEUR)", "unit": "\u20acm", "freq": "quarters",
                     "points": [[p, 90000.0 + i * 300] for i, p in enumerate(Q)]}}
    F.eurostat_unemp.fetch = lambda geo: {} if "eurostat-unemp" in DOWN else {
        "unemployment": {"label": "Unemployment rate, SA (Eurostat une_rt_m)", "unit": "%", "freq": "months",
                         "points": [[p, 5.9] for p in M]}}
    F.fetch_eurostat_trade_balance_world = lambda: None if "eurostat-trade" in DOWN else [[p, 6479.300000000003] for p in M[-120:]]
    F.fetch_oecd_bci = lambda: [[p, 99.2] for p in M]
    F.fetch_eurostat_govfinance = lambda item: [[str(y), 103.9 if item == "GD" else -4.4] for y in range(2000, 2026)]
    F.series_guard.apply_guard = lambda *a, **k: None

def run(prev=None, key="test"):
    tmp = tempfile.mkdtemp(); cwd = os.getcwd()
    try:
        os.chdir(tmp)
        if prev: json.dump(prev, open("data-be.json", "w"))
        if key: os.environ["FRED_API_KEY"] = key
        else: os.environ.pop("FRED_API_KEY", None)
        SEEN.clear()
        with redirect_stdout(io.StringIO()) as buf:
            rc = F.main()
        return rc, json.load(open("data-be.json")), buf.getvalue()
    finally:
        os.chdir(cwd)

os.environ["OECD_TURN_GROUP"] = "ALL"
install()
rc, d, log = run()
s = d["series"]
WANT = {"gdp_level", "gdp_real", "gdp_growth", "unemployment", "ecb_rate", "participation_rate", "employment_rate",
        "bond_yield_10y", "cpi", "cpi_mom", "trade_balance", "business_confidence", "debt_gdp", "deficit"}
check(rc == 0, "clean run returns 0")
check(set(s) == WANT, f"serves exactly the eurozone key set: extra {set(s) - WANT}, missing {WANT - set(s)}")
check("policy_rate" not in s and "current_account" not in s and "fdi" not in s, "no own policy rate, CA or FDI served")
fred_ids = [u.split("series_id=")[1].split("&")[0] for u in SEEN if "stlouisfed" in u]
check(all(("AT" not in x[5:]) for x in fred_ids if x.startswith(("CP0000", "IRLT", "LRAC", "LREM", "LRHU"))),
      f"no Austrian series ids left: {fred_ids}")
check({"CP0000BEM086NEST", "IRLTLT01BEM156N", "LRAC64TTBEQ156S", "LREM64TTBEQ156S", "ECBDFR", "DEXUSEU"} <= set(fred_ids),
      f"asks FRED for the Belgian ids: {fred_ids}")
check("CPMNACSCAB1GQBE" not in fred_ids and "LRHUTTTTBEM156S" not in fred_ids, "Eurostat GDP/unemployment used, FRED copies not fetched")
check(all("BEM086" in s[k]["label"] for k in ("cpi", "cpi_mom")), "HICP labels name the Belgian series")
check(s["ecb_rate"]["points"][-1] == ["2026-10", 2.5], f"ECB rate current: {s['ecb_rate']['points'][-1]}")
check(s["gdp_growth"]["freq"] == "quarters" and abs(s["gdp_growth"]["points"][-1][1] - round((90000 + 125 * 300) / (90000 + 124 * 300) * 100 - 100, 2)) < 0.01,
      f"gdp_growth derived q/q from real levels: {s['gdp_growth']['points'][-1]}")
check(s["trade_balance"]["points"][-1][1] == 6479.3, "trade balance rounded to 1dp (no float noise)")
check("Eurostat" in s["trade_balance"]["label"] and s["trade_balance"]["unit"] == "\u20acm", "trade from Eurostat, in euro")
fx = d["fx_to_usd"]
check(fx["pair"] == "EUR/USD" and fx["direction"] == "multiply" and fx["rate"] == 1.1259, f"fx block: {fx['pair']} {fx['rate']}")
check(abs(s["cpi"]["points"][-1][1] - round(((100 + (len(M) - 1) * 0.2) / (100 + (len(M) - 13) * 0.2) - 1) * 100, 2)) < 0.01,
      f"cpi is YoY of the index: {s['cpi']['points'][-1]}")

# Eurostat GDP down: falls back to the Belgian FRED copies, not Austria's
DOWN.add("eurostat-gdp"); install()
rc2, d2, _ = run()
fred_ids2 = [u.split("series_id=")[1].split("&")[0] for u in SEEN if "stlouisfed" in u]
check("CPMNACSCAB1GQBE" in fred_ids2 and "CLVMNACSCAB1GQBE" in fred_ids2, f"GDP fallback uses Belgian FRED ids: {fred_ids2}")
DOWN.clear()
# Eurostat unemployment down: FRED LRHUTTTTBEM156S
DOWN.add("eurostat-unemp"); install()
_, d3, _ = run()
check("LRHUTTTTBEM156S" in d3["series"]["unemployment"]["label"], "unemployment fallback is the Belgian FRED series")
DOWN.clear()
# Eurostat trade down: FRED fallback converted to euro
DOWN.add("eurostat-trade"); install()
_, d4, log4 = run()
tb = d4["series"]["trade_balance"]
check("XTNTVA01BEM667S" in tb["label"] and tb["unit"] == "\u20acm", f"trade fallback is Belgian and converted to euro: {tb['label']}")
DOWN.clear()
# FRED down entirely: FRED series absent this run, Eurostat ones kept
DOWN.add("stlouisfed"); install()
rc5, d5, log5 = run()
check(rc5 == 0 and "gdp_level" in d5["series"] and "cpi" not in d5["series"], "FRED outage: Eurostat series still written")
DOWN.clear(); install()
# no key at all: no FRED calls, page still writes
rc6, d6, _ = run(key=None)
check(rc6 == 0 and not any("stlouisfed" in u for u in SEEN), "no key: no FRED calls, still writes")
# previous fx carried over when FX fails
DOWN.add("DEXUSEU"); install()
_, d7, _ = run(prev=d)
check(d7.get("fx_to_usd") == d["fx_to_usd"], "fx carried over from the previous file when FRED FX fails")
DOWN.clear(); install()

# audit: clean synthetic file passes structure; planted faults are caught
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
import audit_be as A  # noqa: E402
def audit(x):
    A.RESULTS.clear()
    with redirect_stdout(io.StringIO()):
        A.structure_and_plausibility(x)
    return [r for r in A.RESULTS if r[0] == "FAIL"]
base = copy.deepcopy(d)
base["series"]["participation_rate"]["points"] = [[p, 65.0] for p in Q[16:]]
check(not audit(base), f"clean file passes the audit: {audit(base)}")
for name, plant in {
    "policy_rate served": lambda x: x["series"].__setitem__("policy_rate", x["series"]["ecb_rate"]),
    "ECB off the 5bp grid": lambda x: x["series"]["ecb_rate"]["points"][-1].__setitem__(1, 2.53),
    "stale ECB rate": lambda x: x["series"]["ecb_rate"].update(points=x["series"]["ecb_rate"]["points"][:-6]),
    "FX upside down": lambda x: x["fx_to_usd"].update(rate=round(1 / 1.1259, 4),
                                                       history=[[p, round(1 / v, 4)] for p, v in x["fx_to_usd"]["history"]]),
    "FX latest out of line with history": lambda x: x["fx_to_usd"].update(rate=0.888),
    "Austrian label": lambda x: x["series"]["cpi"].update(label="HICP, all items, YoY (Austria)"),
    "GDP quarters disagree": lambda x: x["series"]["gdp_real"]["points"].pop(),
    "unnamed CPI jump": lambda x: x["series"]["cpi"]["points"][-1].__setitem__(1, 14.0),
    "wrong unit": lambda x: x["series"]["trade_balance"].update(unit="$m"),
}.items():
    x = copy.deepcopy(base); plant(x)
    check(bool(audit(x)), f"audit catches: {name}")

check(F.__doc__ and "Belgium" in F.__doc__ and "Austria" in F.__doc__, "docstring describes Belgium and its template")
import oecd_turn  # noqa: E402
check(oecd_turn.GROUPS.get("fetch_be.py") == "A", "fetch_be.py mapped to oecd_turn group A")
check(_live_hash() == _LIVE_H0, "live data-be.json untouched by this test")
print(f"{N[0]} checks, {len(FAILS)} failures")
sys.exit(1 if FAILS else 0)
