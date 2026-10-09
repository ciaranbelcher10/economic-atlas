"""Offline tests for fetch_hu.py and tools/audit_hu.py (v1.7.34). Every rule
tested both ways, with planted faults. Run: python3 tools/test_fetch_cz.py"""
from __future__ import annotations

import copy, io, json, os, sys, tempfile
from contextlib import redirect_stdout

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

# Built v1.7.34 from tools/test_fetch_cz.py with Hungary-shaped fixtures.
# Tripwire: the test must never touch the live data file.
import hashlib as _hl
_LIVE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data-hu.json")
def _live_hash():
    return _hl.sha256(open(_LIVE, "rb").read()).hexdigest() if os.path.exists(_LIVE) else None
_LIVE_H0 = _live_hash()

import fetch_hu as F  # noqa: E402
import ecb_exr  # noqa: E402
_REAL_FETCH_MONTHLY = ecb_exr.fetch_monthly

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

M = months("1996-01", "2026-08")
Q = [f"{y}-Q{q}" for y in range(1996, 2027) for q in range(1, 5)][:-2]   # to 2026-Q2
TM = months("2015-01", "2026-07")                                          # Eurostat trade months
SEEN = []

class Resp:
    def __init__(self, js=None, code=200, text=""): self._js, self.status_code, self.text = js, code, text
    def json(self): return self._js
    def raise_for_status(self):
        if self.status_code >= 400: raise RuntimeError(f"HTTP {self.status_code}")

def fred_obs(sid):
    if sid.startswith("CP0000"): return [{"date": f"{p}-01", "value": str(100 + i * 0.2)} for i, p in enumerate(M)]
    if sid.endswith("Q156S"): return [{"date": f"{p[:4]}-{(int(p[-1]) - 1) * 3 + 1:02d}-01", "value": "72.0"} for p in Q[8:]]
    if sid.startswith("CPMNAC"): return [{"date": f"{p[:4]}-{(int(p[-1]) - 1) * 3 + 1:02d}-01", "value": "20000000"} for p in Q]
    if sid.startswith("CLVMNAC"): return [{"date": f"{p[:4]}-{(int(p[-1]) - 1) * 3 + 1:02d}-01", "value": "16000000"} for p in Q]
    if sid == "IRLTLT01HUM156N": return [{"date": f"{p}-01", "value": "4.2"} for p in months("2000-04", "2026-08")]
    return [{"date": f"{p}-01", "value": "3.0"} for p in M]

BIS_MONTHLY = [[p, 15.0 if p < "2001-07" else 3.75] for p in months("1995-12", "2026-08")]
def bis_csv(rows):
    return "TIME_PERIOD,OBS_VALUE\n" + "".join(f"{p},{v}\n" for p, v in rows)

WB = {"PA.NUS.FCRF": [[str(y), 300.0 + (y % 7) * 5] for y in range(1993, 2026)],
      "BX.KLT.DINV.WD.GD.ZS": [[str(y), 2.7] for y in range(1993, 2026)],
      "BN.CAB.XOKA.GD.ZS": [[str(y), 0.6] for y in range(1993, 2026)]}

