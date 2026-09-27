"""
Daily 10-year government bond yields for the country-page Markets tiles:
writes data-bond-<suffix>.json for each country below.

Only official sources that publish a free daily series and allow reuse:

  US      FRED DGS10: US Treasury 10-year constant-maturity yield (Treasury
          data, public domain). Needs FRED_API_KEY.
  Canada  Bank of Canada Valet API, BD.CDN.10YR.DQ.YLD: Government of Canada
          10-year benchmark bond yield. No key.
  Japan   Ministry of Finance JGB interest rates, 10-year constant maturity:
          jgbcme_all.csv (history, refreshed monthly) + jgbcme.csv (current
          month), both published at 9:30am Tokyo the next business day.

  UK      Bank of England database, IUDMNPY: 10-year nominal par yield on
          British Government Securities, daily. Used with the Bank's
          permission (its database terms otherwise exclude commercial use).

Deliberately NOT here (v1.6.17):
  Euro area The ECB publishes its 10-year benchmark only monthly; the daily
            benchmark data are licensed and not redistributed. The daily ECB
            yield-curve par yield is a different, model-based measure, so
            putting it on the same tile would mix two definitions.

The tile is the only thing this feeds. Charts, Compare, rankings and
indicator pages keep the harmonised monthly series (OECD, and the ECB for the
euro area), so every country is still compared on one definition.

Each file: {"country", "key": "bond_yield_10y", "title", "points": [[date,
pct], ...] (last three years of trading days), "source", "source_short",
"confirmed_at"}. A source that fails keeps the previous file untouched, so
its stamp ages and the tile's light turns amber.
"""
import csv
import io
import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone

import requests

UA = {"User-Agent": "economic-atlas/0.1 (+https://theeconomicatlas.com)"}
YEARS = 3


def _cutoff():
    return (date.today() - timedelta(days=365 * YEARS)).isoformat()


def _check(points, name):
    if len(points) < 20:
        raise ValueError(f"{name}: only {len(points)} observations")
    bad = [p for p in points if not (-2 < p[1] < 25)]
    if bad:
        raise ValueError(f"{name}: implausible yield {bad[0]}")
    return points


def fetch_us():
    key = os.environ.get("FRED_API_KEY", "")
    if not key:
        raise RuntimeError("FRED_API_KEY not set")
    url = ("https://api.stlouisfed.org/fred/series/observations?series_id=DGS10"
           f"&api_key={key}&file_type=json&observation_start={_cutoff()}")
    r = requests.get(url, timeout=60, headers=UA)
    r.raise_for_status()
    pts = [[o["date"], round(float(o["value"]), 3)] for o in r.json().get("observations", [])
           if o.get("value") not in (None, "", ".")]
    return _check(sorted(pts), "DGS10")


def fetch_ca():
    sid = "BD.CDN.10YR.DQ.YLD"
    url = f"https://www.bankofcanada.ca/valet/observations/{sid}/json?start_date={_cutoff()}"
    r = requests.get(url, timeout=60, headers=UA)
    r.raise_for_status()
    pts = []
    for o in r.json().get("observations", []):
        v = (o.get(sid) or {}).get("v")
        if v in (None, "", "Bank holiday"):
            continue
        try:
            pts.append([o["d"], round(float(v), 3)])
        except (ValueError, KeyError):
            continue
    return _check(sorted(pts), sid)


def _mof_rows(text):
    """Rows of the MoF CSV after its 'Date,1Y,...' header, as (iso date, 10Y)."""
    lines = text.splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith("Date,"))
    reader = csv.DictReader(io.StringIO("\n".join(lines[start:])))
    out = []
    for row in reader:
        d, v = (row.get("Date") or "").strip(), (row.get("10Y") or "").strip()
        m = re.fullmatch(r"(\d{4})/(\d{1,2})/(\d{1,2})", d)
        if not m or v in ("", "-"):
            continue
        out.append([f"{m[1]}-{int(m[2]):02d}-{int(m[3]):02d}", round(float(v), 3)])
    return out


