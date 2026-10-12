"""Offline tests for fetch_ph.py and tools/audit_ph.py (v1.7.49), with
Philippine-shaped fixtures (PSA OpenSTAT PXWeb tables, peso, trade deficit,
quarterly-then-monthly labour force survey). Run: python3 tools/test_fetch_ph.py"""
from __future__ import annotations

import copy, hashlib, io, json, os, sys, tempfile
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..")); sys.path.insert(0, HERE)
LIVE = os.path.join(HERE, "..", "data-ph.json")
H0 = hashlib.sha256(open(LIVE, "rb").read()).hexdigest() if os.path.exists(LIVE) else None
import fetch_ph as F  # noqa: E402
import audit_ph as A  # noqa: E402
F.PX_PAUSE = 0

N, BAD = [0], []
def check(ok, msg):
    N[0] += 1
    if not ok: BAD.append(msg); print("FAIL ", msg)

MN = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
def months(a, b):
    y, m = int(a[:4]), int(a[5:]); out = []
    while f"{y}-{m:02d}" <= b:
        out.append(f"{y}-{m:02d}"); m += 1
        if m == 13: y, m = y + 1, 1
    return out
Q = [f"{y}-Q{q}" for y in range(2010, 2027) for q in range(1, 5)][:-2]
YEARS = [str(y) for y in range(1955, 2027)]

def var(code, text, vals, time=False):
    return {"code": code, "text": text, "values": [f"{i}" for i in range(len(vals))], "valueTexts": vals, "time": time}

TABLES = {
    F.T_GDP_NSA: [var("Item", "Expenditure Item", ["Household Final Consumption Expenditure", "GROSS DOMESTIC PRODUCT", "Gross Domestic Product per capita"]),
                  var("Valuation", "Type of Valuation", ["At Current Prices", "At Constant 2018 Prices"]),
                  var("Year", "Year", YEARS, True), var("Quarter", "Quarter", ["Q1", "Q2", "Q3", "Q4", "Annual"], True)],
    F.T_GDP_SA: [var("Item", "Expenditure Item", ["Gross Domestic Product", "Gross National Income"]),
                 var("Year", "Year", YEARS, True), var("Period", "Period", ["Q1", "Q2", "Q3", "Q4"], True)],
    F.T_LFS: [var("Year", "Year", YEARS, True), var("Month", "Month", MN + ["Annual"], True),
              var("Rates", "Rates", ["Labor Force Participation Rate", "Employment Rate", "Unemployment Rate", "Underemployment Rate"]),
              var("Sex", "Sex", ["Both sexes", "Male", "Female"])],
}
for t in (F.T_CPI_YOY, F.T_CPI_INDEX, F.T_CPI_INDEX_BACK):
    TABLES[t] = [var("Geolocation", "Geolocation", ["PHILIPPINES", "NCR", "AONCR"]),
                 var("Commodity Description", "Commodity Description", ["0 - ALL ITEMS", "01 - FOOD AND NON-ALCOHOLIC BEVERAGES", "01.1 - FOOD"]),
                 var("Year", "Year", YEARS, True), var("Period", "Period", [m[:3] for m in MN], True)]

def lfs_months():
    # quarterly rounds (Jan/Apr/Jul/Oct) to 2020, monthly from 2021
    return [p for p in months("2005-01", "2020-12") if p[5:] in ("01", "04", "07", "10")] + months("2021-01", "2026-08")

def series_for(table, sel):
    """Fixture values by period for the selected (text) values."""
    t = {v["code"]: dict(zip(v["values"], v["valueTexts"])) for v in TABLES[table]}
    pick = {c: t[c][sel[c][0]] for c in sel}
    if table == F.T_GDP_NSA:
        out = {}
        for i, q in enumerate(Q):
            base = 4_000_000 + i * 60_000 if pick["Valuation"].startswith("At Current") else 3_000_000 + i * 40_000
            out[q] = base * (0.97 if q.endswith("Q1") else 1.0)
        return out
    if table == F.T_GDP_SA: return {q: 3_000_000 + i * 40_000 for i, q in enumerate(Q)}
    if table == F.T_CPI_YOY:
        ix = series_for(F.T_CPI_INDEX, sel)
        return {p: round((ix[p] / ix[f"{int(p[:4]) - 1}{p[4:]}"] - 1) * 100 + CFG["cpi_off"], 1) for p in months("2019-01", "2026-09")}
    if table == F.T_CPI_INDEX_BACK: return {p: round(42.2 * 1.003 ** i, 1) for i, p in enumerate(months("1994-01", "2017-12"))}
    if table == F.T_CPI_INDEX: return {p: round(100 * 1.002 ** i, 1) for i, p in enumerate(months("2018-01", "2026-09"))}
    if table == F.T_LFS:
        val = {"Labor Force Participation Rate": 64.516, "Employment Rate": 96.149, "Unemployment Rate": 3.851, "Underemployment Rate": 12.0}[pick["Rates"]]
        return {p: val for p in lfs_months()}
    raise RuntimeError(table)

