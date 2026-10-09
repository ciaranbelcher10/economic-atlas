"""Offline tests for fetch_sa.py and tools/audit_sa.py (v1.7.35), with
Saudi-shaped fixtures (riyal peg, trade surplus, OECD national accounts).
Run: python3 tools/test_fetch_sa.py"""
from __future__ import annotations

import copy, hashlib, io, json, os, sys, tempfile
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..")); sys.path.insert(0, HERE)
LIVE = os.path.join(HERE, "..", "data-sa.json")
H0 = hashlib.sha256(open(LIVE, "rb").read()).hexdigest() if os.path.exists(LIVE) else None
os.environ["OECD_TURN_GROUP"] = "ALL"
import fetch_sa as F  # noqa: E402
import audit_sa as A  # noqa: E402
F.OECD_PAUSE = 0

N, BAD = [0], []
def check(ok, msg):
    N[0] += 1
    if not ok: BAD.append(msg); print("FAIL ", msg)

def months(a, b):
    y, m = int(a[:4]), int(a[5:]); out = []
    while f"{y}-{m:02d}" <= b:
        out.append(f"{y}-{m:02d}"); m += 1
        if m == 13: y, m = y + 1, 1
    return out
Q = [f"{y}-Q{q}" for y in range(2010, 2027) for q in range(1, 5)][:-2]

def qna_csv(la_only=False):
    rows = ["TRANSACTION,PRICE_BASE,ADJUSTMENT,TRANSFORMATION,UNIT_MEASURE,TIME_PERIOD,OBS_VALUE"]
    for i, q in enumerate(Q):
        nom = 900000 + i * 6000
        if la_only: rows.append(f"B1GQ,V,Y,LA,XDC,{q},{nom * 4}")
        else: rows.append(f"B1GQ,V,Y,N,XDC,{q},{nom}")
        rows.append(f"B1GQ,L,Y,N,XDC,{q},{800000 + i * 4000}")
        rows.append(f"B1GQ,L,N,N,XDC,{q},{(800000 + i * 4000) * (0.98 if q.endswith('Q2') else 1.0)}")
        if i:
            rows.append(f"B1GQ,L,Y,G1,PC,{q},{round(((800000 + i * 4000) / (800000 + (i - 1) * 4000) - 1) * 100, 3)}")
        if i >= 4:
            rows.append(f"B1GQ,L,Y,GY,PC,{q},{round(((800000 + i * 4000) / (800000 + (i - 4) * 4000) - 1) * 100, 3)}")
    return "\n".join(rows) + "\n"

ITG_M = months("2015-01", "2026-07")
def itg_csv():
    rows = ["INDICATOR,VALUATION,UNIT,TIME_PERIOD,OBS_VALUE"]
    for p in ITG_M:
        P = p.replace("-", "-M")
        rows.append(f"XG,FOB,XDC,{P},87762015822.0")
        rows.append(f"XG,FOB,USD,{P},23403204219.2")
        if p != ITG_M[-1]:                                    # imports a month behind exports
            rows.append(f"MG,CIF,XDC,{P},70447255064.0")
    return "\n".join(rows) + "\n"

BIS_M = [[p, 1.75 if p < "2000-01" else 5.0] for p in months("1995-01", "2026-08")]
WB = {"PA.NUS.FCRF": [[str(y), 3.75 if y >= 1987 else 3.6] for y in range(1960, 2026)],
      "SL.UEM.TOTL.ZS": [[str(y), 5.6 - (y - 1991) * 0.05] for y in range(1991, 2026)],
      "BN.CAB.XOKA.GD.ZS": [[str(y), 2.0] for y in range(1971, 2026)],
      "BX.KLT.DINV.WD.GD.ZS": [[str(y), 1.5] for y in range(1970, 2026)]}
CFG = {"la_only": False, "down": set()}
SEEN = []

class Resp:
    def __init__(self, text="", js=None, code=200): self.text, self._js, self.status_code = text, js, code
    def json(self): return self._js
    def raise_for_status(self):
        if self.status_code >= 400: raise RuntimeError(f"HTTP {self.status_code}")

