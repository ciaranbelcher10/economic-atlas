"""v1.9.25: Germany, France, Italy, the Netherlands and Spain take trade_balance from Eurostat first.
Run: python3 tools/test_eurostat_trade.py"""
import inspect
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import eurostat_trade as et  # noqa: E402
import series_guard  # noqa: E402
import fetch_de, fetch_fr, fetch_it, fetch_nl, fetch_es  # noqa: E402,E401

fails, runs = [], 0


def check(cond, msg):
    global runs
    runs += 1
    if not cond:
        fails.append(msg)
        print("FAIL", msg)


def jsonstat(points):
    idx = {p: i for i, (p, _) in enumerate(points)}
    return {"dimension": {"time": {"category": {"index": idx}}}, "value": {str(i): v for i, (_, v) in enumerate(points) if v is not None}}


class Resp:
    def __init__(self, payload, status=200):
        self.payload, self.status_code = payload, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self.payload


def run(exp, imp, geo="DE"):
    asked = []

    def get(url, **kw):
        asked.append(url)
        if "stk_flow=EXP" in url:
            return exp if isinstance(exp, Resp) else Resp(jsonstat(exp))
        return imp if isinstance(imp, Resp) else Resp(jsonstat(imp))
    with mock.patch.object(et.requests, "get", side_effect=get), redirect_stdout(io.StringIO()):
        return et.series(geo), asked


# 1. the balance: exports less imports, matched by month, rounded to 0.1
s, asked = run([["2026-07", 100.04], ["2026-08", 120.0], ["2026-09", 5.0]], [["2026-06", 1.0], ["2026-07", 90.0], ["2026-08", 130.05]])
check(s and s["points"] == [["2026-07", 10.0], ["2026-08", -10.1]], f"balance wrong or unmatched months kept: {s and s['points']}")
check(s and s["label"] == "Trade balance, goods, total (Eurostat, world partner, derived EXP-IMP)" and s["unit"] == "\u20acm" and s["freq"] == "months",
      f"label, unit or frequency wrong: {s}")
check(len(asked) == 2 and all("geo=DE" in u and "partner=WORLD" in u and "ext_st_27_2020msbec" in u and "indic_et=TRD_VAL" in u
                              and "bclas_bec=TOTAL" in u for u in asked) and any("stk_flow=EXP" in u for u in asked)
      and any("stk_flow=IMP" in u for u in asked), f"query wrong: {asked}")
# 2. anything missing gives None, never a partial or invented series
check(run([["2026-07", 1.0]], Resp({}, 500))[0] is None, "a failed imports request must give None")
check(run(Resp({}, 404), [["2026-07", 1.0]])[0] is None, "a failed exports request must give None")
check(run([["2026-07", 1.0]], [["2026-08", 1.0]])[0] is None, "no shared month must give None")
check(run([], [])[0] is None, "empty flows must give None")
# 3. each script: FRED's copy is only the fallback, Eurostat is asked with the right code, before the guard
for mod, geo in ((fetch_de, "DE"), (fetch_fr, "FR"), (fetch_it, "IT"), (fetch_nl, "NL"), (fetch_es, "ES")):
    n = mod.__name__
    check("trade_balance" not in mod.FRED_SERIES, f"{n}: trade_balance still a primary FRED series")
    check(mod.TRADE_BALANCE_FRED_FALLBACK[0] == f"XTNTVA01{geo}M667S" and mod.TRADE_BALANCE_FRED_FALLBACK[3] == "$m",
          f"{n}: fallback series wrong: {mod.TRADE_BALANCE_FRED_FALLBACK}")
    src = inspect.getsource(mod.main)
    call, guard = src.find(f'eurostat_trade.series("{geo}")'), src.find("series_guard.apply_guard(")
    loop = src.find("for name, (sid, freq, label, unit, tf, scale) in FRED_SERIES.items():")
    check(src.count("eurostat_trade.series(") == 1 and -1 < loop < call < guard, f"{n}: Eurostat must be asked once, for {geo}, after FRED and before the guard")
    fb = src.find("TRADE_BALANCE_FRED_FALLBACK", call)
    check(call < fb < guard and "elif key:" in src[call:fb], f"{n}: the FRED fallback must run only when Eurostat fails")
    conv = src.find('if "trade_balance" in out["series"]:')
    check(conv > guard and 'ser["unit"].strip().startswith("$")' in src[conv:conv + 300],
          f"{n}: the $ to EUR conversion must only touch a series in dollars")
# 4. the guard: Eurostat (more current, 24 years) replaces FRED's copy; a later FRED fallback cannot drag it back
prev = json.loads((ROOT / "data-de.json").read_text(encoding="utf-8"))["series"]["trade_balance"]
eu = {"label": et.LABEL, "unit": et.UNIT, "freq": "months",
      "points": [[f"{y}-{m:02d}", 1.0] for y in range(2002, 2027) for m in range(1, 13) if (y, m) <= (2026, 8)]}
if prev["label"] != et.LABEL:      # before the first run with v1.9.25 the repo still holds FRED's copy
    chosen, verdict, _ = series_guard.merge_series("trade_balance", eu, prev)
    check(verdict == "new-current" and chosen is eu, f"the guard must accept the more current Eurostat series: {verdict}")
fred_older = dict(eu, label="Trade balance, goods, total (XTNTVA01DEM667S)", points=[[p, v] for p, v in eu["points"][:-1]])
chosen, verdict, _ = series_guard.merge_series("trade_balance", fred_older, eu)
check(verdict == "kept" and chosen is eu, f"a staler FRED fallback must not replace Eurostat: {verdict}")

print(f"test_eurostat_trade: {'FAILED' if fails else 'ok'} ({runs} checks, {len(fails)} failed)")
sys.exit(1 if fails else 0)
