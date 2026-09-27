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

  Euro area (v1.6.20) ECB yield curve, YC.B.U2.EUR.4F.G_N_C.SV_C_YM.PY_10Y:
          10-year par yield fitted to all euro-area central government bonds,
          daily. A model-based measure, NOT the ECB 10-year benchmark the
          monthly chart shows, so it gets its own key (bond_par_10y) and its
          own tile, labelled as such, and never replaces the benchmark.

Long-term yields, monthly (v1.6.20), for the four countries with no OECD
10-year series: Indonesia, Morocco, Singapore, Thailand. IMF Monetary and
Financial Statistics (MFS_IR dataflow, sovereign bond yield
S13BOND_RT_PT_A_PT), as each central bank reports it. The maturity follows
the national definition and is not guaranteed to be 10 years, so these are
stored as bond_yield_lt and kept out of the 10-year rankings and Compare.

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


def fetch_ez_par():
    url = ("https://data-api.ecb.europa.eu/service/data/YC/"
           f"B.U2.EUR.4F.G_N_C.SV_C_YM.PY_10Y?format=csvdata&startPeriod={_cutoff()}")
    r = requests.get(url, timeout=60, headers=dict(UA, Accept="text/csv"))
    r.raise_for_status()
    pts = []
    for row in csv.DictReader(io.StringIO(r.content.decode("utf-8-sig", "replace"))):
        d, v = (row.get("TIME_PERIOD") or "").strip(), (row.get("OBS_VALUE") or "").strip()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) and v not in ("", "NaN"):
            pts.append([d, round(float(v), 3)])
    return _check(sorted(pts), "ECB YC PY_10Y")


def fetch_imf_bond(iso3):
    """Monthly sovereign bond yield from IMF MFS_IR (the pipeline already
    reaches api.imf.org for Morocco's CPI). Rejects a dead series."""
    url = ("https://api.imf.org/external/sdmx/3.0/data/dataflow/IMF.STA/MFS_IR/~/"
           f"{iso3}.S13BOND_RT_PT_A_PT.M?c[TIME_PERIOD]=ge:1990-M01")
    r = requests.get(url, timeout=60, headers=dict(UA, Accept="text/csv"))
    print(f"  [imf-bond] {iso3} status={r.status_code}")
    r.raise_for_status()
    pts = []
    for row in csv.DictReader(io.StringIO(r.text)):
        per = (row.get("TIME_PERIOD") or "").strip().replace("-M", "-")
        v = (row.get("OBS_VALUE") or "").strip()
        if re.fullmatch(r"\d{4}-\d{2}", per) and v:
            try:
                pts.append([per, round(float(v), 3)])
            except ValueError:
                pass
    pts = sorted(pts)
    if len(pts) < 24:
        raise ValueError(f"IMF MFS_IR {iso3}: only {len(pts)} monthly observations")
    last = datetime.strptime(pts[-1][0] + "-01", "%Y-%m-%d").date()
    if (date.today() - last).days > 400:
        raise ValueError(f"IMF MFS_IR {iso3}: series ends {pts[-1][0]}, too old to show as current")
    bad = [p for p in pts if not (-2 < p[1] < 40)]
    if bad:
        raise ValueError(f"IMF MFS_IR {iso3}: implausible yield {bad[0]}")
    return pts


_LT_DESC = ("{c} central bank's long-term government bond yield as reported to the IMF (Monetary and Financial "
            "Statistics, sovereign bond yield, monthly). The maturity follows the national definition and is not "
            "necessarily 10 years, so it is not included in the 10-year rankings or in Compare.")

def fetch_oecd_irlt(iso3):
    """OECD long-term interest rate (IRLT, the 10-year government bond
    yield the OECD publishes for members and some partner economies), from
    the Short-Term Economic Statistics financial-market dataflow. Monthly
    where published, quarterly otherwise. Same concept as the OECD series
    every other country page uses, but read directly from OECD rather than
    FRED because FRED carries no mirror for these economies."""
    url = ("https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_FINMARK/"
           f"{iso3}..IRLT......?format=csvfile&startPeriod=1990")
    r = requests.get(url, timeout=60, headers=dict(UA, Accept="text/csv"))
    print(f"  [oecd-irlt] {iso3} status={r.status_code}")
    r.raise_for_status()
    by_freq = {"M": [], "Q": []}
    for row in csv.DictReader(io.StringIO(r.text)):
        f = (row.get("FREQ") or "").strip()
        per = (row.get("TIME_PERIOD") or "").strip()
        v = (row.get("OBS_VALUE") or "").strip()
        if f not in by_freq or not v:
            continue
        if not (re.fullmatch(r"\d{4}-\d{2}", per) or re.fullmatch(r"\d{4}-Q[1-4]", per)):
            continue
        try:
            by_freq[f].append([per, round(float(v), 3)])
        except ValueError:
            pass
    freq, pts = ("months", sorted(by_freq["M"])) if len(by_freq["M"]) >= 24 else ("quarters", sorted(by_freq["Q"]))
    if len(pts) < 8:
        raise ValueError(f"OECD IRLT {iso3}: only {len(pts)} observations")
    last = pts[-1][0]
    y, rest = int(last[:4]), last[5:]
    m = (int(rest[1]) * 3) if rest.startswith("Q") else int(rest)
    if (date.today() - date(y, m, 1)).days > 400:
        raise ValueError(f"OECD IRLT {iso3}: series ends {last}, too old to show as current")
    bad = [p for p in pts if not (-2 < p[1] < 40)]
    if bad:
        raise ValueError(f"OECD IRLT {iso3}: implausible yield {bad[0]}")
    return freq, pts