DOWN, BIS_OVERRIDE = set(), {}
RATES = {p: 390.0 for p in months("1999-01", "2026-07")}
def install():
    def fake_get(url, timeout=None, headers=None, **kw):
        SEEN.append(url)
        for tag in DOWN:
            if tag in url: return Resp(code=503)
        if "stlouisfed" in url:
            sid = url.split("series_id=")[1].split("&")[0]
            return Resp(js={"observations": fred_obs(sid)})
        if "WS_CBPOL/1.0/M.HU" in url:
            return Resp(text=bis_csv(BIS_OVERRIDE.get("rows", BIS_MONTHLY)))
        if "WS_CBPOL/1.0/D.HU" in url:
            return Resp(text="TIME_PERIOD,OBS_VALUE\n2026-08-31,3.75\n2026-09-30,3.75\n2026-10-07,3.5\n")
        if "worldbank" in url:
            code = url.split("/indicator/")[1].split("?")[0]
            return Resp(js=[{}, [{"date": y, "value": v} for y, v in WB[code]]])
        raise RuntimeError("unexpected URL " + url)
    F.requests.get = fake_get
    F.eurostat_gdp.fetch_levels = lambda geo, cur, lab: {} if "eurostat-gdp" in DOWN else {
        "gdp_level": {"label": f"GDP nominal, current prices, SA (Eurostat namq_10_gdp, CP_{cur})", "unit": lab, "freq": "quarters",
                      "points": [[p, 4000000.0 + i * 150000] for i, p in enumerate(Q)]},
        "gdp_real": {"label": f"Real GDP, chain-linked volume, SA (Eurostat namq_10_gdp, CLV20_{cur})", "unit": lab, "freq": "quarters",
                     "points": [[p, 9000000.0 + i * 60000] for i, p in enumerate(Q)]}}
    F.eurostat_unemp.fetch = lambda geo: {} if "eurostat-unemp" in DOWN else {
        "unemployment": {"label": "Unemployment rate, SA (Eurostat une_rt_m)", "unit": "%", "freq": "months",
                         "points": [[p, 3.2] for p in M[24:]]}}
    F.ecb_irs.fetch = lambda cc, cur: {} if "ecb-irs" in DOWN else {
        "bond_yield_10y": {"label": f"10-year government bond yield, monthly average (ECB IRS M.{cc}.L.L40.CI.0000.{cur}.N.Z)",
                           "unit": "%", "freq": "months", "points": [[p, 4.9] for p in months("2000-04", "2026-09")]}}
    F.inflation_sources.fetch_national_cpi = lambda area: None if "oecd-cpi" in DOWN else {
        "label": "CPI, national definition, all items, YoY (OECD live prices system)", "unit": "%", "freq": "months",
        "points": [[p, 1.9] for p in months("2016-01", "2026-08")]}
    def trade_world(flow):
        if "eurostat-trade" in DOWN: return None
        last = TM if flow == "EXP" else TM[:-1]          # imports a month behind exports
        return [[p, 17000.4 if flow == "EXP" else 15500.1] for p in last]
    F.fetch_eurostat_trade_world = trade_world
    F.ecb_exr.fetch_monthly = lambda cur: {} if "ecb-exr" in DOWN else dict(RATES)
    F.fetch_oecd_bci = lambda: [[p, 99.2] for p in M]
    F.fetch_eurostat_govfinance = lambda item: [[str(y), 73.5 if item == "GD" else -2.0] for y in range(2000, 2026)]
    F.series_guard.apply_guard = lambda *a, **k: None

def run(prev=None, key="test"):
    tmp = tempfile.mkdtemp(); cwd = os.getcwd()
    try:
        os.chdir(tmp)
        if prev: json.dump(prev, open("data-hu.json", "w"))
        if key: os.environ["FRED_API_KEY"] = key
        else: os.environ.pop("FRED_API_KEY", None)
        SEEN.clear()
        with redirect_stdout(io.StringIO()) as buf:
            rc = F.main()
        return rc, json.load(open("data-hu.json")), buf.getvalue()
    finally:
        os.chdir(cwd)

os.environ["OECD_TURN_GROUP"] = "ALL"
install()
rc, d, log = run()
s = d["series"]
WANT = {"gdp_level", "gdp_real", "gdp_growth", "unemployment", "policy_rate", "participation_rate", "employment_rate",
        "bond_yield_10y", "cpi", "cpi_mom", "cpi_national", "exports", "imports", "trade_balance",
        "business_confidence", "debt_gdp", "deficit", "current_account"}   # no FDI for Hungary (SPE flows)
check(rc == 0, "clean run returns 0")
check(set(s) == WANT, f"serves exactly the expected key set: extra {set(s) - WANT}, missing {WANT - set(s)}")
check("ecb_rate" not in s, "no ECB rate on a non-euro page")
fred_ids = [u.split("series_id=")[1].split("&")[0] for u in SEEN if "stlouisfed" in u]
check({"CP0000HUM086NEST", "LRAC64TTHUQ156S", "LREM64TTHUQ156S"} <= set(fred_ids), f"asks FRED for the country ids: {fred_ids}")
check(not any(t in x for x in fred_ids for t in ("GR", "EL", "PL", "FI", "CZ")), f"no template country ids left: {fred_ids}")
check("CPMNACSCAB1GQHU" not in fred_ids and "LRHUTTTTHUM156S" not in fred_ids and "IRLTLT01HUM156N" not in fred_ids,
      "Eurostat GDP/unemployment and ECB IRS used; FRED copies not fetched")
check(all(s[k]["unit"] == "HUFm" for k in ("gdp_level", "gdp_real", "exports", "imports", "trade_balance")),
      "every currency series in forint")
