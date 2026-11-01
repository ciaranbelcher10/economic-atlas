"""v1.9.53: when Eurostat fails, the euro area keeps its previous Eurostat series instead of
switching to FRED's EA19 copy (different aggregate and price base; it happened on 28 Oct 2026).

    python3 tools/test_fetch_ez_keep_eurostat.py   -> "N ok, 0 failed"

Offline: uses the live data-ez.json as the previous run, read only.
"""
import copy, io, json, os, re, sys
from contextlib import redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import fetch_ez as F  # noqa: E402

ok = bad = 0
def check(cond, name):
    global ok, bad
    if cond: ok += 1
    else: bad += 1; print("FAIL", name)

prev = json.load(open(os.path.join(ROOT, "data-ez.json")))["series"]
check(all("Eurostat" in prev[k]["label"] for k in F.EUROSTAT_DIRECT), "the live file serves all five from Eurostat (the premise)")

def run(fetched, prev_series):
    series = {k: v for k, v in fetched.items()}
    fetched = dict(fetched)
    with redirect_stdout(io.StringIO()) as buf:
        kept = F.keep_eurostat(series, fetched, prev_series)
    return series, fetched, kept, buf.getvalue()

# 1. Eurostat down for everything: all five kept from the previous run, so FRED is skipped for them
series, fetched, kept, log = run({}, prev)
check(kept == list(F.EUROSTAT_DIRECT), f"all five kept: {kept}")
check(all(series[k] is prev[k] and "EA19" not in series[k]["label"] for k in kept), "kept series are the previous Eurostat ones, never EA19")
check(all(k in fetched for k in F.EUROSTAT_DIRECT) and all(k in F.FRED_SERIES or k.startswith("cpi") for k in kept),
      "kept keys are marked fetched, so the FRED loop skips them")
check(log.count("CARRIED OVER") == 5 and "EA19" in log, "each keep is logged loudly")

# 2. Eurostat answers some: the fresh ones are not overwritten
fresh = {"label": "GDP nominal, current prices, SCA (Eurostat namq_10_gdp, CP_MEUR)", "unit": "\u20acm", "freq": "quarters", "points": [["2026-Q3", 1.0]]}
series, fetched, kept, _ = run({"gdp_level": fresh}, prev)
check(series["gdp_level"] is fresh and "gdp_level" not in kept, "a fresh Eurostat series this run is used, not the old one")
check(set(kept) == set(F.EUROSTAT_DIRECT) - {"gdp_level"}, f"the others are kept: {kept}")

# 3. the previous run had FRED's copy (no Eurostat yet): nothing kept, FRED stays the fallback
fred_prev = copy.deepcopy(prev)
for k in F.EUROSTAT_DIRECT:
    fred_prev[k]["label"] = "Real GDP, chained, quarterly level (CLVMEURSCAB1GQEA19)"
check(run({}, fred_prev)[2] == [], "no previous Eurostat series: nothing kept, FRED may fill in")
# 4. an empty previous series is never kept
empty_prev = copy.deepcopy(prev); empty_prev["gdp_real"]["points"] = []
check("gdp_real" not in run({}, empty_prev)[2], "an empty previous series is not kept")
check(run({}, {})[2] == [], "no previous file: nothing kept")

# 5. main() wires it in before the FRED loop, and the FRED loop skips what it kept
src = open(os.path.join(ROOT, "fetch_ez.py"), encoding="utf-8").read()
main = src[src.index("def main()"):]
i_keep, i_fred = main.find("keep_eurostat(out[\"series\"], es_gdp, _prev_eurostat)"), main.find("for name, (sid, freq, label, unit, tf, scale) in FRED_SERIES.items():")
check(0 < i_keep < i_fred, "keep_eurostat runs before the FRED loop")
check(re.search(r"FRED_SERIES\.items\(\):\s*\n\s*if name in es_gdp:\s*\n\s*continue", main), "the FRED loop skips keys already served")
check(set(F.EUROSTAT_DIRECT) >= {"gdp_level", "gdp_real", "gdp_growth"} and all(k in F.FRED_SERIES for k in ("gdp_level", "gdp_real", "gdp_growth")),
      "every GDP key FRED could fill is protected")

print(f"{ok} ok, {bad} failed")
sys.exit(1 if bad else 0)