OECD_IRLT = {"Indonesia": ("id", "IDN")}


_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def fetch_singstat_sgs10():
    """Singapore 10-year government bond yield, monthly, from the Department
    of Statistics' open TableBuilder API (table M700071, "Interest Rates",
    no key). The table defines it as the end-of-month rate: the average of
    closing bid rates quoted by SGS primary dealers (MAS data)."""
    url = "https://tablebuilder.singstat.gov.sg/api/table/tabledata/M700071?limit=5000"
    r = requests.get(url, timeout=60, headers=dict(UA, Accept="application/json"))
    print(f"  [singstat] M700071 status={r.status_code}")
    r.raise_for_status()
    body = r.json()

    def rows(node):
        if isinstance(node, dict):
            if "rowText" in node and "columns" in node:
                yield node
            for v in node.values():
                yield from rows(v)
        elif isinstance(node, list):
            for v in node:
                yield from rows(v)

    match = [row for row in rows(body) if "10-year bond yield" in str(row.get("rowText", "")).lower()]
    if not match:
        top = list(body)[:5] if isinstance(body, dict) else type(body).__name__
        raise ValueError(f"SingStat M700071: no '10-Year Bond Yield' row (top-level keys {top})")
    pts = []
    for c in match[0]["columns"]:
        k, v = str(c.get("key", "")).strip(), str(c.get("value", "")).strip()
        m = re.fullmatch(r"(\d{4})\s+([A-Za-z]{3})", k)
        if not m or v in ("", "na", "-"):
            continue
        try:
            pts.append([f"{m[1]}-{_MONTHS[m[2].lower()]:02d}", round(float(v), 3)])
        except (ValueError, KeyError):
            continue
    pts.sort()
    if len(pts) < 24:
        raise ValueError(f"SingStat M700071: only {len(pts)} monthly observations")
    y, mo = map(int, pts[-1][0].split("-"))
    if (date.today() - date(y, mo, 1)).days > 400:
        raise ValueError(f"SingStat M700071: series ends {pts[-1][0]}, too old to show as current")
    return pts

LONG_TERM = {
    "Indonesia": ("id", "IDN"), "Morocco": ("ma", "MAR"),
    "Singapore": ("sg", "SGP"), "Thailand": ("th", "THA"),
}


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


def _jobs():
    for country, (suffix, title, fn, source, short) in SOURCES.items():
        yield country, suffix, "bond_yield_10y", "days", title, fn, source, short, None
    yield ("Eurozone", "ez", "bond_par_10y", "days", "10-year par yield (daily)", fetch_ez_par,
           "ECB yield curve, 10-year par yield fitted to all euro-area central government bonds, daily "
           "(series YC.B.U2.EUR.4F.G_N_C.SV_C_YM.PY_10Y). A model-based measure, not the ECB 10-year benchmark "
           "shown in the chart, which is published only monthly.",
           "ECB yield curve \u00b7 PY_10Y, daily", None)
    for country, (suffix, iso3) in OECD_IRLT.items():
        yield (country, suffix, "bond_yield_lt", "months", "10-year bond yield (OECD)",
               (lambda i=iso3: fetch_oecd_irlt(i)),
               f"OECD Short-Term Economic Statistics, long-term interest rate (IRLT), {iso3}: the 10-year government bond yield as reported to the OECD.",
               "OECD \u00b7 IRLT, long-term interest rate",
               f"The yield on {country}'s 10-year government bonds as reported to the OECD. {country} is not an OECD member, so this "
               "comes from the OECD's partner-economy data rather than the harmonised series the 10-year rankings use, and is kept out of them.")
    yield ("Singapore", "sg", "bond_yield_lt", "months", "10-year bond yield", fetch_singstat_sgs10,
           "Singapore Department of Statistics, TableBuilder table M700071 (Interest Rates, monthly): "
           "Government Securities 10-Year Bond Yield, end of month, the average of closing bid rates quoted by "
           "SGS primary dealers (Monetary Authority of Singapore data).",
           "SingStat \u00b7 M700071, end of month",
           "The yield on Singapore's 10-year government bonds at the end of each month. Singapore is not an OECD "
           "member, so this comes from its own statistics office rather than the harmonised OECD series the "
           "10-year rankings use, and is kept out of them.")
    for country, (suffix, iso3) in LONG_TERM.items():
        if country in OECD_IRLT or country == "Singapore":
            continue
        yield (country, suffix, "bond_yield_lt", "months", "Long-term bond yield",
               (lambda i=iso3: fetch_imf_bond(i)),
               f"IMF Monetary and Financial Statistics (MFS_IR), sovereign bond yield {iso3}.S13BOND_RT_PT_A_PT.M, monthly, as reported by the central bank.",
               "IMF MFS \u00b7 sovereign bond yield, monthly", _LT_DESC.format(c=country + "'s"))


def main(base_dir="."):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    failures = 0
    jobs = list(_jobs())
    for country, suffix, key, freq, title, fn, source, short, desc in jobs:
        path = os.path.join(base_dir, f"data-bond-{suffix}.json")
        try:
            pts = fn()
            if isinstance(pts, tuple):
                freq, pts = pts
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
            json.dump({"country": country, "key": key, "freq": freq, "title": title, "points": pts,
                       "description": desc, "source": source, "source_short": short, "confirmed_at": now},
                      f, separators=(",", ":"))
        print(f"  ok  {country:<9} {key:<14} {pts[-1][1]}% at {pts[-1][0]} ({len(pts)} observations)")
    return 1 if failures == len(jobs) else 0


if __name__ == "__main__":
    sys.exit(main())
