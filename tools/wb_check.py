#!/usr/bin/env python3
"""Compare the Atlas's US$ GDP and GDP per person with the World Bank (World Development Indicators).

Reads the site's own figures from rankings/gdp-by-country.html and rankings/gdp-per-capita-by-country.html
(data-value, data-period), fetches NY.GDP.MKTP.CD and NY.GDP.PCAP.CD for the same year from the World Bank
API (public, no key), and prints the gap for every economy, largest first.

    python3 tools/wb_check.py              # writes wb_check.csv and prints a table
    python3 tools/wb_check.py --limit 1.0  # only rows more than 1% apart

Read-only: it changes no site file. The World Bank publishes once or twice a year, so it can lag national
revisions (Japan, Switzerland) and uses fiscal years for some economies (India: April to March).
"""
import argparse, csv, json, re, sys, time, urllib.request

ISO3 = {"US": "USA", "China": "CHN", "Eurozone": "EMU", "Germany": "DEU", "Japan": "JPN", "UK": "GBR", "India": "IND",
        "France": "FRA", "Italy": "ITA", "Canada": "CAN", "Brazil": "BRA", "Spain": "ESP", "South Korea": "KOR",
        "Australia": "AUS", "Mexico": "MEX", "Turkey": "TUR", "Indonesia": "IDN", "Netherlands": "NLD",
        "Saudi Arabia": "SAU", "Switzerland": "CHE", "Poland": "POL", "Taiwan": None, "Belgium": "BEL",
        "Argentina": "ARG", "Ireland": "IRL", "Sweden": "SWE", "Israel": "ISR", "Singapore": "SGP", "Austria": "AUT",
        "Norway": "NOR", "Vietnam": "VNM", "Philippines": "PHL", "Malaysia": "MYS", "Denmark": "DNK", "Colombia": "COL",
        "Romania": "ROU", "South Africa": "ZAF", "Hong Kong": "HKG", "Pakistan": "PAK", "Czechia": "CZE", "Egypt": "EGY",
        "Chile": "CHL", "Portugal": "PRT", "Peru": "PER", "Finland": "FIN", "Nigeria": "NGA", "Greece": "GRC",
        "New Zealand": "NZL", "Hungary": "HUN", "Morocco": "MAR", "Slovakia": "SVK", "Bulgaria": "BGR", "Croatia": "HRV",
        "Luxembourg": "LUX", "Lithuania": "LTU", "Slovenia": "SVN", "Latvia": "LVA", "Estonia": "EST", "Cyprus": "CYP",
        "Iceland": "ISL", "Malta": "MLT", "Thailand": "THA"}


def site(path, scale):
    s = open(path, encoding="utf-8").read()
    out = {}
    for c, v, p in re.findall(r'data-country="([^"]+)" data-value="([^"]+)"[^>]*?data-period="(\d{4})', s):
        out[c] = (float(v) * scale, int(p))
    return out


def wb(indicator, codes, year):
    """One request per economy: the World Bank API often times out on long multi-country requests."""
    out = {}
    for code in codes:
        url = f"https://api.worldbank.org/v2/country/{code}/indicator/{indicator}?date={year}&format=json"
        req = urllib.request.Request(url, headers={"User-Agent": "economic-atlas-wb-check"})
        for attempt in range(4):
            try:
                with urllib.request.urlopen(req, timeout=90) as r:
                    data = json.load(r)
                break
            except Exception as e:
                if attempt == 3:
                    print(f"  {code} {indicator}: no response ({e.__class__.__name__}), skipped", file=sys.stderr)
                    data = [None, None]
                else:
                    time.sleep(3 * (attempt + 1))
        for row in (data[1] if len(data) > 1 and data[1] else []):
            if row.get("value") is not None:
                out[code] = row["value"]
        print(f"  {indicator} {year} {code}", end="\r", file=sys.stderr, flush=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=float, default=0.0)
    a = ap.parse_args()
    rows = []
    for label, path, ind, scale in (("GDP US$bn", "rankings/gdp-by-country.html", "NY.GDP.MKTP.CD", 1.0),
                                    ("GDP per person US$", "rankings/gdp-per-capita-by-country.html", "NY.GDP.PCAP.CD", 1e9)):
        mine = site(path, scale)
        years = sorted({y for _, y in mine.values()})
        for y in years:
            codes = [ISO3[c] for c, (_, yy) in mine.items() if yy == y and ISO3.get(c)]
            theirs = wb(ind, codes, y)
            for c, (v, yy) in mine.items():
                if yy != y:
                    continue
                code = ISO3.get(c)
                w = theirs.get(code) if code else None
                if w is not None and ind == "NY.GDP.MKTP.CD":
                    w = w / 1e9
                gap = (v / w - 1) * 100 if w else None
                rows.append([label, c, y, round(v, 1), round(w, 1) if w else "", round(gap, 2) if gap is not None else ""])
    rows.sort(key=lambda r: -abs(r[5]) if r[5] != "" else 1)
    with open("wb_check.csv", "w", newline="") as f:
        csv.writer(f).writerows([["measure", "economy", "year", "atlas", "world_bank", "gap_pct"]] + rows)
    print(f"{'measure':20} {'economy':14} {'year':4} {'atlas':>12} {'World Bank':>12} {'gap %':>7}")
    for r in rows:
        if r[5] == "" or abs(r[5]) >= a.limit:
            print(f"{r[0]:20} {r[1]:14} {r[2]:4} {r[3]:>12} {str(r[4]):>12} {str(r[5]):>7}")
    within = sum(1 for r in rows if r[5] != "" and abs(r[5]) < 1)
    print(f"\n{len(rows)} comparisons, {within} within 1%, {sum(1 for r in rows if r[5] == '')} with no World Bank figure. wb_check.csv written.")


if __name__ == "__main__":
    sys.exit(main())
