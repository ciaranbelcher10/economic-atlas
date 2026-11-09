"""Fetch total population for every economy on the site and write data-population.json (v1.9.114).

Source: World Bank, Population, total (SP.POP.TOTL), annual, mid-year estimates, from 1960.
One request covers every economy. Used for the population metric and the Per capita toggle.

Not covered: Taiwan (the World Bank does not publish it; Taiwan already has partial coverage
by decision, 12 Oct 2026). Listed under "missing" so every page can say so.

Guards, so a bad response never replaces good data:
  - every value must be a positive whole number of people;
  - a year-on-year change bigger than MAX_JUMP is refused for that economy (a data break);
  - an economy that had data before and comes back empty or shorter keeps its previous points;
  - if fewer than MIN_ECONOMIES come back, or the newest year is too old, the file is not written.

Run:  python3 fetch_population.py          (skips if refreshed in the last REFRESH_HOURS)
      FORCE_POPULATION=1 python3 fetch_population.py   (always fetch)
"""
import datetime as dt
import json
import os
import sys

import requests

from fx_config import COUNTRY_FX

OUT = "data-population.json"
INDICATOR = "SP.POP.TOTL"
WB_URL = ("https://api.worldbank.org/v2/country/{codes}/indicator/" + INDICATOR +
          "?format=json&per_page=20000&date=1960:{year}")
UA = {"User-Agent": "economic-atlas-data-bot (+https://theeconomicatlas.com)"}
SOURCE = "World Bank, Population, total (SP.POP.TOTL), annual mid-year estimates"
MIN_ECONOMIES = 55          # 61 expected; allow a few to be temporarily absent
MAX_LAG_YEARS = 3           # newest year anywhere must be at most this many years old
MAX_JUMP = 0.12             # year-on-year change above 12% is treated as a break
REFRESH_HOURS = 20          # population changes once a year: refresh at most daily
NOT_COVERED = {"Taiwan": "The World Bank does not publish population for Taiwan."}
# Site code -> World Bank code, where they differ from the upper-cased site code.
WB_CODE = {"uk": "GB", "ez": "XC"}


def wb_codes():
    """{World Bank code: site name} for every economy the World Bank covers."""
    out = {}
    for name, (_cur, site, _q) in COUNTRY_FX.items():
        if name in NOT_COVERED:
            continue
        out[WB_CODE.get(site, site.upper())] = name
    return out


def parse(payload, code_to_name):
    """World Bank JSON -> {site name: [[year, people], ...]} (sorted, values as ints)."""
    if not isinstance(payload, list) or len(payload) < 2 or not isinstance(payload[1], list):
        raise ValueError("World Bank population: unexpected response shape")
    out = {}
    for row in payload[1]:
        code = (row.get("country") or {}).get("id") or row.get("countryiso3code")
        name = code_to_name.get(code)
        if name is None or row.get("value") is None:
            continue
        year, v = str(row.get("date")), float(row["value"])
        if not year.isdigit() or v <= 0:
            continue
        out.setdefault(name, []).append([year, int(round(v))])
    return {k: sorted(v) for k, v in out.items()}


def drop_breaks(name, pts):
    """Refuse an economy whose series has an implausible jump (keeps the data honest)."""
    for (y0, a), (y1, b) in zip(pts, pts[1:]):
        if int(y1) - int(y0) == 1 and abs(b / a - 1) > MAX_JUMP:
            print(f"  [refused] {name}: {y0}->{y1} changes {100 * (b / a - 1):+.1f}%")
            return None
    return pts


def merge(new, prev):
    """Keep previous points for any economy that came back empty, shorter or broken."""
    out, kept = {}, []
    for name in sorted(set(new) | set(prev)):
        n, p = new.get(name), prev.get(name)
        if n and (not p or (len(n) >= len(p) and n[-1][0] >= p[-1][0])):
            out[name] = n
        elif p:
            out[name] = p; kept.append(name)
    return out, kept


def build(payload, prev_doc, today=None):
    """Pure function (no network): the document to write, or raise if it must not be written."""
    today = today or dt.date.today()
    code_to_name = wb_codes()
    fresh = {}
    for name, pts in parse(payload, code_to_name).items():
        ok = drop_breaks(name, pts)
        if ok:
            fresh[name] = ok
    prev = (prev_doc or {}).get("countries", {})
    prev_pts = {k: v.get("points", []) for k, v in prev.items()}
    merged, kept = merge(fresh, prev_pts)
    if len(fresh) < MIN_ECONOMIES:
        raise ValueError(f"only {len(fresh)} economies came back (need {MIN_ECONOMIES}); not writing")
    newest = max(int(p[-1][0]) for p in merged.values())
    if newest < today.year - MAX_LAG_YEARS:
        raise ValueError(f"newest year is {newest}; too old, not writing")
    name_to_code = {v: k for k, v in code_to_name.items()}
    expected = sorted(code_to_name.values())
    return {
        "updated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": SOURCE,
        "unit": "people",
        "freq": "years",
        "countries": {n: {"wb_code": name_to_code.get(n), "points": merged[n]} for n in sorted(merged)},
        "missing": dict(sorted({**NOT_COVERED,
                                **{n: "No World Bank population figure came back for this economy."
                                   for n in expected if n not in merged}}.items())),
        "kept_previous": kept,
    }


def main():
    prev = {}
    if os.path.exists(OUT):
        try:
            prev = json.load(open(OUT, encoding="utf-8"))
        except ValueError:
            prev = {}
    if prev.get("updated") and not os.environ.get("FORCE_POPULATION"):
        try:
            age = dt.datetime.now(dt.timezone.utc) - dt.datetime.strptime(prev["updated"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
            if age < dt.timedelta(hours=REFRESH_HOURS):
                print(f"fetch_population: refreshed {age.seconds // 3600}h ago; skipping (population is annual)")
                return 0
        except ValueError:
            pass
    codes = ";".join(sorted(wb_codes()))
    url = WB_URL.format(codes=codes, year=dt.date.today().year)
    try:
        r = requests.get(url, timeout=90, headers=UA)
        print(f"  [wb] {INDICATOR} status={r.status_code}")
        r.raise_for_status()
        doc = build(r.json(), prev)
    except Exception as e:  # keep the previous file untouched
        print(f"fetch_population: FAILED, previous {OUT} kept ({e})")
        return 1
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
    c = doc["countries"]
    print(f"fetch_population: {len(c)} economies, {sum(len(v['points']) for v in c.values())} points, "
          f"newest {max(v['points'][-1][0] for v in c.values())}; missing: {', '.join(doc['missing']) or 'none'}"
          + (f"; kept previous for {', '.join(doc['kept_previous'])}" if doc["kept_previous"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
