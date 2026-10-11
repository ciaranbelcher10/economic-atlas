"""Offline tests for fetch_lv.py (v1.7.46, from test_fetch_ee.py). Every rule tested both ways, with
planted faults. Run: python3 tools/test_fetch_lv.py"""
from __future__ import annotations

import copy, io, json, os, re, sys, tempfile
from contextlib import redirect_stdout

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

# Tripwire: the test must never touch the live data file.
import hashlib as _hl
_LIVE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data-lv.json")
def _live_hash():
    return _hl.sha256(open(_LIVE, "rb").read()).hexdigest() if os.path.exists(_LIVE) else None
_LIVE_H0 = _live_hash()

import fetch_lv as F  # noqa: E402

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
    if sid.startswith("CP0000"): return [{"date": f"{p}-01", "value": str(100 + i * 0.2)} for i, p in enumerate(months("1996-01", "2026-08"))]  # from 1996: no HICP trim
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
        if "ec.europa.eu/eurostat" in url and "geo=LV" in url:
            per = M if "irt_lt_mcby_m" in url else Q[16:]
            if "lfsi_emp_q" in url and "eurostat-lfsi" in DOWN: return Resp(code=400)
            val = 4.1 if "irt_lt_mcby_m" in url else (71.0 if ("lfsq_argan" in url or "indic_em=ACT" in url) else 66.0)
            rs = Resp(); rs.text = json.dumps({"id": ["geo", "time"], "size": [1, len(per)],
                "dimension": {"geo": {"category": {"index": {"LV": 0}}}, "time": {"category": {"index": {p: i for i, p in enumerate(per)}}}},
                "value": {str(i): val for i in range(len(per))}})
            return rs
        raise RuntimeError("unexpected URL " + url)
    F.requests.get = fake_get
    F.eurostat_gdp.fetch_levels = lambda geo, cur, lab: {} if "eurostat-gdp" in DOWN else {
        "gdp_level": {"label": "GDP nominal, current prices, SA (Eurostat namq_10_gdp, CP_MEUR)", "unit": "\u20acm", "freq": "quarters",
                      "points": [[p, 3000.0 + i * 100] for i, p in enumerate(Q)]},
        "gdp_real": {"label": "Real GDP, chain-linked volume, SA (Eurostat namq_10_gdp, CLV20_MEUR)", "unit": "\u20acm", "freq": "quarters",
                     "points": [[p, 2500.0 + i * 80] for i, p in enumerate(Q)]}}
    F.eurostat_unemp.fetch = lambda geo: {} if "eurostat-unemp" in DOWN else {
        "unemployment": {"label": "Unemployment rate, SA (Eurostat une_rt_m)", "unit": "%", "freq": "months",
                         "points": [[p, 5.9] for p in M]}}
    F.fetch_eurostat_trade_balance_world = lambda: None if "eurostat-trade" in DOWN else [[p, -479.300000000003] for p in M[-120:]]
    F.fetch_oecd_bci = lambda: [[p, 99.2] for p in M]
    F.fetch_eurostat_govfinance = lambda item: [[str(y), 23.6 if item == "GD" else -1.5] for y in range(2000, 2026)]
    F.series_guard.apply_guard = lambda *a, **k: None

def run(prev=None, key="test"):
    tmp = tempfile.mkdtemp(); cwd = os.getcwd()
    try:
        os.chdir(tmp)
        if prev: json.dump(prev, open("data-lv.json", "w"))
        if key: os.environ["FRED_API_KEY"] = key
        else: os.environ.pop("FRED_API_KEY", None)
        SEEN.clear()
        with redirect_stdout(io.StringIO()) as buf:
            rc = F.main()
        return rc, json.load(open("data-lv.json")), buf.getvalue()
    finally:
        os.chdir(cwd)

os.environ["OECD_TURN_GROUP"] = "ALL"
install()
rc, d, log = run()
s = d["series"]
WANT = {"gdp_level", "gdp_real", "gdp_growth", "unemployment", "ecb_rate", "participation_rate", "employment_rate",
        "bond_yield_10y", "cpi", "cpi_mom", "trade_balance", "debt_gdp", "deficit", "business_confidence"}
check(rc == 0, "clean run returns 0")
check(set(s) == WANT, f"serves exactly the eurozone key set: extra {set(s) - WANT}, missing {WANT - set(s)}")
check("policy_rate" not in s and "current_account" not in s and "fdi" not in s, "no own policy rate, CA or FDI served")
fred_ids = [u.split("series_id=")[1].split("&")[0] for u in SEEN if "stlouisfed" in u]
check(all(("AT" not in x[5:] and "BE" not in x[5:]) for x in fred_ids if x.startswith(("CP0000", "IRLT", "LRAC", "LREM", "LRHU"))),
      f"no Belgian or Austrian series ids left: {fred_ids}")
