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
import glob
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
    # v1.9.125: an economy whose population comes from elsewhere (Cyprus: Eurostat, same area as GDP) says so
    return {"label": entry.get("label") or LABEL, "unit": "people", "freq": "years",
            "points": [[str(y), int(v)] for y, v in entry["points"]],
            "source": entry.get("source") or "World Bank", "confirmed_at": (updated[:16] + "Z") if updated else None}


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


def pc_round(x):
    """Whole currency units, except below 100, where three significant figures
    are kept. v1.9.138: Israel's new-shekel GDP per person for 1960-1964 is
    under ₪1 (hyperinflation and the 1985 redenomination) and rounded to 0."""
    if x is None:
        return None
    if abs(x) >= 100:
        return round(x)
    from math import floor, log10
    return round(x, max(0, 2 - int(floor(log10(abs(x)))))) if x else 0


def gdp_per_capita_series(gdp, pop_points, country, updated, pop_source="World Bank"):
    """GDP per person for each complete calendar year that has that SAME year's population
    (exact-year rule: no other year's population is ever used). Whole currency units (see pc_round)."""
    if not gdp or "%" in str(gdp.get("unit", "")):
        return None
    years = calendar_year_gdp(gdp, country)
    pop = {str(y): v for y, v in pop_points if v}
    scale = scale_of(gdp.get("unit"))
    pts = [[y, pc_round(years[y] * scale / pop[y])] for y in sorted(years) if y in pop]
    if len(pts) < 2:
        return None
    return {"label": f"GDP per person, current prices, calendar year (GDP divided by {pop_source} population)",
            "unit": re.sub(r"(tn|bn|m|k)$", "", str(gdp.get("unit", "")).strip()), "freq": "years",
            "points": pts, "derived": True, "confirmed_at": (updated[:16] + "Z") if updated else None}


def _annual_totals(series):
    """{year: total} for complete calendar years. Annual points as they are;
    quarters summed when all four are present; a trailing four-quarter sum
    (gdp_real_annual) read at Q4."""
    if not series or not series.get("points"):
        return {}
    pts = [(str(p), v) for p, v in series["points"] if v is not None]
    if series.get("freq") == "years":
        return {p[:4]: v for p, v in pts if re.fullmatch(r"\d{4}", p)}
    if "trailing 4-quarter sum" in str(series.get("label", "")).lower():
        return {p[:4]: v for p, v in pts if p.endswith("-Q4")}
    by = {}
    for p, v in pts:
        m = re.fullmatch(r"(\d{4})-Q([1-4])", p)
        if m:
            by.setdefault(m.group(1), {})[m.group(2)] = v
    return {y: sum(q.values()) for y, q in by.items() if len(q) == 4}


def real_usd_anchor(nominal, real):
    """How real GDP becomes US dollars: constant prices of an anchor year,
    converted at that year's average exchange rate (the World Bank's method
    for its constant-dollar series, which anchors on 2015). The anchor is
    the latest complete calendar year both series cover; the deflator is
    nominal / real GDP in that year. Real GDP x deflator equals nominal GDP
    in the anchor year, and growth in dollars equals published real growth.

    v1.9.138: the site converted real GDP in base-year prices (Argentina
    2004 pesos, Turkey 2009 lira, Brazil 1995 reais) at the latest year's
    exchange rate, which put Argentina's real GDP at 0.09% of its nominal
    GDP in dollars. Returns {"year", "deflator"} or None when the two series
    are not in the same currency."""
    if not nominal or not real:
        return None
    strip = lambda u: re.sub(r"(tn|bn|m|k)$", "", str(u or "").strip())
    if strip(nominal.get("unit")) != strip(real.get("unit")):
        return None
    n, r = _annual_totals(nominal), _annual_totals(real)
    years = sorted(y for y in n if y in r and r[y])
    if not years:
        return None
    y = years[-1]
    return {"year": y, "deflator": round(n[y] * scale_of(nominal.get("unit")) / (r[y] * scale_of(real.get("unit"))), 6)}

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
        gpc = gdp_per_capita_series(d.get("series", {}).get("gdp_level"), new["points"], name, updated, new["source"])
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
    # v1.9.138: every economy's real GDP gets its US$ anchor, population or not (Taiwan has none).
    anchored = 0
    for f in sorted(glob.glob(os.path.join(root, "data-??.json"))):
        d = json.load(open(f, encoding="utf-8"))
        S = d.get("series", {})
        changed = False
        for rk in ("gdp_real", "gdp_real_annual"):
            if S.get(rk):
                by = real_usd_anchor(S.get("gdp_level"), S[rk])
                if S[rk].get("usd_anchor") != by:
                    changed = True
                    if by:
                        S[rk]["usd_anchor"] = by
                    else:
                        S[rk].pop("usd_anchor", None)
        if changed:
            with open(f, "w", encoding="utf-8") as fh:
                json.dump(d, fh, ensure_ascii=False, separators=(",", ":"))
            anchored += 1
    print(f"merge_population: real GDP US$ anchor updated in {anchored} data file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
