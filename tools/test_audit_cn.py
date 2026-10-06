"""Proves tools/audit_cn.py catches the faults it exists to catch: a clean
synthetic China file passes, and each planted fault fails the audit.
    python3 tools/test_audit_cn.py   -> "N ok, 0 failed"
"""
import copy, json, os, subprocess, sys, tempfile
from datetime import date
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ok = bad = 0
def check(name, cond, detail=""):
    global ok, bad
    if cond: ok += 1
    else: bad += 1; print("FAIL", name, detail)

T = date.today()
def periods(kind, n):
    out = []
    if kind == "months":
        k = T.year * 12 + T.month - 1 - 2
        for i in range(n): y, m = divmod(k - i, 12); out.append(f"{y}-{m + 1:02d}")
    elif kind == "quarters":
        k = T.year * 4 + (T.month - 1) // 3 - 1
        for i in range(n): y, q = divmod(k - i, 4); out.append(f"{y}-Q{q + 1}")
    else:
        out = [str(T.year - 1 - i) for i in range(n)]
    return out[::-1]
VAL = {"gdp_level": 3.5e7, "gdp_growth": 1.0, "gdp_growth_yoy": 5.0, "gdp_real": 1.3e8, "cpi": 0.8, "cpi_mom": 0.1,
       "policy_rate": 3.0, "bond_yield_10y": 1.7, "business_confidence": 98.4, "debt_gdp": 90.0, "deficit": -7.0,
       "current_account": 2.0, "fdi": 0.4, "unemployment": 4.6, "exports": 2.4e6, "imports": 1.8e6, "trade_balance": 6e5}
sys.path.insert(0, os.path.join(ROOT, "tools"))
import audit_cn
series = {}
for k, (unit, freq, *_r) in audit_cn.EXPECT.items():
    series[k] = {"label": f"{k} (official source)", "unit": unit, "freq": freq,
                 "points": [[p, VAL[k]] for p in periods(freq, 40)]}
clean = {"updated": "2026-10-06T00:00:00Z", "series": series,
         "fx_to_usd": {"pair": "CNY/USD", "rate": 7.1, "as_of": "x", "direction": "divide", "history": []}}

def audit(d):
    f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False); json.dump(d, f); f.close()
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "audit_cn.py"), "--offline", f.name],
                       capture_output=True, text=True)
    os.unlink(f.name)
    return r.returncode, r.stdout

rc, out = audit(clean)
check("clean file passes", rc == 0, out[-600:])
def planted(name, mutate, expect):
    d = copy.deepcopy(clean); mutate(d)
    rc, out = audit(d)
    check(name, rc == 1 and expect in out, out[-400:])
planted("missing series", lambda d: d["series"].pop("cpi"), "FAIL  cpi present")
planted("GDP in billions not millions", lambda d: [p.__setitem__(1, p[1] / 1000) for p in d["series"]["gdp_level"]["points"]], "outside")
planted("CPI as a fraction", lambda d: d["series"]["cpi"]["points"][-1].__setitem__(1, 0.008 * 1000), "jump over")
planted("gap in a series", lambda d: d["series"]["cpi"]["points"].pop(20), "gap")
planted("stale series", lambda d: d["series"]["policy_rate"].__setitem__("points", d["series"]["policy_rate"]["points"][:-8]), "stale")
planted("LPR off the 5bp grid", lambda d: d["series"]["policy_rate"]["points"][-1].__setitem__(1, 3.03), "5bp")
planted("balance not exports minus imports", lambda d: d["series"]["trade_balance"]["points"][-1].__setitem__(1, 1.0), "mismatched")
planted("wrong unit", lambda d: d["series"]["exports"].__setitem__("unit", "$m"), "unit")
planted("internal wording in a label", lambda d: d["series"]["cpi"].__setitem__("label", "CPI (confirmed live)"), "internal wording")
planted("FX direction flipped", lambda d: d["fx_to_usd"].__setitem__("rate", 0.14), "fx_to_usd block")
rc, out = audit(dict(clean, series={k: v for k, v in clean["series"].items() if k != "cpi_mom"}))
check("cpi_mom may be absent", rc == 0 and "cpi_mom absent by design" in out, out[-300:])
planted("derived MoM label fails", lambda d: d["series"]["cpi_mom"].__setitem__("label", "CPI, all items, MoM (IMF CPI index)"), "not derived")
print(f"{ok} ok, {bad} failed"); sys.exit(1 if bad else 0)