check("MNAC" in s["gdp_level"]["label"] and "MNAC" in s["gdp_real"]["label"], "Eurostat GDP asked in national currency (MNAC)")
check(all("HUM086" in s[k]["label"] for k in ("cpi", "cpi_mom")), "HICP labels name the country series")
check("national" in s["cpi_national"]["label"], "national CPI served under its own key")
check(s["policy_rate"]["points"][0][0] == "2001-07", f"policy rate starts at 2001-07: {s['policy_rate']['points'][0]}")
check(s["policy_rate"]["points"][-1] == ["2026-10", 3.5], f"BIS daily extends the policy rate: {s['policy_rate']['points'][-1]}")
check("M.HU" in s["policy_rate"]["label"] and "base rate" in s["policy_rate"]["label"], "policy rate label names BIS M.HU and the base rate")
check("L.L40.CI.0000.HUF" in s["bond_yield_10y"]["label"], "bond yield from ECB IRS for HUF")
ex, im, tb = (dict(s[k]["points"]) for k in ("exports", "imports", "trade_balance"))
check(ex.get("2026-06") == round(17000.4 * 390.0, 1) and im.get("2026-06") == round(15500.1 * 390.0, 1),
      f"trade converted at the month's ECB rate: {ex.get('2026-06')}, {im.get('2026-06')}")
check(tb.get("2026-06") == round(17000.4 * 390 - 15500.1 * 390, 1) and tb["2026-06"] > 0, f"balance = exports - imports, a surplus: {tb.get('2026-06')}")
check("2026-07" not in ex and s["exports"]["points"][-1][0] == "2026-06", "exports trimmed to the last month imports are published (2026-06)")
check(len({s[k]["points"][-1][0] for k in ("exports", "imports", "trade_balance")}) == 1,
      f"trade tiles end in the same month: {[s[k]['points'][-1][0] for k in ('exports', 'imports', 'trade_balance')]}")
fx = d["fx_to_usd"]
check(fx["history"][0][0] == "1995", f"FX history from 1995: {fx['history'][0]}")
check(fx["pair"] == "HUF/USD" and fx["direction"] == "divide" and fx["as_of"] == "2025" and fx["rate"] == WB["PA.NUS.FCRF"][-1][1],
      f"fx block: {fx['pair']} {fx['direction']} {fx['rate']} {fx['as_of']}")
check(any("country/HUN/" in u for u in SEEN) and not any("country/POL/" in u or "country/GRC/" in u for u in SEEN),
      "World Bank asked for HUN only")
check(s["gdp_growth"]["freq"] == "quarters" and abs(s["gdp_growth"]["points"][-1][1]
      - round((9000000 + (len(Q) - 1) * 60000) / (9000000 + (len(Q) - 2) * 60000) * 100 - 100, 2)) < 0.01,
      f"gdp_growth derived q/q from real levels: {s['gdp_growth']['points'][-1]}")

# ECB rate source down: no trade at all rather than euro figures on a forint page
DOWN.add("ecb-exr"); install()
_, d2, log2 = run()
check(not any(k in d2["series"] for k in ("exports", "imports", "trade_balance")), "no ECB rates: trade left out, never served in euro")
DOWN.clear()
# Eurostat GDP down: falls back to the HU FRED copies
DOWN.add("eurostat-gdp"); install()
_, d3, _ = run()
fred_ids3 = [u.split("series_id=")[1].split("&")[0] for u in SEEN if "stlouisfed" in u]
check("CPMNACSCAB1GQHU" in fred_ids3 and "CLVMNACSCAB1GQHU" in fred_ids3 and d3["series"]["gdp_level"]["unit"] == "HUFm",
      f"GDP fallback uses HU FRED ids, forint: {fred_ids3}")
DOWN.clear()
# ECB IRS down: FRED IRLTLT01HUM156N
DOWN.add("ecb-irs"); install()
_, d4, _ = run()
check("IRLTLT01HUM156N" in d4["series"]["bond_yield_10y"]["label"], "bond fallback is the HU FRED series")
DOWN.clear()
# Eurostat unemployment down: FRED LRHUTTTTHUM156S
DOWN.add("eurostat-unemp"); install()
_, d5, _ = run()
check("LRHUTTTTHUM156S" in d5["series"]["unemployment"]["label"], "unemployment fallback is the HU FRED series")
DOWN.clear()
# BIS returns an implausible value: policy rate left out this run
BIS_OVERRIDE["rows"] = BIS_MONTHLY[:-1] + [["2026-08", 375.0]]; install()
_, d6, log6 = run()
check("policy_rate" not in d6["series"] and "implausible" in log6, "implausible BIS value: policy rate left out, logged")
BIS_OVERRIDE.clear(); install()
# no key: no FRED calls, page still writes
rc7, d7, _ = run(key=None)
check(rc7 == 0 and not any("stlouisfed" in u for u in SEEN) and "policy_rate" in d7["series"],
      "no key: no FRED calls, non-FRED series still written")
# previous fx carried over when the World Bank FX call fails
DOWN.add("PA.NUS.FCRF"); install()
_, d8, _ = run(prev=d)
check(d8.get("fx_to_usd") == d["fx_to_usd"], "fx carried over from the previous file when World Bank FX fails")
DOWN.clear(); install()