check({"CP0000LVM086NEST", "IRLTLT01LVM156N", "ECBDFR", "DEXUSEU"} <= set(fred_ids) and not {"LRAC64TTLVQ156S", "LREM64TTLVQ156S"} & set(fred_ids),
      f"asks FRED for the Latvian ids: {fred_ids}")
check("CPMNACSCAB1GQEE" not in fred_ids and "LRHUTTTTLVM156S" not in fred_ids, "Eurostat GDP/unemployment used, FRED copies not fetched")
check(all("LVM086" in s[k]["label"] for k in ("cpi", "cpi_mom")), "HICP labels name the Latvian series")
check(s["cpi"]["points"][0][0] == "1997-01" and s["cpi_mom"]["points"][0][0] == "1996-02", f"HICP not trimmed (no SERIES_START for cpi): first {s['cpi']['points'][0][0]}")
check(s["ecb_rate"]["points"][0][0] == "2014-01", f"ECB rate served from euro entry (2014-01): first {s['ecb_rate']['points'][0][0]}")
check(all("lfsi_emp_q" in s[k]["label"] and "SA" in s[k]["label"] for k in ("participation_rate", "employment_rate")), "labour rates come from Eurostat lfsi_emp_q SA even when FRED answers")
check("business_confidence" in s and "OECD BCICP" in s["business_confidence"]["label"], "business confidence served from OECD BCICP")
check(F.OECD_QUERIES[0].split("DF_CLI/")[1].startswith("LVA.M.BCICP"), "OECD BCI query is LVA")
check(s["unemployment"]["points"][0][0] < "2009-01", "unemployment (Eurostat, no break) keeps its full history")
check(s["ecb_rate"]["points"][-1] == ["2026-10", 2.5], f"ECB rate current: {s['ecb_rate']['points'][-1]}")
check(s["gdp_growth"]["freq"] == "quarters" and abs(s["gdp_growth"]["points"][-1][1] - round((2500 + 125 * 80) / (2500 + 124 * 80) * 100 - 100, 2)) < 0.01,
      f"gdp_growth derived q/q from real levels: {s['gdp_growth']['points'][-1]}")
check(s["trade_balance"]["points"][-1][1] == -479.3, "trade balance rounded to 1dp (no float noise)")
check("Eurostat" in s["trade_balance"]["label"] and s["trade_balance"]["unit"] == "\u20acm", "trade from Eurostat, in euro")
fx = d["fx_to_usd"]
check(fx["pair"] == "EUR/USD" and fx["direction"] == "multiply" and fx["rate"] == 1.1259, f"fx block: {fx['pair']} {fx['rate']}")
_NC = len(months("1996-01", "2026-08"))
check(abs(s["cpi"]["points"][-1][1] - round(((100 + (_NC - 1) * 0.2) / (100 + (_NC - 13) * 0.2) - 1) * 100, 2)) < 0.01,
      f"cpi is YoY of the index: {s['cpi']['points'][-1]}")

# Eurostat GDP down: falls back to the Latvian FRED copies, not Austria's
DOWN.add("eurostat-gdp"); install()
rc2, d2, _ = run()
fred_ids2 = [u.split("series_id=")[1].split("&")[0] for u in SEEN if "stlouisfed" in u]
check("CPMNACSCAB1GQEE" in fred_ids2 and "CLVMNACSCAB1GQEE" in fred_ids2, f"GDP fallback uses Latvian FRED ids: {fred_ids2}")
DOWN.clear()
# Eurostat unemployment down: FRED LRHUTTTTLVM156S
DOWN.add("eurostat-unemp"); install()
_, d3, _ = run()
check("LRHUTTTTLVM156S" in d3["series"]["unemployment"]["label"], "unemployment fallback is the Latvian FRED series")
DOWN.clear()
# Eurostat trade down: FRED fallback converted to euro
DOWN.add("eurostat-trade"); install()
_, d4, log4 = run()
tb = d4["series"]["trade_balance"]
check("XTNTVA01LVM667S" in tb["label"] and tb["unit"] == "\u20acm", f"trade fallback is Latvian and converted to euro: {tb['label']}")
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

# OECD-derived FRED copies missing (likely for a small OECD member): Eurostat stand-ins
DOWN.update({"IRLTLT01LVM156N", "LREM64TTLVQ156S", "LRAC64TTLVQ156S"}); install()
rc8, d8, log8 = run()
s8 = d8["series"]
check(rc8 == 0 and "irt_lt_mcby_m" in s8["bond_yield_10y"]["label"] and s8["bond_yield_10y"]["points"][-1][1] == 4.1,
      f"bond falls back to Eurostat irt_lt_mcby_m: {s8['bond_yield_10y']['label']}")
