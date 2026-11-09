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
import sys

from fx_config import COUNTRY_FX

SRC = "data-population.json"
KEY = "population"
LABEL = "Population, total, mid-year estimate, annual (World Bank SP.POP.TOTL)"


def series_for(entry, updated):
    return {"label": LABEL, "unit": "people", "freq": "years",
            "points": [[str(y), int(v)] for y, v in entry["points"]],
            "source": "World Bank", "confirmed_at": (updated[:16] + "Z") if updated else None}


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
        if d.setdefault("series", {}).get(KEY) == new:
            continue
        d["series"][KEY] = new
        with open(f, "w", encoding="utf-8") as fh:
            json.dump(d, fh, ensure_ascii=False, separators=(",", ":"))
        done += 1
    print(f"merge_population: population written to {done} data file(s); not covered: {', '.join(skipped) or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