def fake_get(url, timeout=None, headers=None, **kw):
    SEEN.append(url)
    for tag in CFG["down"]:
        if tag in url: return Resp(code=503)
    if "DF_QNA" in url: return Resp(qna_csv(CFG["la_only"]))
    if "WS_CBPOL/1.0/M.SA" in url: return Resp("TIME_PERIOD,OBS_VALUE\n" + "".join(f"{p},{v}\n" for p, v in BIS_M))
    if "WS_CBPOL/1.0/D.SA" in url: return Resp("TIME_PERIOD,OBS_VALUE\n2026-08-31,5.0\n2026-09-17,4.75\n2026-10-08,4.5\n")
    if "IMF.STA/ITG" in url: return Resp(itg_csv())
    if "worldbank" in url:
        code = url.split("/indicator/")[1].split("?")[0]
        return Resp(js=[{}, [{"date": y, "value": v} for y, v in WB[code]]])
    raise RuntimeError("unexpected URL " + url)

def install():
    F.requests.get = fake_get
    F._QNA.clear()
    F.oecd_prices.fetch_cpi_index = lambda areas, freq, label="": [] if "cpi" in CFG["down"] else \
        [[p, round(100 * (1.02 ** (i / 12)), 4)] for i, p in enumerate(months("2010-01", "2026-08"))]
    F.imf_weo.fetch = lambda iso3, code: [[str(y), 25.9 if code == F.imf_weo.DEBT else -2.5] for y in range(1991, 2025)]
    F.series_guard.apply_guard = lambda *a, **k: None

def run(prev=None):
    tmp = tempfile.mkdtemp(); cwd = os.getcwd()
    try:
        os.chdir(tmp)
        if prev: json.dump(prev, open("data-sa.json", "w"))
        SEEN.clear()
        with redirect_stdout(io.StringIO()) as buf:
            rc = F.main()
        return rc, json.load(open("data-sa.json")), buf.getvalue()
    finally:
        os.chdir(cwd)

install()
rc, d, log = run()
s = d["series"]
WANT = {"gdp_level", "gdp_real", "gdp_growth", "gdp_growth_yoy", "cpi", "cpi_mom", "policy_rate", "unemployment",
        "exports", "imports", "trade_balance", "debt_gdp", "deficit", "current_account", "fdi"}
check(rc == 0, "clean run returns 0")
check(set(s) == WANT, f"serves exactly the Saudi key set: extra {set(s) - WANT}, missing {WANT - set(s)}")
check(not any(k in s for k in ("bond_yield_10y", "business_confidence")), "no bond yield or business confidence")
check(all(s[k]["unit"] == "SARm" for k in ("gdp_level", "gdp_real", "exports", "imports", "trade_balance")), "currency series in riyals")
check(s["gdp_level"]["points"][-1] == ["2026-Q2", 900000 + (len(Q) - 1) * 6000], "nominal GDP from the SA level (N)")
check(s["policy_rate"]["points"][0][0] == "2000-01" and s["policy_rate"]["points"][-1] == ["2026-10", 4.5],
      f"policy rate from 2000-01, extended by BIS daily: {s['policy_rate']['points'][0]} .. {s['policy_rate']['points'][-1]}")
check(s["cpi"]["freq"] == "months" and abs(s["cpi"]["points"][-1][1] - 2.0) < 0.05 and s["cpi_mom"]["freq"] == "months",
      f"monthly CPI rates from the index: {s['cpi']['points'][-1]}")
ex, im, tb = (dict(s[k]["points"]) for k in ("exports", "imports", "trade_balance"))
check(ex.get("2026-06") == 87762.0 and im.get("2026-06") == 70447.3, f"trade in riyal million from the IMF's XDC: {ex.get('2026-06')}, {im.get('2026-06')}")
check(tb.get("2026-06") == round(87762.0 - 70447.3, 1) and tb["2026-06"] > 0, "balance = exports - imports, a surplus")
check(len({s[k]["points"][-1][0] for k in ("exports", "imports", "trade_balance")}) == 1 and "2026-07" not in ex,
      "trade tiles end in the same month (exports trimmed to imports)")
check("USD" not in s["exports"]["label"] and "riyals" in s["exports"]["label"], "trade label says riyals")
y = dict(s["gdp_growth_yoy"]["points"])
check("not seasonally adjusted" in s["gdp_growth_yoy"]["label"] and y["2026-Q2"] == round(((800000 + (len(Q) - 1) * 4000) * 0.98 / ((800000 + (len(Q) - 5) * 4000) * 0.98) - 1) * 100, 1),
      f"y/y from unadjusted levels (GASTAT's headline): {y.get('2026-Q2')}")
