#!/usr/bin/env python3
"""v1.9.124: cross-check our GDP per capita against the World Bank's own figure.

Ours: each economy's gdp_per_capita series (calendar-year GDP / that year's population, local
currency, whole units). Theirs: NY.GDP.PCAP.CN (GDP per capita, current local currency units).
For every economy and every year both publish (last 10 years), report the gap. Different GDP
vintages and population revisions mean small gaps are normal; anything over the tolerance is
listed for a look, not treated as wrong by itself.

Needs network access to api.worldbank.org and the `requests` package, so run it on the Mac:
    python3 tools/check_wb_gdp_per_capita.py            # tolerance 3%
    python3 tools/check_wb_gdp_per_capita.py --tol 5
Exit code 1 if any economy's latest common year is outside the tolerance.
"""
import argparse, json, os, re, sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
API = "https://api.worldbank.org/v2/country/{iso}/indicator/NY.GDP.PCAP.CN?format=json&per_page=100&date={y0}:{y1}"
# Economies the World Bank does not publish under an ISO2 code we hold, or where the comparison is not like for like
SKIP = {"Eurozone": "aggregate (WB code EMU, different coverage)", "Taiwan": "not covered by the World Bank"}


def countries():
    gen = open(os.path.join(ROOT, "generate_indicator_pages.py"), encoding="utf-8").read()
    for m in re.finditer(r'^    "([^"]+)":\s*\("([a-z]{2,3})", "[a-z-]+", "([A-Z]{2})",', gen, re.M):
        yield m.group(1), "data-" + m.group(2) + ".json", m.group(3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tol", type=float, default=3.0, help="percent gap allowed on the latest common year")
    args = ap.parse_args()
    import requests
    worst, out_of_tol, checked = [], [], 0
    for name, f, iso2 in countries():
        if name in SKIP:
            print(f"  skip  {name}: {SKIP[name]}")
            continue
        p = os.path.join(ROOT, f)
        if not os.path.exists(p):
            continue
        s = json.load(open(p, encoding="utf-8")).get("series", {}).get("gdp_per_capita")
        if not s or not s.get("points"):
            print(f"  none  {name}: no gdp_per_capita series")
            continue
        ours = {str(y): v for y, v in s["points"] if v}
        ys = sorted(ours)[-10:]
        r = requests.get(API.format(iso=iso2, y0=ys[0], y1=ys[-1]), timeout=30)
        r.raise_for_status()
        js = r.json()
        theirs = {row["date"]: row["value"] for row in (js[1] if len(js) > 1 and js[1] else []) if row.get("value")}
        common = [y for y in ys if y in theirs]
        if not common:
            print(f"  ----  {name}: World Bank has no overlapping year")
            continue
        checked += 1
        gaps = {y: (ours[y] / theirs[y] - 1) * 100 for y in common}
        y = common[-1]
        flag = abs(gaps[y]) > args.tol
        print(f"  {'OUT ' if flag else 'ok  '}  {name:14s} {y}: ours {ours[y]:,.0f}, World Bank {theirs[y]:,.0f}, gap {gaps[y]:+.2f}%"
              f"  (range over {len(common)} yrs: {min(gaps.values()):+.1f}% to {max(gaps.values()):+.1f}%)")
        worst.append((abs(gaps[y]), name, y, gaps[y]))
        if flag:
            out_of_tol.append(name)
    worst.sort(reverse=True)
    print(f"\n{checked} economies compared; {len(out_of_tol)} outside {args.tol}% on the latest common year")
    for g, n, y, v in worst[:5]:
        print(f"  largest: {n} {y} {v:+.2f}%")
    sys.exit(1 if out_of_tol else 0)


if __name__ == "__main__":
    main()
