#!/usr/bin/env python3
"""Offline checks for the ECB IRS 10-year yield switch (v1.6.42).

    python3 tools/test_ecb_irs.py     # prints "N ok", exits 1 on any failure
"""
import json, os, re, sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import ecb_irs, series_guard  # noqa: E402

CASES = {"Poland": ("PL", "PLN", "fetch_pl.py", "poland.html"),
         "Italy": ("IT", "EUR", "fetch_it.py", "italy.html"),
         "Spain": ("ES", "EUR", "fetch_es.py", "spain.html")}
ok, fails = 0, []


def check(cond, msg):
    global ok
    if cond:
        ok += 1
    else:
        fails.append(msg)


def months(start, end):
    y, m = start; out = []
    while (y, m) <= end:
        out.append([f"{y}-{m:02d}", 3.0]); m += 1
        if m == 13: y, m = y + 1, 1
    return out


# parser
csv_text = "KEY,FREQ,TIME_PERIOD,OBS_VALUE\nk,M,2026-07,5.5\nk,M,2026-08,5.81\nk,M,2026,9\nk,M,2026-09,\n"
check(ecb_irs.parse(csv_text) == [["2026-07", 5.5], ["2026-08", 5.81]], "parse keeps only monthly rows with values")
check(ecb_irs.key("PL", "PLN") == "M.PL.L.L40.CI.0000.PLN.N.Z", "key format")

src = json.load(open(os.path.join(REPO, "data-metric-sources.json"), encoding="utf-8"))
compare = open(os.path.join(REPO, "compare.html"), encoding="utf-8").read()
for country, (cc, cur, script, page) in CASES.items():
    k = ecb_irs.key(cc, cur)
    s = open(os.path.join(REPO, script), encoding="utf-8").read()
    check(f'ecb_irs.fetch("{cc}", "{cur}")' in s, f"{country}: script calls ecb_irs.fetch")
    check("name in direct" in s, f"{country}: FRED loop skips series served directly")
    check(not re.search(r'"bond_yield_10y":\s*"', s.split("ALLOW_SHRINK = ", 1)[1].split("\n\n", 1)[0]),
          f"{country}: no ALLOW_SHRINK for bond_yield_10y (it would let a quarterly fallback replace monthly)")
    pop = src[country]["bond_yield_10y"]["source"]
    check(k in pop, f"{country}: popover cites {k}")
    blk = re.search(r'\n  "?%s"?: \{(.*?)\n  \}' % country, compare, re.S)
    check(blk and k in blk.group(1), f"{country}: Compare block cites {k}")
    others = [ecb_irs.key(c2, u2) for n2, (c2, u2, _, _) in CASES.items() if n2 != country]
    check(blk and not any(o in blk.group(1) for o in others), f"{country}: Compare block cites no other country's key")
    html = open(os.path.join(REPO, page), encoding="utf-8").read()
    check(html.count(k) == 2, f"{country}: page cites {k} in tile/chart and info panel")
    check(not any(o in html for o in others), f"{country}: page cites no other country's key")

    # guard: the switch is accepted; a FRED quarterly fallback afterwards is not
    prev = json.load(open(os.path.join(REPO, f"data-{cc.lower()}.json"), encoding="utf-8"))["series"]["bond_yield_10y"]
    start = {"PL": (2001, 1), "IT": (1991, 3), "ES": (1991, 11)}[cc]
    new = {"label": "ECB IRS " + k, "unit": "%", "freq": "months", "points": months(start, (2026, 8))}
    v = series_guard.merge_series("bond_yield_10y", new, prev, {})[1]
    check(v.startswith("new"), f"{country}: guard accepts the ECB series (got {v})")
    fb = {"label": "FRED fallback", "unit": "%", "freq": "quarters",
          "points": [[f"{y}-Q{q}", 3.0] for y in range(1991, 2026) for q in range(1, 5)]}
    v = series_guard.merge_series("bond_yield_10y", fb, new, {})[1]
    check(v == "kept", f"{country}: guard keeps monthly ECB over a quarterly fallback (got {v})")

for f in fails:
    print("FAIL", f)
print(f"{ok} ok")
sys.exit(1 if fails else 0)