# ecb_exr: parsing, short replies, conversion
csvtxt = "KEY,TIME_PERIOD,OBS_VALUE\n" + "".join(f"x,{p},24.5\n" for p in months("2015-01", "2026-09"))
with redirect_stdout(io.StringIO()):
    got = _REAL_FETCH_MONTHLY("HUF", get=lambda *a, **k: Resp(text=csvtxt))
    short = _REAL_FETCH_MONTHLY("HUF", get=lambda *a, **k: Resp(text="KEY,TIME_PERIOD,OBS_VALUE\nx,2026-09,24.5\n"))
    bad = _REAL_FETCH_MONTHLY("HUF", get=lambda *a, **k: Resp(code=500))
check(len(got) == len(months("2015-01", "2026-09")) and got["2026-09"] == 24.5, "ecb_exr parses the monthly CSV")
check(short == {} and bad == {}, "ecb_exr rejects a short reply and an HTTP error")
check(ecb_exr.to_national([["2026-01", 10.0], ["2026-02", 1.0]], {"2026-01": 24.5}) == [["2026-01", 245.0]],
      "to_national converts at the month's rate and drops months without one")

# audit: clean synthetic file passes structure; planted faults are caught
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
import audit_hu as A  # noqa: E402
def audit(x):
    A.RESULTS.clear()
    with redirect_stdout(io.StringIO()):
        A.structure_and_plausibility(x)
    return [r for r in A.RESULTS if r[0] == "FAIL"]
base = copy.deepcopy(d)
check(not audit(base), f"clean file passes the audit: {audit(base)}")
for name, plant in {
    "ecb_rate served": lambda x: x["series"].__setitem__("ecb_rate", x["series"]["policy_rate"]),
    "policy rate off the 5bp grid": lambda x: x["series"]["policy_rate"]["points"][-1].__setitem__(1, 3.53),
    "stale policy rate": lambda x: x["series"]["policy_rate"].update(points=x["series"]["policy_rate"]["points"][:-6]),
    "policy rate from before 2001-07": lambda x: x["series"]["policy_rate"]["points"].insert(0, ["2001-06", 3.75]),
    "FX upside down": lambda x: x["fx_to_usd"].update(rate=round(1 / x["fx_to_usd"]["rate"], 4),
                                                       history=[[p, round(1 / v, 4)] for p, v in x["fx_to_usd"]["history"]]),
    "FX history monthly, not annual": lambda x: x["fx_to_usd"].update(history=[["2026-01", 21.0]] * 2, rate=21.0),
    "FX direction multiply": lambda x: x["fx_to_usd"].update(direction="multiply"),
    "Greek label": lambda x: x["series"]["cpi"].update(label="HICP, all items, YoY (Greece)"),
    "Polish label": lambda x: x["series"]["cpi_national"].update(label="CPI, national, Poland"),
    "trade identity broken": lambda x: x["series"]["trade_balance"]["points"][-1].__setitem__(1, 1.0),
    "trade tiles end in different months": lambda x: x["series"]["imports"]["points"].pop(),
    "trade in euro": lambda x: x["series"]["trade_balance"].update(unit="\u20acm"),
    "deficit beyond range": lambda x: x["series"]["deficit"]["points"][-1].__setitem__(1, 8.0),
    "unnamed CPI jump": lambda x: x["series"]["cpi"]["points"][-1].__setitem__(1, 14.0),
    "unnamed national CPI jump": lambda x: x["series"]["cpi_national"]["points"][-1].__setitem__(1, 9.0),
    "unnamed gap in the bond yield": lambda x: x["series"]["bond_yield_10y"].update(points=[q for q in x["series"]["bond_yield_10y"]["points"] if q[0] != "2020-03"]),
    "GDP quarters disagree": lambda x: x["series"]["gdp_real"]["points"].pop(),
    "employment rate out of range": lambda x: x["series"]["employment_rate"]["points"][-1].__setitem__(1, 95.0),
    "current account missing": lambda x: x["series"].pop("current_account"),
    "FDI served": lambda x: x["series"].__setitem__("fdi", x["series"]["current_account"]),
}.items():
    x = copy.deepcopy(base); plant(x)
    check(bool(audit(x)), f"audit catches: {name}")

check(F.__doc__ and "Hungary" in F.__doc__ and "Czechia" in F.__doc__ and "Probed 9 Oct 2026" in F.__doc__,
      "docstring describes Hungary and its template")
import oecd_turn  # noqa: E402
check(oecd_turn.GROUPS.get("fetch_hu.py") == "B", "fetch_hu.py mapped to oecd_turn group B")
check(_live_hash() == _LIVE_H0, "live data-hu.json untouched by this test")
print(f"{N[0]} checks, {len(FAILS)} failures")
sys.exit(1 if FAILS else 0)
