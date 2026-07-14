"""Fetch economic series for Economic Atlas.

UK  -> data.json     (ONS + OECD + World Bank + Bank of England; no keys)
US  -> data-us.json  (FRED + OECD + World Bank; FRED needs a free API key)

Run:  python3 fetch_data.py
The FRED key is read from the FRED_API_KEY environment variable. In GitHub
Actions, add it as a repository secret and expose it in the workflow:
    env:
      FRED_API_KEY: ${{ secrets.FRED_API_KEY }}
Without the key, the UK build runs in full and the US build writes only its
keyless series (OECD, World Bank); FRED series are skipped with a notice.
"""

from __future__ import annotations

import csv
import io
import json
import os
import sys
from datetime import datetime, timezone

import requests

UA = {"User-Agent": "economic-atlas/0.2"}

# ===========================================================================
# UK — ONS series (verified page URIs)
# ===========================================================================
UK_SERIES = {
    "gdp_level": (["/economy/grossdomesticproductgdp/timeseries/abmi/pn2"],
                  "GDP, chained volume measure (ABMI)", "£m"),
    "gdp_growth": (["/economy/grossdomesticproductgdp/timeseries/ihyq/pn2"],
                   "GDP growth, quarter on quarter (IHYQ)", "%"),
    "productivity": (["/employmentandlabourmarket/peopleinwork/labourproductivity/timeseries/lzvb/prdy"],
                     "Output per hour worked, index 2023=100 (LZVB)", "index"),
    "unemployment": (["/employmentandlabourmarket/peoplenotinwork/unemployment/timeseries/mgsx/lms"],
                     "Unemployment rate, 16+, SA (MGSX)", "%"),
    "employment": (["/employmentandlabourmarket/peopleinwork/employmentandemployeetypes/timeseries/lf24/lms"],
                   "Employment rate, 16-64, SA (LF24)", "%"),
    "inactivity": (["/employmentandlabourmarket/peoplenotinwork/economicinactivity/timeseries/lf2s/lms"],
                   "Economic inactivity rate, 16-64, SA (LF2S)", "%"),
    "cpi": (["/economy/inflationandpriceindices/timeseries/d7g7/mm23"],
            "CPI annual rate, all items (D7G7)", "%"),
    "cpih": (["/economy/inflationandpriceindices/timeseries/l55o/mm23"],
             "CPIH annual rate, all items (L55O)", "%"),
    "cpi_mom": (["/economy/inflationandpriceindices/timeseries/d7oe/mm23"],
                "CPI monthly rate, all items (D7OE)", "%"),
    "debt_gdp": (["/economy/governmentpublicsectorandtaxes/publicsectorfinance/timeseries/hf6x/pusf"],
                 "Public sector net debt ex banks, % of GDP (HF6X)", "%"),
    "net_debt": (["/economy/governmentpublicsectorandtaxes/publicsectorfinance/timeseries/hf6w/pusf"],
                 "Public sector net debt ex banks, £bn (HF6W)", "£bn"),
    "deficit": (["/economy/governmentpublicsectorandtaxes/publicsectorfinance/timeseries/dzls/pusf"],
                "Public sector net borrowing ex banks (DZLS)", "£m"),
    "current_account": (["/economy/nationalaccounts/balanceofpayments/timeseries/aa6h/bop",
                         "/economy/nationalaccounts/balanceofpayments/timeseries/aa6h/pb"],
                        "Current account balance, % of GDP (AA6H)", "%"),
    "trade_balance": (["/economy/nationalaccounts/balanceofpayments/timeseries/ikbj/mret"],
                      "Total trade balance, goods and services, SA (IKBJ)", "£m"),
    "exports": (["/economy/nationalaccounts/balanceofpayments/timeseries/ikbh/mret"],
                "Total exports, goods and services, SA (IKBH)", "£m"),
    "imports": (["/economy/nationalaccounts/balanceofpayments/timeseries/ikbi/mret"],
                "Total imports, goods and services, SA (IKBI)", "£m"),
}

ONS_ENDPOINTS = [
    "https://api.beta.ons.gov.uk/v1/data?uri={uri}",
    "https://www.ons.gov.uk{uri}/data",
]

