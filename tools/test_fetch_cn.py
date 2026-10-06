"""Offline tests for fetch_cn.py: every source answered by canned responses
shaped like the real ones in the October 2026 probe output, then the
written data-cn.json is checked series by series.

    python3 tools/test_fetch_cn.py   -> "N ok, 0 failed"
"""
import csv, io, json, os, shutil, sys, tempfile
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["OECD_TURN_GROUP"] = "ALL"
import fetch_cn, fetch_ma, oecd_turn  # noqa: E402

ok = bad = 0
def check(name, cond, detail=""):
    global ok, bad
    if cond: ok += 1
    else: bad += 1; print("FAIL", name, detail)

T = date.today()
def months(n):
    out, y, m = [], T.year, T.month - 2          # last month published two months ago
    for _ in range(n):
        if m < 1: y, m = y - 1, m + 12
        out.append(f"{y}-{m:02d}"); m -= 1
    return out[::-1]
def quarters(n):
    out, y, q = [], T.year, (T.month - 1) // 3   # last full quarter
    if q == 0: y, q = y - 1, 4
    for _ in range(n):
        out.append(f"{y}-Q{q}"); q -= 1
        if q == 0: y, q = y - 1, 4
    return out[::-1]
def csvtext(rows):
    buf = io.StringIO(); w = csv.DictWriter(buf, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    return buf.getvalue()

M, Q = months(40), quarters(20)
qna_rows = []
for i, p in enumerate(Q):
    base = dict(FREQ="Q", REF_AREA="CHN", TRANSACTION="B1GQ", TIME_PERIOD=p)
    qna_rows += [dict(base, ADJUSTMENT="N", UNIT_MEASURE="XDC", PRICE_BASE="V", TRANSFORMATION="N", TABLE_IDENTIFIER=t,
                      OBS_VALUE=str(30000000 + i * 100000)) for t in ("T0101", "T0102")]
    qna_rows.append(dict(base, ADJUSTMENT="Y", UNIT_MEASURE="PC", PRICE_BASE="L", TRANSFORMATION="G1", TABLE_IDENTIFIER="T0102", OBS_VALUE="0.9"))
    qna_rows.append(dict(base, ADJUSTMENT="Y", UNIT_MEASURE="PC", PRICE_BASE="L", TRANSFORMATION="GY", TABLE_IDENTIFIER="T0102", OBS_VALUE="4.3"))
    qna_rows.append(dict(base, ADJUSTMENT="N", UNIT_MEASURE="XDC", PRICE_BASE="Q", TRANSFORMATION="N", TABLE_IDENTIFIER="T0101", OBS_VALUE="1"))
    qna_rows.append(dict(base, TRANSACTION="B1G", ADJUSTMENT="N", UNIT_MEASURE="XDC", PRICE_BASE="V", TRANSFORMATION="N", TABLE_IDENTIFIER="T0101", OBS_VALUE="5"))
cpi_rows = [dict(REF_AREA="CHN", FREQ="M", METHODOLOGY="N", ADJUSTMENT="N", TRANSFORMATION="GY", TIME_PERIOD=p, OBS_VALUE="0.8") for p in M]
bci_rows = [dict(REF_AREA="CHN", FREQ="M", MEASURE="BCICP", TIME_PERIOD=p, OBS_VALUE="98.4") for p in M]
irlt_rows = [dict(REF_AREA="CHN", FREQ="M", MEASURE="IRLT", TIME_PERIOD=p, OBS_VALUE="1.69") for p in M]
bis_rows = [dict(TIME_PERIOD=p, OBS_VALUE="3.0") for p in M]
itg_rows = []
for p in M:
    pm = p.replace("-", "-M")
    itg_rows.append(dict(INDICATOR="XG", VALUATION="FOB", UNIT="USD", TRANSFORMATION="", TIME_PERIOD=pm, OBS_VALUE="300000000000"))
    if p != M[-1]:                               # imports a month behind, as in the probe
        itg_rows.append(dict(INDICATOR="MG", VALUATION="CIF", UNIT="USD", TRANSFORMATION="", TIME_PERIOD=pm, OBS_VALUE="200000000000"))
    itg_rows.append(dict(INDICATOR="XG", VALUATION="FOB", UNIT="PT", TRANSFORMATION="YOY_PCH", TIME_PERIOD=pm, OBS_VALUE="6.2"))
cpi_ix_rows = [dict(TIME_PERIOD=p.replace("-", "-M"), OBS_VALUE=str(100 + i * 0.1)) for i, p in enumerate(M)]
WB = {"NY.GDP.MKTP.KN": 134568798262700, "BN.CAB.XOKA.GD.ZS": 3.77, "BX.KLT.DINV.WD.GD.ZS": 0.41,
      "SL.UEM.TOTL.ZS": 4.615, "PA.NUS.FCRF": 7.19}
FRED_FX = [{"date": f"{p}-15", "value": "7.10"} for p in M] + [{"date": f"{M[-1]}-28", "value": "7.20"}]

class R:
    def __init__(self, text=None, js=None, code=200): self.text, self._js, self.status_code = text, js, code
    def json(self): return self._js
    def raise_for_status(self):
        if self.status_code >= 400: raise RuntimeError(f"HTTP {self.status_code}")

FAIL = set()
def fake_get(url, **kw):
    for tag in FAIL:
        if tag in url: return R("", code=503)
    if "DF_QNA" in url: return R(csvtext(qna_rows))
    if "DF_PRICES_C2018" in url: return R("", code=404)
    if "DF_PRICES_ALL" in url: return R(csvtext(cpi_rows))
    if "DF_CLI" in url: return R(csvtext(bci_rows))
    if "DF_FINMARK" in url: return R(csvtext(irlt_rows))
    if "WS_CBPOL" in url: return R(csvtext(bis_rows))
    if "/ITG/" in url: return R(csvtext(itg_rows))
    if "/CPI/" in url: return R(csvtext(cpi_ix_rows))
    if "worldbank" in url:
        code = url.split("/indicator/")[1].split("?")[0]
        return R(js=[{}, [{"date": "2025", "value": WB[code]}, {"date": "2024", "value": WB[code]}]])
    if "stlouisfed" in url: return R(js={"observations": FRED_FX})
    if "imf.org" in url and "WEO" in url: return R(js={})
    raise AssertionError("unexpected URL " + url)

import requests, imf_weo, fetch_bonds_daily
requests.get = fake_get
imf_weo.fetch = lambda iso3, ind: [["2023", 84.1], ["2024", 90.4]] if ind == imf_weo.DEBT else [["2023", -6.7], ["2024", -7.1]]
fetch_cn.imf_weo = imf_weo
fetch_cn.time.sleep = lambda s: None

def run(prev=None):
    tmp = tempfile.mkdtemp(); cwd = os.getcwd()
    try:
        os.chdir(tmp)
        if prev: json.dump(prev, open("data-cn.json", "w"))
        fetch_cn._QNA = None; fetch_ma._IMF_INDEX_CACHE.clear()
        rc = fetch_cn.main()
        return rc, json.load(open("data-cn.json"))
    finally:
        os.chdir(cwd); shutil.rmtree(tmp)

os.environ["FRED_API_KEY"] = "test"
rc, d = run()
s = d["series"]
check("exit 0", rc == 0)
want = {"gdp_level", "gdp_growth", "gdp_growth_yoy", "gdp_real", "cpi", "cpi_mom", "policy_rate", "bond_yield_10y",
        "business_confidence", "debt_gdp", "deficit", "current_account", "fdi", "unemployment", "exports", "imports", "trade_balance"}
check("all 17 series", set(s) == want, sorted(want ^ set(s)))
check("GDP level from T0101 current prices only", s["gdp_level"]["points"][0][1] == 30000000 and len(s["gdp_level"]["points"]) == 20)
check("GDP unit CNYm, quarterly", s["gdp_level"]["unit"] == "CNYm" and s["gdp_level"]["freq"] == "quarters")
check("QoQ growth is G1", all(v == 0.9 for _, v in s["gdp_growth"]["points"]))
check("YoY growth is GY", all(v == 4.3 for _, v in s["gdp_growth_yoy"]["points"]))
check("real GDP scaled to CNYm", abs(s["gdp_real"]["points"][-1][1] - 134568798.2627) < 1)
check("CPI fell back to C1999", s["cpi"]["points"][-1][1] == 0.8)
check("CPI MoM derived from IMF index", len(s["cpi_mom"]["points"]) == 39)
check("policy rate labelled LPR", "loan prime rate" in s["policy_rate"]["label"])
check("unemployment labelled ILO modelled", "ILO modelled" in s["unemployment"]["label"])
check("trade converted to CNYm", all(s[k]["unit"] == "CNYm" for k in ("exports", "imports", "trade_balance")))
check("exports at that month's rate", s["exports"]["points"][0][1] == round(300000 * 7.10, 1))
check("last month at month-end rate", s["exports"]["points"][-1][1] == round(300000 * 7.20, 1))
check("balance only where both months exist", s["trade_balance"]["points"][-1][0] == M[-2] and len(s["trade_balance"]["points"]) == 39)
check("balance = exports - imports", s["trade_balance"]["points"][0][1] == round(100000 * 7.10, 1))
check("fx block", d["fx_to_usd"]["pair"] == "CNY/USD" and d["fx_to_usd"]["direction"] == "divide" and d["fx_to_usd"]["rate"] == 7.20)
labels = " ".join(v["label"] for v in s.values()).lower()
check("no label carries internal build wording", not any(w in labels for w in ("confirmed", "placeholder", "inferred", "probe")))

# stale source rejected, previous data carried over
bis_rows[:] = [dict(TIME_PERIOD="2020-01", OBS_VALUE="3.0")]
rc2, d2 = run(prev=d)
check("stale BIS rejected and carried over", d2["series"]["policy_rate"]["points"] == s["policy_rate"]["points"])
bis_rows[:] = [dict(TIME_PERIOD=p, OBS_VALUE="45") for p in M]
rc3, d3 = run(prev=d)
check("implausible BIS rejected", d3["series"]["policy_rate"]["points"] == s["policy_rate"]["points"])
bis_rows[:] = [dict(TIME_PERIOD=p, OBS_VALUE="3.0") for p in M]

# no FX at all: fresh dollar trade must never be published as yuan
FAIL.update({"stlouisfed", "worldbank"})
rc4, d4 = run(prev=d)
check("no FX: trade carried over, still yuan", d4["series"]["exports"] == s["exports"])
rc5, d5 = run()
check("no FX, no history: trade left out", "exports" not in d5["series"])
FAIL.clear()

# off-turn: OECD series carried over, nothing else lost
os.environ["OECD_TURN_GROUP"] = "A"
sys.argv[0] = "fetch_cn.py"; oecd_turn._announced = False
rc6, d6 = run(prev=d)
check("off-turn keeps OECD series", all(d6["series"][k] == s[k] for k in ("gdp_level", "cpi", "business_confidence", "bond_yield_10y")))
check("off-turn still fetches BIS and World Bank", d6["series"]["policy_rate"] == s["policy_rate"] and "unemployment" in d6["series"])
check("fetch_cn.py is in turn group C", oecd_turn.GROUPS.get("fetch_cn.py") == "C")

print(f"{ok} ok, {bad} failed")
sys.exit(1 if bad else 0)