check("lfsi_emp_q" in s8["employment_rate"]["label"] and "SA" in s8["employment_rate"]["label"] and s8["employment_rate"]["freq"] == "quarters" and s8["employment_rate"]["points"][-1][1] == 66.0,
      f"employment falls back to Eurostat SA lfsi_emp_q: {s8['employment_rate']['label']}")
check("lfsi_emp_q" in s8["participation_rate"]["label"] and s8["participation_rate"]["points"][-1][1] == 71.0,
      "participation falls back to Eurostat SA lfsi_emp_q (ACT)")
check(any("indic_em=EMP_LFS" in u and "s_adj=SA" in u for u in SEEN) and any("indic_em=ACT" in u for u in SEEN), "SA queries name EMP_LFS and ACT")
check(F._redact(RuntimeError("400 for url: https://api.stlouisfed.org/x?series_id=A&api_key=887dsecret&file_type=json")).count("887dsecret") == 0, "FRED api_key redacted from error text")
DOWN.add("eurostat-lfsi"); install()
_, d8b, _ = run()
check("lfsq_ergan" in d8b["series"]["employment_rate"]["label"] and "lfsq_argan" in d8b["series"]["participation_rate"]["label"],
      "SA query down: unadjusted lfsq_* used")
DOWN.discard("eurostat-lfsi")
check(any("geo=LV" in u and "age=Y15-64" in u for u in SEEN), "Eurostat labour query is Latvia, ages 15-64")
DOWN.clear(); install()
_, d9, _ = run()
check(not any("irt_lt_mcby_m" in u for u in SEEN), "no bond fallback call when FRED answers")

# audit: clean synthetic file passes structure; planted faults are caught
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
import audit_lv as A  # noqa: E402
def audit(x):
    A.RESULTS.clear()
    with redirect_stdout(io.StringIO()):
        A.structure_and_plausibility(x)
    return [r for r in A.RESULTS if r[0] == "FAIL"]
base = copy.deepcopy(d)
base["series"]["participation_rate"]["points"] = [[p, 65.0] for p in Q[16:] if p >= "2009-Q1"]
check(not audit(base), f"clean file passes the audit: {audit(base)}")
for name, plant in {
    "policy_rate served": lambda x: x["series"].__setitem__("policy_rate", x["series"]["ecb_rate"]),
    "ECB off the 5bp grid": lambda x: x["series"]["ecb_rate"]["points"][-1].__setitem__(1, 2.53),
    "stale ECB rate": lambda x: x["series"]["ecb_rate"].update(points=x["series"]["ecb_rate"]["points"][:-6]),
    "FX upside down": lambda x: x["fx_to_usd"].update(rate=round(1 / 1.1259, 4),
                                                       history=[[p, round(1 / v, 4)] for p, v in x["fx_to_usd"]["history"]]),
    "FX latest out of line with history": lambda x: x["fx_to_usd"].update(rate=0.888),
    "Belgian label": lambda x: x["series"]["cpi"].update(label="HICP, all items, YoY (Belgium)"),
    "GDP quarters disagree": lambda x: x["series"]["gdp_real"]["points"].pop(),
    "unnamed CPI jump": lambda x: x["series"]["cpi"]["points"][-1].__setitem__(1, 14.0),
    "wrong unit": lambda x: x["series"]["trade_balance"].update(unit="$m"),
    "labour rate from before the 2009 break": lambda x: x["series"]["employment_rate"]["points"].insert(0, ["2008-Q4", 67.7]),
}.items():
    x = copy.deepcopy(base); plant(x)
    check(bool(audit(x)), f"audit catches: {name}")

check(F.__doc__ and "Latvia" in F.__doc__ and "fetch_ee.py" in F.__doc__ and ("Confirmed by the first real run" in F.__doc__ or "UNCONFIRMED" in F.__doc__) and "0.702804" in F.__doc__,
      "docstring describes Latvia, its template, the conversion rate, and the run status")
import oecd_turn  # noqa: E402
_src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "fetch_lv.py"), encoding="utf-8").read()
_geos = set(re.findall(r"geo=([A-Z]{2})", _src))
check(_geos == {"LV"}, f"every Eurostat query in fetch_lv.py is geo=LV: {sorted(_geos)}")
check(oecd_turn.GROUPS.get("fetch_lv.py") == "A", "fetch_lv.py mapped to oecd_turn group A")
check(_live_hash() == _LIVE_H0, "live data-lv.json untouched by this test")
print(f"{N[0]} checks, {len(FAILS)} failures")
sys.exit(1 if FAILS else 0)