check(s["unemployment"]["freq"] == "years" and "ILO modelled" in s["unemployment"]["label"], "unemployment disclosed as the ILO modelled estimate")
fx = d["fx_to_usd"]
check(fx["pair"] == "SAR/USD" and fx["direction"] == "divide" and fx["rate"] == 3.75 and fx["as_of"] == "2025", f"fx block: {fx}"[:120])
check(any("country/SAU/" in u for u in SEEN) and any("Q..SAU" in u for u in SEEN) and not any("NZL" in u or "M.NZ" in u for u in SEEN),
      "every request names Saudi Arabia, none New Zealand")

CFG["la_only"] = True; install()
_, d2, log2 = run()
check(d2["series"]["gdp_level"]["points"][-1][1] == 900000 + (len(Q) - 1) * 6000 and "divided by four" in log2,
      "annualised-only GDP is divided by four, and the log says so")
CFG["la_only"] = False
CFG["down"] = {"IMF.STA/ITG"}; install()
_, d3, _ = run()
check(not any(k in d3["series"] for k in ("exports", "imports", "trade_balance")), "IMF trade down: trade left out (guard carries it)")
CFG["down"] = {"PA.NUS.FCRF"}; install()
_, d4, _ = run(prev=d)
check(d4.get("fx_to_usd") == d["fx_to_usd"], "fx carried over when the World Bank fails")
CFG["down"] = set(); install()

def audit(x):
    A.RESULTS.clear()
    with redirect_stdout(io.StringIO()):
        A.structure_and_plausibility(x)
    return [r for r in A.RESULTS if r[0] == "FAIL"]
base = copy.deepcopy(d)
check(not audit(base), f"clean file passes the audit: {audit(base)}")
for name, plant in {
    "bond yield served": lambda x: x["series"].__setitem__("bond_yield_10y", x["series"]["policy_rate"]),
    "policy rate before 2000": lambda x: x["series"]["policy_rate"]["points"].insert(0, ["1999-12", 5.0]),
    "policy rate off grid": lambda x: x["series"]["policy_rate"]["points"][-1].__setitem__(1, 4.53),
    "stale policy rate": lambda x: x["series"]["policy_rate"].update(points=x["series"]["policy_rate"]["points"][:-6]),
    "FX off the peg": lambda x: x["fx_to_usd"].update(rate=3.6, history=x["fx_to_usd"]["history"][:-1] + [["2025", 3.6]]),
    "FX upside down": lambda x: x["fx_to_usd"].update(rate=0.2667, history=[[p, 0.2667] for p, v in x["fx_to_usd"]["history"]]),
    "FX multiply": lambda x: x["fx_to_usd"].update(direction="multiply"),
    "trade identity broken": lambda x: x["series"]["trade_balance"]["points"][-1].__setitem__(1, 1.0),
    "trade ends differ": lambda x: x["series"]["imports"]["points"].pop(),
    "New Zealand label": lambda x: x["series"]["cpi"].update(label="CPI (Stats NZ via OECD)"),
    "CPI jump unnamed": lambda x: x["series"]["cpi"]["points"][-1].__setitem__(1, 9.0),
    "CPI with two decimals": lambda x: x["series"]["cpi"]["points"][-1].__setitem__(1, 2.04),
    "unemployment in USD": lambda x: x["series"]["unemployment"].update(unit="SARm"),
    "deficit out of range": lambda x: x["series"]["deficit"]["points"][-1].__setitem__(1, -40.0),
}.items():
    x = copy.deepcopy(base); plant(x)
    check(bool(audit(x)), f"audit catches: {name}")

import oecd_turn  # noqa: E402
check(oecd_turn.GROUPS.get("fetch_sa.py") == "A", "fetch_sa.py in oecd_turn group A")
check("Saudi Arabia" in F.__doc__ and "modelled" in F.__doc__, "docstring names the country and the unemployment stand-in")
check((hashlib.sha256(open(LIVE, "rb").read()).hexdigest() if os.path.exists(LIVE) else None) == H0, "live data-sa.json untouched")
print(f"{N[0]} checks, {len(BAD)} failures")
sys.exit(1 if BAD else 0)