def px_json(table, body):
    sel = {q["code"]: q["selection"]["values"] for q in body["query"]}
    vals = series_for(table, sel)
    tvars = [v for v in TABLES[table] if v["time"]]
    data = []
    for p, v in vals.items():
        y = p[:4]
        if "Q" in p: sub = f"Q{p[6]}"
        else: sub = [x for x in tvars[1]["valueTexts"] if x[:3] == MN[int(p[5:]) - 1][:3]][0]
        key = [str(YEARS.index(y)), str(tvars[1]["valueTexts"].index(sub))]
        data.append({"key": [sel[c][0] for c in sel] + key, "values": [str(v)]})
    data.append({"key": [sel[c][0] for c in sel] + [str(YEARS.index("2025")), str(len(tvars[1]["values"]) - 1)], "values": [".."]})
    cols = [{"code": c, "type": "d"} for c in sel] + [{"code": v["code"], "type": "t"} for v in tvars] + [{"code": "x", "type": "c"}]
    return {"columns": cols, "data": data}

ITG_M = months("2015-01", "2026-07")
def itg_csv():
    rows = ["INDICATOR,VALUATION,UNIT,TIME_PERIOD,OBS_VALUE"]
    for p in ITG_M:
        P = p.replace("-", "-M")
        if p <= "2022-12":                                     # the IMF's peso figures stop in 2022
            rows.append(f"XG,FOB,XDC,{P},380000000000.0")
            rows.append(f"MG,CIF,XDC,{P},640000000000.0")
        rows.append(f"XG,FOB,USD,{P},6500000000.0")
        if p != ITG_M[-1]:
            rows.append(f"MG,CIF,USD,{P},11000000000.0")
    return "\n".join(rows) + "\n"

BIS_M = [[p, 27.5 if p < "1990-01" else 5.0] for p in months("1986-01", "2026-08")]
FX_M = [[p, 58.0] for p in months("2000-01", "2026-09")]
WB = {"PA.NUS.FCRF": [[str(y), 57.5] for y in range(1960, 2026)],
      "BN.CAB.XOKA.GD.ZS": [[str(y), -2.0] for y in range(1977, 2026)],
      "BX.KLT.DINV.WD.GD.ZS": [[str(y), 2.0] for y in range(1977, 2026)]}
CFG = {"down": set(), "rename": False, "cpi_off": 0.0}
SEEN = []

class Resp:
    def __init__(self, text="", js=None, code=200, bom=False):
        self.text, self._js, self.status_code = text, js, code
        self.content = (b"\xef\xbb\xbf" if bom else b"") + json.dumps(js).encode() if js is not None else text.encode()
    def json(self): return self._js
    def raise_for_status(self):
        if self.status_code >= 400: raise RuntimeError(f"HTTP {self.status_code}")

def table_of(url):
    return url.split("/DB/", 1)[1]

def fake_get(url, timeout=None, headers=None, **kw):
    SEEN.append(url)
    for tag in CFG["down"]:
        if tag in url: return Resp(code=503)
    if "openstat.psa.gov.ph" in url:
        vs = copy.deepcopy(TABLES[table_of(url)])
        if CFG["rename"] and table_of(url) == F.T_LFS:
            vs[3]["valueTexts"] = ["Both sexes", "Male", "Female", "Both Sexes "]; vs[3]["values"].append("3")
        return Resp(js={"title": "t", "variables": vs}, bom=True)
    if "WS_CBPOL/1.0/M.PH" in url: return Resp("TIME_PERIOD,OBS_VALUE\n" + "".join(f"{p},{v}\n" for p, v in BIS_M))
    if "WS_CBPOL/1.0/D.PH" in url: return Resp("TIME_PERIOD,OBS_VALUE\n2026-08-31,5.0\n2026-09-15,5.0\n2026-10-08,4.75\n")
    if "WS_XRU/1.0/M.PH.PHP.A" in url: return Resp("TIME_PERIOD,OBS_VALUE\n" + "".join(f"{p},{v + 0.5}\n" for p, v in FX_M))
    if "WS_XRU/1.0/M.PH.PHP.E" in url: return Resp("TIME_PERIOD,OBS_VALUE\n" + "".join(f"{p},{v}\n" for p, v in FX_M))
    if "IMF.STA/ITG" in url: return Resp(itg_csv())
    if "worldbank" in url:
        code = url.split("/indicator/")[1].split("?")[0]
        return Resp(js=[{}, [{"date": y, "value": v} for y, v in WB[code]]])
    raise RuntimeError("unexpected URL " + url)

