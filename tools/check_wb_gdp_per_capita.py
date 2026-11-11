#!/usr/bin/env python3
"""v1.9.124: cross-check our GDP per capita against the World Bank's own figure.

Ours: each economy's gdp_per_capita series (calendar-year GDP / that year's population, local
currency, whole units). Theirs: NY.GDP.PCAP.CN (GDP per capita, current local currency units).
For every economy and every year both publish (last 10 years), report the gap. Different GDP
vintages and population revisions mean small gaps are normal; anything over the tolerance is
listed for a look, not treated as wrong by itself.

v1.9.125: one batched request per indicator with retries; a dollar-unit series (Switzerland) is
compared with NY.GDP.PCAP.CD (current US$), not the local-currency figure.

Needs network access to api.worldbank.org and the `requests` package, so run it on the Mac:
    python3 tools/check_wb_gdp_per_capita.py            # tolerance 3%
    python3 tools/check_wb_gdp_per_capita.py --tol 5
Exit code 1 if any economy's latest common year is outside the tolerance.
"""
import argparse, json, os, re, sys, time

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
# v1.9.125: one batched request per indicator (the per-economy calls timed out), 120s, 3 attempts.
API = "https://api.worldbank.org/v2/country/{isos}/indicator/{ind}?format=json&per_page=4000&date={y0}:{y1}"
LOCAL, USD = "NY.GDP.PCAP.CN", "NY.GDP.PCAP.CD"
# v1.9.126: explained differences. Inside its band an economy is reported as "known", not flagged;
# outside the band it is flagged like any other, so a new problem still shows.
KNOWN = {
    "Cyprus": ((3.0, 6.5), "population is Eurostat's for the government-controlled area (the area its GDP covers);"
               " the World Bank uses its own estimate for that area. Matches Eurostat's published GDP per capita."),
}
SKIP = {"Eurozone": "aggregate (WB code EMU, different coverage)", "Taiwan": "not covered by the World Bank"}


def already_usd():
    """Economies whose GDP the site holds in US dollars (the generator's GDP_ALREADY_USD)."""
    gen = open(os.path.join(ROOT, "generate_indicator_pages.py"), encoding="utf-8").read()
    m = re.search(r'^GDP_ALREADY_USD = \{([^}]*)\}', gen, re.M)
    return set(re.findall(r'"([^"]+)"', m.group(1))) if m else {"US", "Switzerland"}


def indicator_for(name, usd_names):
    """Our series' own currency decides the comparison. A "$" unit is not enough: Australia, Canada
    and Mexico are "$" in their own currency. Only economies held in US dollars use the US$ figure."""
    return USD if name in usd_names else LOCAL


def countries():
    gen = open(os.path.join(ROOT, "generate_indicator_pages.py"), encoding="utf-8").read()
    for m in re.finditer(r'^    "([^"]+)":\s*\("([a-z]{2,3})", "[a-z-]+", "([A-Z]{2})",', gen, re.M):
        yield m.group(1), "data-" + m.group(2) + ".json", m.group(3)


def fetch(requests, isos, ind, y0, y1):
    url = API.format(isos=";".join(sorted(isos)), ind=ind, y0=y0, y1=y1)
    for attempt in range(1, 4):
        try:
            r = requests.get(url, timeout=120); r.raise_for_status()
            js = r.json(); rows = js[1] if len(js) > 1 and js[1] else []
            out = {}
            for row in rows:
                if row.get("value"):
                    out.setdefault(row["country"]["id"], {})[row["date"]] = row["value"]
            return out
        except Exception as e:
            print(f"  {ind} attempt {attempt} failed: {type(e).__name__}: {e}")
            time.sleep(10 * attempt)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tol", type=float, default=3.0, help="percent gap allowed on the latest common year")
    args = ap.parse_args()
    import requests
    econ, usd_names = [], already_usd()
    for name, f, iso2 in countries():
        if name in SKIP:
            print(f"  skip  {name}: {SKIP[name]}"); continue
        p = os.path.join(ROOT, f)
        if not os.path.exists(p):
            continue
        s = json.load(open(p, encoding="utf-8")).get("series", {}).get("gdp_per_capita")
        if not s or not s.get("points"):
            print(f"  none  {name}: no gdp_per_capita series"); continue
        econ.append((name, iso2, indicator_for(name, usd_names), {str(y): v for y, v in s["points"] if v}))
    ys = sorted({y for e in econ for y in e[3]})[-11:]
    wb = {}
    for ind in (LOCAL, USD):
        isos = {e[1] for e in econ if e[2] == ind}
        if not isos:
            continue
        got = fetch(requests, isos, ind, ys[0], ys[-1])
        if got is None:
            sys.exit(f"World Bank API unavailable for {ind} after 3 attempts")
        wb[ind] = got
    worst, out_of_tol = [], []
    for name, iso2, ind, ours in econ:
        theirs = wb.get(ind, {}).get(iso2, {})
        common = sorted(y for y in ours if y in theirs)
        if not common:
            print(f"  ----  {name}: World Bank has no overlapping year"); continue
        gaps = {y: (ours[y] / theirs[y] - 1) * 100 for y in common}
        y = common[-1]
        band = KNOWN.get(name)
        known = bool(band) and band[0][0] <= gaps[y] <= band[0][1]
        flag = abs(gaps[y]) > args.tol and not known
        cur = "US$" if ind == USD else "local"
        print(f"  {'OUT ' if flag else ('known' if known else 'ok  ')}  {name:14s} {y} ({cur}): ours {ours[y]:,.0f}, World Bank {theirs[y]:,.0f}, gap {gaps[y]:+.2f}%"
              f"  (range over {len(common)} yrs: {min(gaps.values()):+.1f}% to {max(gaps.values()):+.1f}%)")
        if known:
            print(f"         known difference: {band[1]}")
        elif band:
            print(f"         OUTSIDE its known band {band[0][0]:+.1f}% to {band[0][1]:+.1f}%: look again")
        worst.append((abs(gaps[y]), name, y, gaps[y]))
        if flag:
            out_of_tol.append(name)
    worst.sort(reverse=True)
    print(f"\n{len(worst)} economies compared; {len(out_of_tol)} outside {args.tol}% on the latest common year")
    for g, n, y, v in worst[:5]:
        print(f"  largest: {n} {y} {v:+.2f}%")
    sys.exit(1 if out_of_tol else 0)


if __name__ == "__main__":
    main()