MONTHS = {m: i for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN",
     "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], start=1)}


def parse_ons_date(raw: str, freq: str) -> str:
    raw = raw.strip()
    if freq == "months":
        year, mon = raw.split()
        return f"{year}-{MONTHS[mon.upper()]:02d}"
    if freq == "quarters":
        return raw.replace(" ", "-")
    return raw


def fetch_ons(uris: list[str]) -> tuple[str, list, str | None] | None:
    last_error = None
    for uri in uris:
        for template in ONS_ENDPOINTS:
            try:
                r = requests.get(template.format(uri=uri), timeout=30, headers=UA)
                r.raise_for_status()
                payload = r.json()
            except Exception as exc:
                last_error = exc
                continue
            for freq in ("months", "quarters", "years"):
                obs = payload.get(freq)
                if obs:
                    points = []
                    for o in obs:
                        try:
                            points.append([parse_ons_date(o["date"], freq),
                                           float(o["value"])])
                        except (KeyError, ValueError):
                            continue
                    points.sort(key=lambda p: p[0])
                    nxt = (payload.get("description") or {}).get("nextRelease")
                    return freq, points, (nxt or None)
    if last_error:
        raise last_error
    return None


# ===========================================================================
# US — FRED series (IDs verified against fred.stlouisfed.org)
# ===========================================================================
US_FRED = {
    # key: (fred_id, freq, label, unit)
    "gdp_nominal": ("GDP", "quarters",
                    "GDP, current dollars, seasonally adjusted annual rate", "$bn"),
    "gdp_real": ("GDPC1", "quarters",
                 "Real GDP, chained 2017 dollars, SAAR", "$bn"),
    "gdp_growth": ("A191RL1Q225SBEA", "quarters",
                   "Real GDP growth, annualised quarter on quarter", "%"),
    "productivity": ("OPHNFB", "quarters",
                     "Nonfarm business output per hour, index", "index"),
    "unemployment": ("UNRATE", "months", "Unemployment rate, SA", "%"),
    "employment": ("EMRATIO", "months", "Employment-population ratio, SA", "%"),
    "participation": ("CIVPART", "months",
                      "Labor force participation rate, SA", "%"),
    "fed_funds": ("FEDFUNDS", "months", "Effective federal funds rate", "%"),
    "debt_gdp": ("GFDEGDQ188S", "quarters",
                 "Federal debt, total public debt as % of GDP", "%"),
    "deficit": ("MTSDS133FMS", "months",
                "Federal surplus or deficit (-), monthly, NSA", "$m"),
    "trade_balance": ("BOPGSTB", "months",
                      "Trade balance, goods and services, SA", "$m"),
    "exports": ("BOPTEXP", "months",
                "Exports of goods and services, SA", "$m"),
    "imports": ("BOPTIMP", "months",
                "Imports of goods and services, SA", "$m"),
    "cpi_index": ("CPIAUCSL", "months", "CPI, all urban consumers, SA", "index"),
}

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"


def fred_period(date_str: str, freq: str) -> str:
    year, month = date_str[:4], int(date_str[5:7])
    if freq == "quarters":
        return f"{year}-Q{(month - 1) // 3 + 1}"
    return f"{year}-{month:02d}"


def fetch_fred(series_id: str, freq: str, api_key: str) -> list:
    params = {"series_id": series_id, "api_key": api_key,
              "file_type": "json", "observation_start": "1970-01-01"}
    r = requests.get(FRED_BASE, params=params, timeout=60, headers=UA)
    r.raise_for_status()
    obs = r.json().get("observations", [])
    points = []
    for o in obs:
        try:
            if o.get("value") in (None, "", "."):
                continue
            points.append([fred_period(o["date"], freq), float(o["value"])])
        except (KeyError, ValueError):
            continue
    points.sort(key=lambda p: p[0])
    return points


def pct_change(points: list, lag: int) -> list:
    out = []
    for i in range(lag, len(points)):
        prev = points[i - lag][1]
        if prev:
            out.append([points[i][0],
                        round((points[i][1] / prev - 1) * 100, 2)])
    return out


# ===========================================================================
# OECD business confidence — parameterised by country
# ===========================================================================
OECD_BASE = "https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_CLI"


def fetch_oecd_bci(ref_area: str) -> tuple[str, list] | None:
    queries = [
        f"{OECD_BASE}/{ref_area}.M.BCICP...AA...H?format=csvfile&startPeriod=1990",
        f"{OECD_BASE}/{ref_area}.M.BCICP......?format=csvfile&startPeriod=1990",
        f"{OECD_BASE}/all?format=csvfile&startPeriod=2000",
    ]
    for url in queries:
        try:
            r = requests.get(url, timeout=60, headers=UA)
            r.raise_for_status()
        except Exception:
            continue
        try:
            rows = {}
            for row in csv.DictReader(io.StringIO(r.text)):
                low = {k.upper(): (v or "") for k, v in row.items() if k}
                if low.get("REF_AREA", ref_area) != ref_area:
                    continue
                if low.get("MEASURE", "BCICP") != "BCICP":
                    continue
                if (low.get("FREQ") or low.get("FREQUENCY") or "M") != "M":
                    continue
                period, value = low.get("TIME_PERIOD", ""), low.get("OBS_VALUE", "")
                if period and value:
                    try:
                        rows[period] = float(value)
                    except ValueError:
                        continue
            if rows:
                return "months", sorted(([p, v] for p, v in rows.items()),
                                        key=lambda x: x[0])
        except Exception:
            continue
    return None


# ===========================================================================
# World Bank — parameterised by country and indicator
# ===========================================================================
def fetch_worldbank(country: str, indicator: str) -> tuple[str, list] | None:
    url = (f"https://api.worldbank.org/v2/country/{country}/indicator/"
           f"{indicator}?format=json&per_page=200")
    r = requests.get(url, timeout=60, headers=UA)
    r.raise_for_status()
    payload = r.json()
    if not isinstance(payload, list) or len(payload) < 2 or not payload[1]:
        return None
    points = []
    for row in payload[1]:
        try:
            if row.get("value") is None:
                continue
            points.append([str(row["date"]), round(float(row["value"]), 2)])
        except (KeyError, ValueError, TypeError):
            continue
    if not points:
        return None
    points.sort(key=lambda p: p[0])
    return "years", points


# ===========================================================================
# Bank of England Bank Rate — IADB CSV
# ===========================================================================
BOE_URL = ("https://www.bankofengland.co.uk/boeapps/iadb/fromshowcolumns.asp"
           "?csv.x=yes&Datefrom=01/Jan/1975&Dateto=now"
           "&SeriesCodes=IUDBEDR&CSVF=TN&UsingCodes=Y&VPD=Y&VFD=N")


def fetch_boe_rate() -> tuple[str, list] | None:
    r = requests.get(BOE_URL, timeout=60, headers=UA)
    r.raise_for_status()
    monthly = {}
    for row in csv.reader(io.StringIO(r.text)):
        if len(row) < 2:
            continue
        raw_date, raw_val = row[0].strip(), row[1].strip()
        try:
            value = float(raw_val)
        except ValueError:
            continue
        period = None
        parts = raw_date.replace("-", " ").split()
        if len(parts) == 3:
            if parts[0].isdigit() and len(parts[0]) == 4:
                period = f"{parts[0]}-{int(parts[1]):02d}"
            elif parts[2].isdigit() and len(parts[2]) == 4:
                mon = MONTHS.get(parts[1][:3].upper())
                if mon:
                    period = f"{parts[2]}-{mon:02d}"
        if period:
            monthly[period] = value
    if not monthly:
        return None
    return "months", sorted(([p, v] for p, v in monthly.items()),
                            key=lambda x: x[0])


# ===========================================================================
# Build helpers
# ===========================================================================
def load_previous(path: str) -> dict:
    try:
        with open(path) as f:
            old = json.load(f)
        return {k: v["points"][-1][0]
                for k, v in old.get("series", {}).items() if v.get("points")}
    except Exception:
        return {}


def finalise(out: dict, previous: dict, path: str, failures: list) -> None:
    try:
        with open(path) as f:
            prev_meta = json.load(f).get("new_points_meta", {})
    except Exception:
        prev_meta = {}
    now_iso = out["updated"]
    new_meta = {}
    for k, v in out["series"].items():
        period = v["points"][-1][0]
        prior = prev_meta.get(k)
        if prior and prior.get("period") == period:
            new_meta[k] = {"period": period, "first_seen": prior["first_seen"]}
        else:
            new_meta[k] = {"period": period, "first_seen": now_iso}
    out["new_points_meta"] = new_meta

    def _age_days(iso):
        try:
            t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
            return (datetime.now(timezone.utc) - t).total_seconds() / 86400
        except Exception:
            return 999

    out["new_points"] = {k: m["period"] for k, m in new_meta.items()
                          if _age_days(m["first_seen"]) < 2}
    if out["new_points"]:
        print("Fresh (< 2 days old): " + ", ".join(
            f"{k} ({p})" for k, p in out["new_points"].items()))
    with open(path, "w") as f:
        json.dump(out, f)
    print(f"Wrote {path} with {len(out['series'])} series.")
    if failures:
        print(f"Missing: {', '.join(failures)} — the page will still render.")


def stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ok_line(key: str, points: list, freq: str) -> None:
    print(f"  ok  {key:<16} {len(points):>5} observations "
          f"({points[0][0]} to {points[-1][0]}, {freq})")


# ===========================================================================
# UK build
# ===========================================================================
def build_uk() -> bool:
    print("== United Kingdom ==")
    previous = load_previous("data.json")
    out = {"updated": stamp(), "sample": False, "series": {}}
    failures = []
    for key, (uris, label, unit) in UK_SERIES.items():
        try:
            result = fetch_ons(uris)
            if result is None:
                raise ValueError("no observations in response")
            freq, points, nxt = result
            out["series"][key] = {"label": label, "unit": unit,
                                  "freq": freq, "points": points}
            if nxt:
                out["series"][key]["next"] = nxt
            ok_line(key, points, freq)
        except Exception as exc:
            failures.append(key)
            print(f"FAIL  {key:<16} {exc}")

    extras = [
        ("business_confidence", lambda: fetch_oecd_bci("GBR"),
         "Business confidence indicator, LT avg = 100 (OECD BCICP)", "index"),
        ("fdi", lambda: fetch_worldbank("GBR", "BX.KLT.DINV.WD.GD.ZS"),
         "FDI net inflows, % of GDP (World Bank)", "%"),
        ("boe_rate", fetch_boe_rate,
         "Official Bank Rate (Bank of England IUDBEDR)", "%"),
    ]
    for key, fn, label, unit in extras:
        try:
            result = fn()
            if result is None:
                raise ValueError("no usable response")
            freq, points = result
            out["series"][key] = {"label": label, "unit": unit,
                                  "freq": freq, "points": points}
            ok_line(key, points, freq)
        except Exception as exc:
            failures.append(key)
            print(f"FAIL  {key:<16} {exc}")

    if not out["series"]:
        print("UK: nothing fetched.")
        return False
    finalise(out, previous, "data.json", failures)
    return True


# ===========================================================================
# US build
# ===========================================================================
def build_us() -> bool:
    print("\n== United States ==")
    previous = load_previous("data-us.json")
    out = {"updated": stamp(), "sample": False, "series": {}}
    failures = []
    api_key = os.environ.get("FRED_API_KEY", "").strip()

    if not api_key:
        print("note  FRED_API_KEY not set — skipping FRED series.")
        print("      Get a free key at fred.stlouisfed.org, then add it as a")
        print("      GitHub Actions secret named FRED_API_KEY (see README).")
        failures.extend(k for k in US_FRED if k != "cpi_index")
    else:
        for key, (fred_id, freq, label, unit) in US_FRED.items():
            try:
                points = fetch_fred(fred_id, freq, api_key)
                if not points:
                    raise ValueError("no observations in response")
                out["series"][key] = {"label": label, "unit": unit,
                                      "freq": freq, "points": points}
                ok_line(key, points, freq)
            except Exception as exc:
                failures.append(key)
                print(f"FAIL  {key:<16} {exc}")

        # Derive CPI rates from the index, then drop the raw index
        idx = out["series"].pop("cpi_index", None)
        if idx:
            yoy = pct_change(idx["points"], 12)
            mom = pct_change(idx["points"], 1)
            if yoy:
                out["series"]["cpi"] = {
                    "label": "CPI, all items, year on year (from CPIAUCSL)",
                    "unit": "%", "freq": "months", "points": yoy}
                ok_line("cpi", yoy, "months")
            if mom:
                out["series"]["cpi_mom"] = {
                    "label": "CPI, all items, month on month (from CPIAUCSL)",
                    "unit": "%", "freq": "months", "points": mom}
                ok_line("cpi_mom", mom, "months")

    extras = [
        ("business_confidence", lambda: fetch_oecd_bci("USA"),
         "Business confidence indicator, LT avg = 100 (OECD BCICP)", "index"),
        ("fdi", lambda: fetch_worldbank("USA", "BX.KLT.DINV.WD.GD.ZS"),
         "FDI net inflows, % of GDP (World Bank)", "%"),
        ("current_account", lambda: fetch_worldbank("USA", "BN.CAB.XOKA.GD.ZS"),
         "Current account balance, % of GDP (World Bank)", "%"),
    ]
    for key, fn, label, unit in extras:
        try:
            result = fn()
            if result is None:
                raise ValueError("no usable response")
            freq, points = result
            out["series"][key] = {"label": label, "unit": unit,
                                  "freq": freq, "points": points}
            ok_line(key, points, freq)
        except Exception as exc:
            failures.append(key)
            print(f"FAIL  {key:<16} {exc}")

    if not out["series"]:
        print("US: nothing fetched.")
        return False
    finalise(out, previous, "data-us.json", failures)
    return True


def main() -> int:
    uk_ok = build_uk()
    us_ok = build_us()
    return 0 if (uk_ok or us_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