def fake_post(url, json=None, timeout=None, headers=None, **kw):
    SEEN.append("POST " + url)
    for tag in CFG["down"]:
        if tag in url: return Resp(code=503)
    return Resp(js=px_json(table_of(url), json), bom=True)

def install():
    F.requests.get = fake_get
    F.requests.post = fake_post
    F._META.clear()
    F.imf_weo.fetch = lambda iso3, code: [[str(y), 57.0 if code == F.imf_weo.DEBT else -5.5] for y in range(1990, 2025)]
    F.series_guard.apply_guard = lambda *a, **k: None

def run(prev=None):
    tmp = tempfile.mkdtemp(); cwd = os.getcwd()
    try:
        os.chdir(tmp)
        if prev: json.dump(prev, open("data-ph.json", "w"))
        SEEN.clear()
        with redirect_stdout(io.StringIO()) as buf:
            rc = F.main()
        return rc, json.load(open("data-ph.json")), buf.getvalue()
    finally:
        os.chdir(cwd)

install()
rc, d, log = run()
s = d["series"]
WANT = {"gdp_level", "gdp_real", "gdp_growth", "gdp_growth_yoy", "cpi", "cpi_mom", "policy_rate", "unemployment",
        "participation", "employment", "exports", "imports", "trade_balance", "debt_gdp", "deficit", "current_account", "fdi"}
check(rc == 0, "clean run returns 0")
check(set(s) == WANT, f"serves exactly the Philippine key set: extra {set(s) - WANT}, missing {WANT - set(s)}\n{log}")
check(not any(k in s for k in ("bond_yield_10y", "business_confidence")), "no bond yield or business confidence")
check(all(s[k]["unit"] == "PHPm" for k in ("gdp_level", "gdp_real", "exports", "imports", "trade_balance")), "currency series in pesos")
check(s["gdp_level"]["points"][-1] == ["2026-Q2", 4_000_000 + (len(Q) - 1) * 60_000], f"nominal GDP: GDP row at current prices {s['gdp_level']['points'][-1]}")
check(s["gdp_real"]["points"][-1] == ["2026-Q2", 3_000_000 + (len(Q) - 1) * 40_000], "real GDP from the SA table")
y = dict(s["gdp_growth_yoy"]["points"])
check(y["2026-Q1"] == round((3_000_000 + (len(Q) - 2) * 40_000) / (3_000_000 + (len(Q) - 6) * 40_000) * 100 - 100, 1),
      f"y/y from unadjusted constant-price levels: {y.get('2026-Q1')}")
check(s["gdp_growth"]["points"][0][0] == "2010-Q2" and s["gdp_growth"]["points"][-1][0] == "2026-Q2"
      and "seasonally adjusted" in s["gdp_growth"]["label"], "q/q computed from SA levels, ends with the levels")
check(not any("022B5BEXS2" in u for u in SEEN), "PSA's mislabelled growth table is not queried")
c = dict(s["cpi"]["points"])
check(s["cpi"]["points"][0][0] == "1995-01" and all(p in c for p in months("1995-01", "2026-09")), f"CPI from 1995, no hole: {s['cpi']['points'][0]}")
check(not any("0012M4ACP27" in u for u in SEEN), "PSA's broken back series is not queried")
check(abs(s["cpi_mom"]["points"][-1][1] - 0.2) <= 0.1 and s["cpi_mom"]["points"][0][0] == "2018-02", "m/m from the 2018-based index")
check(s["unemployment"]["points"][0][0] == "2021-01" and s["unemployment"]["points"][-1] == ["2026-08", 3.9]
      and s["participation"]["points"][-1] == ["2026-08", 64.5],
      f"LFS from the unbroken monthly run: {s['unemployment']['points'][0]}")
check(s["employment"]["points"][-1] == ["2026-08", round(64.516 * 96.149 / 100, 1)], "employment ratio from unrounded participation x employment rate")
ex, im, tb = (dict(s[k]["points"]) for k in ("exports", "imports", "trade_balance"))
check(ex.get("2026-06") == round(6500 * 58.5, 1) and im.get("2026-06") == round(11000 * 58.5, 1) and tb["2026-06"] < 0,
      f"trade: IMF US$ at the BIS monthly AVERAGE rate, peso million, a deficit: {ex.get('2026-06')}")
check(s["exports"]["points"][-1][0] == "2026-06" and "average rate" in s["exports"]["label"], "trade current (not the stale peso series) and the label discloses the conversion")
check("2026-07" not in ex, "exports trimmed to the last month with imports")
check(s["policy_rate"]["points"][0][0] == "2002-01" and s["policy_rate"]["points"][-1] == ["2026-10", 4.75], f"policy rate extended by BIS daily: {s['policy_rate']['points'][-1]}")
fx = d["fx_to_usd"]
check(fx["pair"] == "PHP/USD" and fx["direction"] == "divide" and fx["rate"] == 57.5 and fx["as_of"] == "2025"
      and all(str(p).isdigit() for p, v in fx["history"]), f"fx block annual from the World Bank (fx_config.ANNUAL): {fx}"[:140])