def fetch_jp():
    base = "https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/"
    by = {}
    for url in (base + "historical/jgbcme_all.csv", base + "jgbcme.csv"):
        r = requests.get(url, timeout=90, headers=UA)
        r.raise_for_status()
        for d, v in _mof_rows(r.content.decode("utf-8", "replace")):
            by[d] = v               # current-month file wins on overlap
    cut = _cutoff()
    return _check(sorted([d, v] for d, v in by.items() if d >= cut), "MoF 10Y")


def _boe_date(s):
    s = s.strip()
    for fmt in ("%d %b %Y", "%d/%b/%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def fetch_uk():
    sid = "IUDMNPY"
    start = datetime.strptime(_cutoff(), "%Y-%m-%d").strftime("%d/%b/%Y")
    url = ("https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp"
           f"?csv.x=yes&Datefrom={start}&Dateto=now&SeriesCodes={sid}&CSVF=TN&UsingCodes=Y&VPD=Y&VFD=N")
    # The Bank's database refuses requests without a browser-style agent.
    headers = {"User-Agent": "Mozilla/5.0 (compatible; economic-atlas/0.1; +https://theeconomicatlas.com)",
               "Accept": "text/csv,text/plain,*/*"}
    r = requests.get(url, timeout=60, headers=headers)
    r.raise_for_status()
    text = r.content.decode("utf-8-sig", "replace")
    if "<html" in text[:500].lower():
        raise ValueError("BoE returned an HTML page, not CSV")
    pts = []
    for row in csv.reader(io.StringIO(text)):
        if len(row) < 2:
            continue
        d = _boe_date(row[0])
        if not d:
            continue                      # header row
        try:
            pts.append([d, round(float(row[1]), 4)])
        except ValueError:
            continue
    return _check(sorted(pts), sid)


SOURCES = {
    "UK": ("uk", "10-year gilt yield", fetch_uk,
           "Bank of England, 10-year nominal par yield on British Government Securities, daily (series IUDMNPY). Used with the Bank's permission.",
           "Bank of England \u00b7 IUDMNPY, daily"),
    "US": ("us", "10-year Treasury yield", fetch_us,
           "US Treasury 10-year constant-maturity yield, daily (FRED series DGS10).",
           "US Treasury \u00b7 FRED DGS10, daily"),
    "Canada": ("ca", "10-year bond yield", fetch_ca,
               "Bank of Canada, Government of Canada 10-year benchmark bond yield, daily (Valet series BD.CDN.10YR.DQ.YLD).",
               "Bank of Canada \u00b7 BD.CDN.10YR.DQ.YLD, daily"),
    "Japan": ("jp", "10-year JGB yield", fetch_jp,
              "Ministry of Finance, Japan: 10-year JGB interest rate on a constant maturity basis, daily (jgbcme.csv).",
              "Japan MoF \u00b7 10-year JGB, daily"),
}


def main(base_dir="."):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    failures = 0
    for country, (suffix, title, fn, source, short) in SOURCES.items():
        path = os.path.join(base_dir, f"data-bond-{suffix}.json")
        try:
            pts = fn()
        except Exception as exc:
            failures += 1
            print(f"FAIL  {country}: {exc} (previous file, if any, kept with its old stamp)")
            continue
        try:
            with open(path) as f:
                prev = json.load(f)
            if prev.get("points") and pts[-1][0] < prev["points"][-1][0]:
                print(f"KEPT  {country}: new data ends {pts[-1][0]}, previous {prev['points'][-1][0]}")
                continue
        except Exception:
            pass
        with open(path, "w") as f:
            json.dump({"country": country, "key": "bond_yield_10y", "title": title, "points": pts,
                       "source": source, "source_short": short, "confirmed_at": now}, f, separators=(",", ":"))
        print(f"  ok  {country:<7} {pts[-1][1]}% on {pts[-1][0]} ({len(pts)} trading days)")
    return 1 if failures == len(SOURCES) else 0


if __name__ == "__main__":
    sys.exit(main())
