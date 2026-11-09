"""
Merge World Bank population into each economy's data file as the series "population" (v1.9.115).

fetch_population.py keeps one file for every economy (data-population.json). The pages, the
indicator-page generator, Compare, Dashboard and Chartmaker all read each economy's own
data-<code>.json, so this step copies that economy's population into it as an ordinary series:
every surface then treats population like any other metric, with no second file to load.

Runs after every fetch script and before "Commit updated data" (like stamp_fx.py), so a fetch
script that rebuilds its file without the series gets it back in the same run. Idempotent.
If data-population.json is missing or unreadable, nothing is changed.
"""
import json
import os
import re
import sys

from fx_config import COUNTRY_FX

SRC = "data-population.json"
KEY = "population"
GDP_KEY = "gdp_per_capita"
# Published as quarters at an annual rate (a year is the mean of its quarters, not the sum);
# the same list the indicator generator and country pages use.
GDP_ANNUAL_RATE = {"US", "Japan"}
LABEL = "Population, total, mid-year estimate, annual (World Bank SP.POP.TOTL)"


def series_for(entry, updated):
    return {"label": LABEL, "unit": "people", "freq": "years",
            "points": [[str(y), int(v)] for y, v in entry["points"]],
            "source": "World Bank", "confirmed_at": (updated[:16] + "Z") if updated else None}


def calendar_year_gdp(gdp, country):
    """{year: GDP} for complete calendar years only: an annual figure, or all four quarters
    (summed, or averaged where quarters are published at an annual rate). A year with any
    quarter missing is left out (v1.9.116: never a part year)."""
    freq, out = gdp.get("freq"), {}
    pts = [p for p in gdp.get("points", []) if p and p[1] is not None]
    if freq == "years":
        for y, v in pts:
            if re.fullmatch(r"\d{4}", str(y)):
                out[str(y)] = float(v)
        return out
    if freq == "quarters":
        by = {}
        for per, v in pts:
            m = re.fullmatch(r"(\d{4})-Q([1-4])", str(per))
            if m:
                by.setdefault(m.group(1), {})[m.group(2)] = float(v)
        for y, qs in by.items():
            if len(qs) == 4:
                tot = sum(qs.values())
                out[y] = tot / 4 if country in GDP_ANNUAL_RATE else tot
    return out


def scale_of(unit):
    m = re.search(r"(tn|bn|m|k)$", str(unit or "").strip())
    return {"tn": 1e12, "bn": 1e9, "m": 1e6, "k": 1e3}[m.group(1)] if m else 1


def gdp_per_capita_series(gdp, pop_points, country, updated):
    """GDP per person for each complete calendar year that has that SAME year's population
    (exact-year rule: no other year's population is ever used). Whole currency units."""
    if not gdp or "%" in str(gdp.get("unit", "")):
        return None
    years = calendar_year_gdp(gdp, country)
    pop = {str(y): v for y, v in pop_points if v}
    scale = scale_of(gdp.get("unit"))
    pts = [[y, round(years[y] * scale / pop[y])] for y in sorted(years) if y in pop]
    if len(pts) < 2:
        return None
    return {"label": "GDP per person, current prices, calendar year (GDP divided by World Bank population)",
            "unit": re.sub(r"(tn|bn|m|k)$", "", str(gdp.get("unit", "")).strip()), "freq": "years",
            "points": pts, "derived": True, "confirmed_at": (updated[:16] + "Z") if updated else None}


def main(root="."):
    path = os.path.join(root, SRC)
    try:
        pop = json.load(open(path, encoding="utf-8"))
        countries, updated = pop["countries"], pop.get("updated")
    except (OSError, ValueError, KeyError) as e:
        print(f"merge_population: {SRC} unavailable ({e}); data files left as they are")
        return 0
    done, skipped = 0, []
    for name, (_cur, code, _q) in COUNTRY_FX.items():
        f = os.path.join(root, f"data-{code}.json")
        if name not in countries or not os.path.exists(f):
            skipped.append(name); continue
        d = json.load(open(f, encoding="utf-8"))
        new = series_for(countries[name], updated)
        gpc = gdp_per_capita_series(d.get("series", {}).get("gdp_level"), new["points"], name, updated)
        S = d.setdefault("series", {})
        if S.get(KEY) == new and S.get(GDP_KEY) == gpc:
            continue
        S[KEY] = new
        if gpc:
            S[GDP_KEY] = gpc
        else:
            S.pop(GDP_KEY, None)
        with open(f, "w", encoding="utf-8") as fh:
            json.dump(d, fh, ensure_ascii=False, separators=(",", ":"))
        done += 1
    print(f"merge_population: population written to {done} data file(s); not covered: {', '.join(skipped) or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