check(any("country/PHL/" in u for u in SEEN) and not any(t in u for u in SEEN for t in ("MYS", "M.MY", "SAU", "M.SA", "oecd")),
      "every request names the Philippines; no OECD, Malaysia or Saudi calls")

CFG["down"] = {"IMF.STA/ITG"}; install()
_, d3, _ = run()
check(not any(k in d3["series"] for k in ("exports", "imports", "trade_balance")), "IMF trade down: trade left out (guard carries it)")
CFG["down"] = {"PA.NUS.FCRF"}; install()
_, d4, _ = run(prev=d)
check(d4.get("fx_to_usd") == d["fx_to_usd"], "fx carried over when both FX sources fail")
CFG["down"] = set(); CFG["rename"] = True; install()
_, d5, log5 = run()
check(not any(k in d5["series"] for k in ("unemployment", "participation", "employment")) and "matched 2 values" in log5,
      "ambiguous PXWeb value (two 'both sexes'-like rows) fails loudly, not silently")
CFG["rename"] = False; CFG["cpi_off"] = 0.3; install()
_, d6, log6 = run()
check("cpi" not in d6["series"] and "does not reproduce" in log6, "CPI fails if the index does not reproduce PSA's published rate")
CFG["cpi_off"] = 0.0; install()

def audit(x):
    A.RESULTS.clear()
    with redirect_stdout(io.StringIO()):
        A.structure_and_plausibility(x)
    return [r for r in A.RESULTS if r[0] == "FAIL"]
base = copy.deepcopy(d)
check(not audit(base), f"clean file passes the audit: {audit(base)}")
for name, plant in {
    "bond yield served": lambda x: x["series"].__setitem__("bond_yield_10y", x["series"]["policy_rate"]),
    "policy rate off grid": lambda x: x["series"]["policy_rate"]["points"][-1].__setitem__(1, 4.6),
    "stale policy rate": lambda x: x["series"]["policy_rate"].update(points=x["series"]["policy_rate"]["points"][:-6]),
    "FX upside down": lambda x: x["fx_to_usd"].update(rate=0.0172, history=[[p, 0.0172] for p, v in x["fx_to_usd"]["history"]]),
    "FX monthly history": lambda x: x["fx_to_usd"]["history"].append(["2026-09", 62.7]),
    "FX multiply": lambda x: x["fx_to_usd"].update(direction="multiply"),
    "trade identity broken": lambda x: x["series"]["trade_balance"]["points"][-1].__setitem__(1, 1.0),
    "trade ends differ": lambda x: x["series"]["imports"]["points"].pop(),
    "labour ends differ": lambda x: x["series"]["employment"]["points"].pop(),
    "Malaysia label": lambda x: x["series"]["cpi"].update(label="CPI (DOSM, OpenDOSM)"),
    "CPI jump unnamed": lambda x: x["series"]["cpi"]["points"][-1].__setitem__(1, 9.0),
    "CPI with two decimals": lambda x: x["series"]["cpi"]["points"][-1].__setitem__(1, 1.74),
    "CPI before 1995": lambda x: x["series"]["cpi"]["points"].insert(0, ["1984-12", 62.8]),
    "unemployment gap": lambda x: x["series"]["unemployment"]["points"].pop(5),
    "unnamed participation jump": lambda x: x["series"]["participation"]["points"][-1].__setitem__(1, 58.0),
    "CPI 2026-04 jump named but March jump not": lambda x: x["series"]["cpi"]["points"][-2].__setitem__(1, 9.0),
    "unemployment in pesos": lambda x: x["series"]["unemployment"].update(unit="PHPm"),
    "deficit out of range": lambda x: x["series"]["deficit"]["points"][-1].__setitem__(1, -40.0),
}.items():
    x = copy.deepcopy(base); plant(x)
    check(bool(audit(x)), f"audit catches: {name}")

import oecd_turn  # noqa: E402
check(oecd_turn.GROUPS.get("fetch_ph.py") == "C", "fetch_ph.py mapped to oecd_turn group C (no OECD calls; every script is mapped)")
check("Philippines" in F.__doc__ and "fetch_my.py" in F.__doc__, "docstring names the country and the template")
check((hashlib.sha256(open(LIVE, "rb").read()).hexdigest() if os.path.exists(LIVE) else None) == H0, "live data-ph.json untouched")
print(f"{N[0]} checks, {len(BAD)} failures")
sys.exit(1 if BAD else 0)
