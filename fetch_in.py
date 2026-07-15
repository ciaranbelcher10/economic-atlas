"""Fetch India economic series and write data-in.json.

Run:  FRED_API_KEY=yourkey python3 fetch_in.py
Sources: FRED (free key required: fred.stlouisfed.org), World Bank.
In GitHub Actions the key comes from the FRED_API_KEY repository secret.

VERIFICATION NOTES (checked against each series' own FRED page before wiring in):
- gdp_level (NGDPNSAXDCINQ) / gdp_real (NGDPRNSAXDCINQ): IMF IFS quarterly,
  confirmed live through Q4 2025 / Q1 2026 respectively.
- India has NO live monthly/quarterly CPI series on FRED. The obvious mirror,
  CPALTT01INM659N, stopped updating in Mar 2025 ("Next Release Date: Not
  Available") -- the same dead-OECD-mirror failure mode as Japan's CPI.
  OECD's own live system clearly still has current India CPI (their monthly
  press releases cite it), but the correct live SDMX query wasn't verified
  end-to-end before this file was written, so CPI is deliberately NOT wired
  in here rather than shipping a guessed query. Needs its own verification
  pass -- see README "Known data gaps".
- India has NO live headline unemployment series on FRED at all (only an old
  World Bank youth-unemployment annual figure). Deliberately omitted rather
  than mislabelling a poor substitute as "unemployment".
- No live RBI policy (repo) rate series exists on FRED for India. Using the
  10-year government bond yield (INDIRLTLT01STM) instead, honestly labelled
  as a bond yield rather than mislabelled as the policy rate. Confirmed live
  through May 2026.
- exports (XTEXVA01INM667S) / imports (XTIMVA01INM664S): OECD merchandise
  trade via FRED, confirmed live (exports to Mar 2026, imports to Dec 2025).
  Same "plain US dollars, not millions" unit bug as Japan/Eurozone's "667S"
  trade family -- confirmed via the sibling trade-balance series showing a
  raw value of -19,520,830,000.00000 for a single month -- so scale=1e-6 is
  applied here too, from day one, rather than discovered later as a bug.
- debt_gdp (GGGDTAINA188N) / deficit (GGNLBAINA188N): IMF WEO annual, both
  confirmed live through 2023 -- the same ~2-year lag as Japan's equivalent
  series, which is normal for annual WEO figures, not a stale mirror.
- business_confidence: OECD BCICP via SDMX, same multi-query fallback
  pattern already used for the other four countries. Best-effort: if IND
  isn't covered by this indicator, the tile/chart simply won't render
  (existing site behaviour for any missing series).
- unemployment (PLFS via MoSPI's own eSankhyiki API): MoSPI relaunched PLFS
  in Jan 2025 specifically to publish MONTHLY all-India unemployment
  (Current Weekly Status), replacing the old annual-only cadence. Confirmed
  via the official swagger spec (api.mospi.gov.in/api/plfs/getData,
  frequency_code=3 = Monthly, data from 2025 onwards) and the official CPI
  API user manual PDF, which documents the real flow: sign up ONCE with a
  username/password (api/users/usersignup), then log in on every single
  run (api/users/login) to get a fresh access token -- tokens expire after
  30 minutes, so they can't be stored as a static secret the way
  FRED_API_KEY is. This script logs in itself each run using
  MOSPI_USERNAME/MOSPI_PASSWORD secrets -- see README "Setting up the
  MoSPI API key". The login step was VERIFIED against a real account on
  2026-07-15: it returns {"response": "<token string>"} directly, NOT
  {"response": {"token": ...}} as the official example script (Login.py)
  assumes -- mospi_login() parses this correctly and defensively handles
  both shapes. Signing in did NOT require an OTP/2FA step despite the
  account having two_factor enabled at signup. The data-fetch call itself
  (using that token in an "authorization" header, per the official
  example) has NOT yet been independently confirmed to return real PLFS
  records -- treat the next live run as the remaining verification step
  and check the Actions log.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

import requests

# key: (fred_id, freq 'm'|'q'|'a', label, unit, transform None|'yoy'|'mom'|'qoq', scale)
FRED_SERIES = {
    "gdp_level": ("NGDPNSAXDCINQ", "q", "GDP, nominal", "\u20b9m", None, 1.0),
    "gdp_real": ("NGDPRNSAXDCINQ", "q", "Real GDP", "\u20b9m", None, 1.0),
    "gdp_growth": ("NGDPRNSAXDCINQ", "q", "Real GDP growth, QoQ", "%", "qoq", 1.0),
    "bond_yield_10y": ("INDIRLTLT01STM", "m", "10-year government bond yield", "%", None, 1.0),
    "debt_gdp": ("GGGDTAINA188N", "a", "General government gross debt, % of GDP", "%", None, 1.0),
    "deficit": ("GGNLBAINA188N", "a", "General government net lending/borrowing, % of GDP", "%", None, 1.0),
    "exports": ("XTEXVA01INM667S", "m", "Exports of goods, $", "$m", None, 1e-6),
    "imports": ("XTIMVA01INM664S", "m", "Imports of goods, $", "$m", None, 1e-6),
}

FRED_URL = ("https://api.stlouisfed.org/fred/series/observations"
            "?series_id={sid}&api_key={key}&file_type=json"
            "&observation_start=1970-01-01")


def fred_period(date: str, freq: str) -> str:
    y, m = date[:4], int(date[5:7])
    if freq == "a":
        return y
    if freq == "q":
        return f"{y}-Q{(m - 1) // 3 + 1}"
    return f"{y}-{m:02d}"  # monthly, and daily reduced to months


def fetch_fred(sid: str, freq: str, key: str) -> list:
    r = requests.get(FRED_URL.format(sid=sid, key=key), timeout=60,
                     headers={"User-Agent": "economic-atlas/0.1"})
    r.raise_for_status()
    points = []
    for o in r.json().get("observations", []):
        if o.get("value") in (None, "", "."):
            continue
        try:
            points.append([fred_period(o["date"], freq), float(o["value"])])
        except (KeyError, ValueError):
            continue
    points.sort(key=lambda p: p[0])
    dedup = {}
    for p, v in points:          # daily series reduce to last value per month
        dedup[p] = v
    return sorted([[p, v] for p, v in dedup.items()], key=lambda x: x[0])


def transform(points: list, kind: str | None) -> list:
    if kind not in ("yoy", "mom", "qoq"):
        return points
    lag = 12 if kind == "yoy" else 1
    return [[points[i][0], round((points[i][1] / points[i - lag][1] - 1) * 100, 2)]
            for i in range(lag, len(points)) if points[i - lag][1]]


# ---- OECD business confidence (India) — free SDMX API, no key ----
OECD_BASE = "https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_CLI"
IN_AREAS = ("IND",)
OECD_QUERIES = [
    f"{OECD_BASE}/IND.M.BCICP...AA...H?format=csvfile&startPeriod=1990",
    f"{OECD_BASE}/IND.M.BCICP......?format=csvfile&startPeriod=1990",
    f"{OECD_BASE}/all?format=csvfile&startPeriod=2000",
]


def fetch_oecd_bci() -> list | None:
    import csv
    import io
    for url in OECD_QUERIES:
        try:
            r = requests.get(url, timeout=60,
                             headers={"User-Agent": "economic-atlas/0.1"})
            r.raise_for_status()
        except Exception:
            continue
        try:
            rows = {}
            for row in csv.DictReader(io.StringIO(r.text)):
                low = {k.upper(): (v or "") for k, v in row.items() if k}
                if low.get("REF_AREA", "IND") not in IN_AREAS:
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
                return sorted([[p, v] for p, v in rows.items()], key=lambda x: x[0])
        except Exception:
            continue
    return None


# ---- MoSPI PLFS unemployment (India) — official govt API. Tokens expire
# after 30 minutes, so this logs in fresh on every run using MOSPI_USERNAME/
# MOSPI_PASSWORD secrets, rather than storing a static token. Sign-up (a
# one-time step only you can do) is documented in README "Setting up the
# MoSPI API key".
MOSPI_LOGIN_URL = "https://api.mospi.gov.in/api/users/login"
MOSPI_DATA_URL = "https://api.mospi.gov.in/api/plfs/getData"


def mospi_login(username: str, password: str) -> str | None:
    r = requests.post(MOSPI_LOGIN_URL, json={"username": username, "password": password},
                      timeout=30, headers={"User-Agent": "economic-atlas/0.1"})
    r.raise_for_status()
    payload = r.json()
    # VERIFIED against a real login call (2026-07-15): the "response" field is
    # the token itself, as a raw encrypted-looking string -- e.g.
    # {"msg": "Login successful", "statusCode": true, "response": "<iv>:<ciphertext>"}
    # NOT an object with a nested "token" key as the official example script
    # (Login.py) assumes. Handle both shapes defensively in case this changes.
    resp = payload.get("response")
    if isinstance(resp, str):
        return resp
    if isinstance(resp, dict):
        return resp.get("token")
    return payload.get("token")


def fetch_plfs_unemployment(token: str) -> list | None:
    params = {
        "indicator_code": "3",     # UR = Unemployment Rate
        "frequency_code": "3",     # Monthly (data from 2025 onwards)
        "state_code": "99",        # All India
        "gender_code": "3",        # Person (all genders combined)
        "age_code": "4",           # All ages
        "sector_code": "3",        # Rural + Urban combined
        "limit": "200",
        "Format": "JSON",
    }
    r = requests.get(MOSPI_DATA_URL, params=params, timeout=60,
                     headers={"User-Agent": "economic-atlas/0.1",
                              "authorization": token})
    r.raise_for_status()
    payload = r.json()
    records = payload.get("data") or payload.get("records") or payload
    if not isinstance(records, list):
        return None
    points = {}
    for row in records:
        try:
            year = str(row.get("year") or row.get("Year"))
            month = int(row.get("month_code") or row.get("Month") or row.get("month"))
            value = row.get("value") if "value" in row else row.get("Value")
            if value is None:
                continue
            period = f"{year}-{month:02d}"
            points[period] = float(value)
        except (TypeError, ValueError):
            continue
    return sorted([[p, v] for p, v in points.items()], key=lambda x: x[0]) or None



WB_URL = ("https://api.worldbank.org/v2/country/IND/indicator/"
          "{code}?format=json&per_page=200")


def fetch_worldbank(code: str) -> list | None:
    r = requests.get(WB_URL.format(code=code), timeout=60,
                     headers={"User-Agent": "economic-atlas/0.1"})
    r.raise_for_status()
    payload = r.json()
    if not isinstance(payload, list) or len(payload) < 2 or not payload[1]:
        return None
    points = []
    for row in payload[1]:
        try:
            if row.get("value") is None:
                continue
            points.append([str(row["date"]), float(row["value"])])
        except (KeyError, ValueError, TypeError):
            continue
    points.sort(key=lambda p: p[0])
    return points or None


def main() -> int:
    out = {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sample": False,
        "series": {},
    }
    failures = []

    key = os.environ.get("FRED_API_KEY")
    if not key:
        print("WARN  no FRED_API_KEY set — FRED series will be skipped.")
    else:
        for name, (sid, freq, label, unit, tf, scale) in FRED_SERIES.items():
            try:
                raw = fetch_fred(sid, freq, key)
                if scale != 1.0:
                    raw = [[p, v * scale] for p, v in raw]
                points = transform(raw, tf)
                if not points:
                    raise ValueError("no observations")
                fr = {"m": "months", "d": "months", "q": "quarters", "a": "years"}[freq]
                out["series"][name] = {"label": f"{label} ({sid})", "unit": unit,
                                       "freq": fr, "points": points}
                print(f"  ok  {name:<16} {len(points):>5} observations "
                      f"({points[0][0]} to {points[-1][0]}, {fr})")
            except Exception as exc:
                failures.append(name)
                print(f"FAIL  {name:<16} {exc}")

    extras = [
        ("business_confidence", lambda: fetch_oecd_bci(),
         "Business confidence indicator, LT avg = 100 (OECD BCICP)", "index", "months"),
        ("fdi", lambda: fetch_worldbank("BX.KLT.DINV.WD.GD.ZS"),
         "FDI net inflows, % of GDP (World Bank)", "%", "years"),
        ("current_account", lambda: fetch_worldbank("BN.CAB.XOKA.GD.ZS"),
         "Current account balance, % of GDP (World Bank)", "%", "years"),
    ]
    for name, fn, label, unit, fr in extras:
        try:
            points = fn()
            if not points:
                raise ValueError("no usable response")
            out["series"][name] = {"label": label, "unit": unit,
                                   "freq": fr, "points": points}
            print(f"  ok  {name:<16} {len(points):>5} observations "
                  f"({points[0][0]} to {points[-1][0]}, {fr})")
        except Exception as exc:
            failures.append(name)
            print(f"FAIL  {name:<16} {exc}")

    mospi_user = os.environ.get("MOSPI_USERNAME")
    mospi_pass = os.environ.get("MOSPI_PASSWORD")
    if not mospi_user or not mospi_pass:
        print("note  no MOSPI_USERNAME/MOSPI_PASSWORD set — unemployment will "
              "be skipped (see README for how to register).")
        failures.append("unemployment")
    else:
        try:
            token = mospi_login(mospi_user, mospi_pass)
            if not token:
                raise ValueError("login succeeded but no token in response")
            points = fetch_plfs_unemployment(token)
            if not points:
                raise ValueError("no usable response")
            out["series"]["unemployment"] = {
                "label": "Unemployment rate, Current Weekly Status (PLFS/MoSPI)",
                "unit": "%", "freq": "months", "points": points}
            print(f"  ok  {'unemployment':<16} {len(points):>5} observations "
                  f"({points[0][0]} to {points[-1][0]}, months)")
        except Exception as exc:
            failures.append("unemployment")
            print(f"FAIL  {'unemployment':<16} {exc}")

    if not out["series"]:
        print("\nNothing fetched.")
        return 1

    if "exports" in out["series"] and "imports" in out["series"]:
        imp = dict(out["series"]["imports"]["points"])
        tb = [[p, round(x - imp[p], 1)]
              for p, x in out["series"]["exports"]["points"] if p in imp]
        if tb:
            out["series"]["trade_balance"] = {
                "label": "Trade balance, goods (exports minus imports)", "unit": "$m",
                "freq": "months", "points": tb}
            print(f"  ok  {'trade_balance':<16} {len(tb):>5} observations (derived)")

    try:
        with open("data-in.json") as f:
            prev_full = json.load(f)
    except Exception:
        prev_full = {}
    prev_meta = prev_full.get("new_points_meta")
    # migrating from no meta file (first-ever run for this country) or a
    # corrupted one: back-date everything to the last known-good run instead
    # of "now", so switching this on doesn't falsely flag every series as
    # freshly released. On a genuine first-ever run there is no prior run to
    # back-date to, so this simply falls through to "now" for that one run
    # only -- expected and harmless for a brand-new country page.
    migrating = prev_meta is None
    backdate = prev_full.get("updated")
    prev_meta = prev_meta or {}
    now_iso = out["updated"]
    new_meta = {}
    for k, v in out["series"].items():
        period = v["points"][-1][0]
        prior = prev_meta.get(k)
        if prior and prior.get("period") == period:
            new_meta[k] = {"period": period, "first_seen": prior["first_seen"]}
        elif migrating and backdate:
            new_meta[k] = {"period": period, "first_seen": backdate}
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

    with open("data-in.json", "w") as f:
        json.dump(out, f)
    print(f"\nWrote data-in.json with {len(out['series'])} series.")
    if failures:
        print(f"Missing: {', '.join(failures)} — the page will still render.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
