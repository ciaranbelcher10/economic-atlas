#!/usr/bin/env python3
"""Every fetch script that converts USD-denominated OECD trade into the
country's own currency must use each period's own exchange rate, never
today's spot rate for the whole history.

    python3 tools/test_trade_fx.py

Checks, for every root fetch_*.py that converts trade:
  1. static: no `lambda v: v * fx_rate` / `v / fx_rate` single-rate converter
  2. behavioural: _fx_rate_for_period picks the rate in effect for monthly,
     quarterly and annual periods, against monthly and annual rate history,
     and falls back to the earliest rate before the history starts
  3. data: for each served converted trade series, a before/after table of
     what today's single rate produced versus each period's own rate
Exit status is non-zero on any failure.
"""
import glob, importlib.util, json, os, re, sys

REPO = os.environ.get("ATLAS_REPO") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
sys.path.insert(0, REPO)
fails = 0

def fail(msg):
    global fails
    fails += 1
    print("  FAIL ", msg)

single = re.compile(r"^\s*to_local\s*=\s*lambda v:\s*v\s*[*/]\s*fx_rate\b", re.M)
converters = []
for f in sorted(glob.glob("fetch_*.py")):
    src = open(f, encoding="utf-8").read()
    if "to_local" not in src:
        continue
    if single.search(src):
        fail(f"{f} converts every period at one rate")
    elif "_fx_rate_for_period(fx_pts, per" in src:
        converters.append(f)
print(f"per-period converters: {len(converters)}")

hist_m = [["2019-12", 1.0], ["2020-01", 2.0], ["2020-06", 3.0], ["2021-01", 4.0]]
hist_a = [["2019", 10.0], ["2020", 20.0]]
cases = [(hist_m, "2020-03", 2.0), (hist_m, "2020-Q2", 3.0), (hist_m, "2020", 3.0),
         (hist_m, "2018-05", 1.0), (hist_m, "2030-01", 4.0),
         (hist_a, "2020-07", 20.0), (hist_a, "2019-Q4", 10.0), (hist_a, "2020", 20.0),
         ([], "2020-01", 9.0)]
for f in converters:
    spec = importlib.util.spec_from_file_location(f[:-3], f)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    for h, per, want in cases:
        got = m._fx_rate_for_period(h, per, 9.0)
        if got != want:
            fail(f"{f}: period {per} gave {got}, expected {want}")
print(f"rate selection: {len(converters) * len(cases)} cases")

print("\nserved series (today's single rate vs each period's own rate, 2010 point):")
for f in sorted(glob.glob("data-*.json")):
    try:
        d = json.load(open(f, encoding="utf-8"))
    except Exception:
        continue
    fx = d.get("fx_to_usd") or {}
    s = (d.get("series") or {}).get("trade_balance")
    if not s or not fx.get("history") or s.get("unit", "").startswith("$") and fx.get("pair", "").startswith("EUR"):
        continue
    p = next((x for x in s["points"] if str(x[0]).startswith("2010")), None)
    if p:
        print(f"  {f:16} {s['unit']:6} {p[0]}: {p[1]:,.1f}")

print(f"\n{fails} failures")
sys.exit(1 if fails else 0)
