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
- exports (XTEXVA01INM667S): OECD merchandise trade via FRED, confirmed
  live (to Mar/Apr 2026), genuinely in US dollars (UNIT_MEASURE: USD_EXC
  on FRED's own OECD data filter for this series).
- FIXED IN 7.6.3 -- real bug found via a user screenshot showing an
  impossible trade balance: the imports series originally used here
  (XTIMVA01INM664S) is NOT dollar-denominated -- its OECD data filter
  shows UNIT_MEASURE: XDC (domestic currency, i.e. rupees), unlike the
  matching exports series which is genuinely USD_EXC (US dollars). Every
  previous "verified" check confirmed each series was individually live,
  but never cross-checked that exports and imports shared the same
  currency before subtracting one from the other -- exports (USD) minus
  imports (rupees, scaled as if millions-of-dollars) produced a nonsense
  trade balance. Rather than hunt for another cryptic imports series ID
  and risk repeating the mistake, trade_balance now comes directly from
  XTNTVA01INM667S -- a single, self-contained, confirmed dollar-
  denominated (USD_EXC) trade balance series -- the exact series used to
  originally diagnose the "667S family reports plain USD" scale bug.
  Imports on their own are no longer shown (same call already made for
  Canada and Australia, where no live dollar-denominated imports
  component could be found either) -- known gap, honestly labelled on
  the page rather than silently dropped.
- gdp_level/gdp_real scale, also FIXED IN 7.6.3: these IMF IFS series are
  the literal quarterly level, NOT a seasonally-adjusted-annual-rate like
  the UK/US series -- displaying the raw quarterly figure as "annual GDP"
  understated nothing but was labelled wrong; worse, the display code
  divided by 1,000 assuming the value was already in $bn (matching the
  original four countries' convention) when it's actually in millions of
  RUPEES, inflating the headline figure by roughly 1000x and mislabelling
  the currency as $ throughout. Fixed by rolling up 4 quarters (the
  existing annualGDP() helper, already used by the UK page) and dividing
  by 1e6 for millions-to-trillions, with the currency symbol corrected to
  actually match the source data (Rs/C$/A$, not $, since no FX conversion
  is performed).
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
    # 8.3.0: India's IMF IFS GDP series is NOT seasonally adjusted (the "NSA"
    # in the FRED ID). QoQ on unadjusted data measures the season, not the
    # economy -- the site was showing a sawtooth of -7.4% .. +12.4% as
    # "growth". YoY (yoy_q, lag 4) is the only meaningful rate here; the
    # India page labels were changed to match.
    "gdp_growth": ("NGDPRNSAXDCINQ", "q", "Real GDP growth, YoY", "%", "yoy_q", 1.0),
    "bond_yield_10y": ("INDIRLTLT01STM", "m", "10-year government bond yield", "%", None, 1.0),
    "debt_gdp": ("GGGDTAINA188N", "a", "General government gross debt, % of GDP", "%", None, 1.0),
    "deficit": ("GGNLBAINA188N", "a", "General government net lending/borrowing, % of GDP", "%", None, 1.0),
    "exports": ("XTEXVA01INM667S", "m", "Exports of goods, $", "$m", None, 1e-6),
    "trade_balance": ("XTNTVA01INM667S", "m", "Trade balance, goods, $", "$m", None, 1e-6),
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
    # yoy = monthly data (lag 12); yoy_q = quarterly data (lag 4).
    if kind not in ("yoy", "yoy_q", "mom", "qoq"):
        return points
    lag = 12 if kind == "yoy" else (4 if kind == "yoy_q" else 1)
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
            print(f"  [oecd-bci] status={r.status_code}")
            r.raise_for_status()
        except Exception as exc:
            print(f"  [oecd-bci] request failed: {exc}")
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
            print(f"  [oecd-bci] {len(rows)} matching rows after filtering -- no usable data in this response")
        except Exception as exc:
            print(f"  [oecd-bci] parsing failed: {exc}")
            continue
    return None


# ---- OECD live CPI (8.3.0) -- same verified fetcher as JP/AU/CA/KR, with
# staleness guard and wildcard-methodology fallback. India's FRED CPI mirror
# died in March 2025; OECD's own DF_PRICES_ALL still publishes current India
# CPI. Check the Actions log for [oecd-cpi] IND lines to verify the first run.
OECD_PRICES_BASE = "https://sdmx.oecd.org/public/rest/data/OECD.SDD.TPS,DSD_PRICES@DF_PRICES_ALL,1.0"


def fetch_oecd_cpi(areas: tuple, freq: str) -> list | None:
    import csv
    import io

    lag = 4 if freq == "Q" else 12
    # Staleness guard (8.3.0): a fetch that "succeeds" but returns a
    # discontinued series must be REJECTED, not shipped. Japan's pinned
    # national-methodology CPI in DF_PRICES_ALL ends June 2021 (the 2015=100
    # base was retired when Japan rebased to 2020=100 in Aug 2021), and the
    # old code happily served it as current -- the live site showed -0.5%
    # deflation for Japan in July 2026 when actual CPI was +1.5%.
    max_age_days = 460 if freq == "Q" else 370

    def period_age_days(period: str) -> float:
        try:
            if "-Q" in period:
                y, q = period.split("-Q")
                dt = datetime(int(y), int(q) * 3, 1, tzinfo=timezone.utc)
            else:
                y, m = period.split("-")[:2]
                dt = datetime(int(y), int(m), 1, tzinfo=timezone.utc)
            return (datetime.now(timezone.utc) - dt).total_seconds() / 86400
        except Exception:
            return 0.0  # unparseable period -> don't reject on age alone

    def to_yoy(pts):
        return [[pts[i][0], round((pts[i][1] / pts[i - lag][1] - 1) * 100, 2)]
                for i in range(lag, len(pts)) if pts[i - lag][1]] or None

    def parse_groups(text: str, area: str, tag: str) -> dict:
        # Group rows by (METHODOLOGY, ADJUSTMENT) so a wildcard query that
        # returns several series variants doesn't get scrambled into one dict
        # (the pre-8.3.0 parser keyed on TIME_PERIOD alone, silently
        # overwriting one methodology's values with another's).
        reader = list(csv.DictReader(io.StringIO(text)))
        if reader:
            print(f"  [oecd-cpi] {tag} {len(reader)} CSV rows; "
                  f"columns: {list(reader[0].keys())}")
        else:
            print(f"  [oecd-cpi] {tag} 0 CSV rows; "
                  f"raw response (first 300 chars): {text[:300]!r}")
            return {}
        groups: dict = {}
        for row in reader:
            low = {k.upper(): (v or "") for k, v in row.items() if k}
            if low.get("REF_AREA", area) != area:
                continue
            period, value = low.get("TIME_PERIOD", ""), low.get("OBS_VALUE", "")
            if not (period and value):
                continue
            gkey = (low.get("METHODOLOGY", "?"), low.get("ADJUSTMENT", "?"))
            try:
                groups.setdefault(gkey, {})[period] = float(value)
            except ValueError:
                continue
        return groups

    for area in areas:
        # Pass 1: pinned national-methodology combos (verified working for
        # AU/CA/KR). Pass 2: wildcard METHODOLOGY and ADJUSTMENT -- for
        # countries where the pinned combo resolves to a discontinued base
        # series (Japan), ask the dataset for every variant it has and pick
        # the freshest. UNIT_MEASURE must still match TRANSFORMATION: GY
        # (year-on-year growth) pairs with PA (percentage), _Z (raw level)
        # pairs with IX (index); GY+IX 404s -- confirmed against
        # DF_PRICES_ALL, see the 7.6.12 diagnostic run.
        attempts = (
            ("PA", "GY", False, "N", "N"),
            ("IX", "_Z", True, "N", "N"),
            ("PA", "GY", False, "", ""),
            ("IX", "_Z", True, "", ""),
        )
        for unit_measure, trans_code, needs_yoy, meth, adj in attempts:
            tag = f"{area}.{meth or '*'}.{unit_measure}.{trans_code}"
            url = (f"{OECD_PRICES_BASE}/{area}.{freq}.{meth}.CPI."
                   f"{unit_measure}._T.{adj}.{trans_code}"
                   f"?format=csvfile&startPeriod=2015")
            try:
                r = requests.get(url, timeout=60,
                                 headers={"User-Agent": "economic-atlas/0.1"})
                print(f"  [oecd-cpi] {tag} status={r.status_code}")
                r.raise_for_status()
            except Exception as exc:
                print(f"  [oecd-cpi] {tag} request failed: {exc}")
                continue
            try:
                groups = parse_groups(r.text, area, tag)
                if not groups:
                    print(f"  [oecd-cpi] {tag} 0 usable rows after filtering "
                          f"(REF_AREA/TIME_PERIOD/OBS_VALUE mismatch)")
                    continue
                # Freshest last-period wins; longer history breaks ties.
                candidates = []
                for gkey, rows in groups.items():
                    pts = sorted([[p, v] for p, v in rows.items()],
                                 key=lambda x: x[0])
                    candidates.append((pts[-1][0], len(pts), gkey, pts))
                candidates.sort(key=lambda t: (t[0], t[1]), reverse=True)
                for last_period, n, gkey, pts in candidates:
                    age = period_age_days(last_period)
                    if age > max_age_days:
                        print(f"  [oecd-cpi] {tag} {gkey} REJECTED stale: "
                              f"{n} points ending {last_period} "
                              f"({age:.0f} days old, limit {max_age_days})")
                        continue
                    out = pts if not needs_yoy else to_yoy(pts)
                    if not out:
                        print(f"  [oecd-cpi] {tag} {gkey} YoY transform "
                              f"produced no points -- skipping")
                        continue
                    print(f"  [oecd-cpi] {tag} {gkey} SUCCESS: {len(out)} "
                          f"points, {out[0][0]} to {out[-1][0]}")
                    return out
                print(f"  [oecd-cpi] {tag} all series variants stale or "
                      f"unusable -- trying next combo")
                continue
            except Exception as exc:
                print(f"  [oecd-cpi] {tag} parsing failed: {exc}")
                continue
    return None


# ---- MoSPI PLFS unemployment (India) — official govt API. Tokens expire
# after 30 minutes, so this logs in fresh on every run using MOSPI_USERNAME/
# MOSPI_PASSWORD secrets, rather than storing a static token. Sign-up (a
# one-time step only you can do) is documented in README "Setting up the
# MoSPI API key".
#
# CONFIRMED on a real run (2026-07-15): api.mospi.gov.in presents a
# self-signed certificate, which Python rejects by default
# (CERTIFICATE_VERIFY_FAILED). This isn't a mistake on our end -- MoSPI's
# OWN official reference client (github.com/nso-india/esankhyiki-mcp,
# mospi/client.py) explicitly disables certificate verification for calls
# to this exact host, so verify=False here matches the platform owner's
# own documented workaround for their infrastructure, not a shortcut we
# invented. Scoped only to these two MoSPI calls -- every other fetch in
# this file (FRED, OECD, World Bank) still verifies certificates normally.
MOSPI_LOGIN_URL = "https://api.mospi.gov.in/api/users/login"
MOSPI_DATA_URL = "https://api.mospi.gov.in/api/plfs/getData"


# CONFIRMED on a live 8.3.0 run (2026-07-19): both MoSPI calls now also fail
# with "SSLError: UNSAFE_LEGACY_RENEGOTIATION_DISABLED" -- OpenSSL 3 refuses
# legacy TLS renegotiation by default, and MoSPI's server still relies on it.
# Fix is a dedicated requests.Session whose HTTPAdapter carries an SSLContext
# with OP_LEGACY_SERVER_CONNECT set, scoped only to api.mospi.gov.in (same
# scoping discipline as the verify=False cert-verification exception above --
# every other fetch in this file still uses plain requests with normal TLS).
def _mospi_session() -> "requests.Session":
    import ssl
    from requests.adapters import HTTPAdapter
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    ctx.options |= ssl.OP_LEGACY_SERVER_CONNECT

    class _LegacyTLSAdapter(HTTPAdapter):
        def init_poolmanager(self, *args, **kwargs):
            kwargs["ssl_context"] = ctx
            return super().init_poolmanager(*args, **kwargs)

        def proxy_manager_for(self, *args, **kwargs):
            kwargs["ssl_context"] = ctx
            return super().proxy_manager_for(*args, **kwargs)

    session = requests.Session()
    session.mount("https://api.mospi.gov.in", _LegacyTLSAdapter())
    return session


def mospi_login(username: str, password: str) -> str | None:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    session = _mospi_session()
    r = session.post(MOSPI_LOGIN_URL, json={"username": username, "password": password},
                      timeout=30, headers={"User-Agent": "economic-atlas/0.1"},
                      verify=False)
    print(f"  [mospi] login status={r.status_code}")
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
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    params = {
        "indicator_code": "3",     # UR = Unemployment Rate
        "frequency_code": "3",     # Monthly (data from 2025 onwards)
        "state_code": "99",        # All India
        "gender_code": "3",        # Person (all genders combined)
        "age_code": "4",           # All ages
        # FIXED IN 7.6.5: was "3" (Rural+Urban). PLFS's monthly Current
        # Weekly Status bulletin is explicitly urban-only by design (per
        # MoSPI's own data catalog: "estimate...in the short time interval
        # of three months for the urban areas only in the CWS") -- the
        # combined-sector code isn't valid for the monthly frequency, so
        # the API returned 14 real rows with every "value" field empty
        # rather than an error. Confirmed via a real run's log output.
        "sector_code": "2",        # Urban only
        "limit": "200",
        "Format": "JSON",
    }
    session = _mospi_session()
    r = session.get(MOSPI_DATA_URL, params=params, timeout=60,
                     headers={"User-Agent": "economic-atlas/0.1",
                              "authorization": token},
                     verify=False)
    print(f"  [mospi] getData status={r.status_code}")
    r.raise_for_status()
    payload = r.json()

    # DIAGNOSTIC (7.6.4): the login response shape ("response" as a raw string,
    # not the nested {"response":{"token":...}} the official example script
    # assumes) turned out to differ from documentation once, so don't assume
    # the data response's shape either -- print enough of it that a failure
    # here is diagnosable from the Actions log alone, not another guess.
    records = payload.get("data")
    if records is None:
        records = payload.get("records")
    if records is None and isinstance(payload, list):
        records = payload
    if not isinstance(records, list):
        print(f"  [mospi] unexpected getData shape, top-level keys: "
              f"{list(payload.keys()) if isinstance(payload, dict) else type(payload)}")
        print(f"  [mospi] raw response (first 500 chars): {str(payload)[:500]}")
        return None
    if records:
        print(f"  [mospi] {len(records)} raw records; first row: "
              f"{records[0] if isinstance(records[0], dict) else type(records[0])}")

    def _get_ci(row, *names):
        """Case-insensitive, multi-alias dict lookup."""
        lower = {k.lower(): v for k, v in row.items()}
        for name in names:
            if name.lower() in lower and lower[name.lower()] not in (None, ""):
                return lower[name.lower()]
        return None

    # CONFIRMED via a real run's log (7.6.6): the "month" field comes back as
    # a full month name ("December"), not a numeric code as the request
    # parameter of the same name suggested -- int("December") raised
    # ValueError, silently caught below, which is why every row was skipped.
    MONTH_NAMES = {"january": 1, "february": 2, "march": 3, "april": 4, "may": 5,
                   "june": 6, "july": 7, "august": 8, "september": 9,
                   "october": 10, "november": 11, "december": 12}

    def _month_num(raw):
        if raw is None:
            return None
        s = str(raw).strip()
        if s.isdigit():
            return int(s)
        return MONTH_NAMES.get(s.lower())

    points = {}
    skipped = 0
    for row in records:
        if not isinstance(row, dict):
            skipped += 1
            continue
        try:
            year = _get_ci(row, "year")
            month = _month_num(_get_ci(row, "month_code", "month"))
            value = _get_ci(row, "value", "ur", "indicator_value", "data_value")
            if year is None or month is None or value is None:
                skipped += 1
                continue
            period = f"{int(year)}-{month:02d}"
            points[period] = float(value)
        except (TypeError, ValueError):
            skipped += 1
            continue
    if skipped:
        print(f"  [mospi] skipped {skipped} of {len(records)} rows (unparseable)")
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
        ("cpi", lambda: fetch_oecd_cpi(("IND",), "M"),
         "CPI, all items, YoY (OECD live prices system)", "%", "months"),
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

    try:
        if key:
            fx_pts = fetch_fred("DEXINUS", "d", key)
            if fx_pts:
                fx_period, fx_rate = fx_pts[-1]
                out["fx_to_usd"] = {"pair": "INR/USD", "rate": fx_rate,
                                     "as_of": fx_period, "direction": "divide"}
                print(f"  ok  fx_to_usd        1 observation ({fx_period}, {fx_rate})")

                to_local = lambda v: v * fx_rate
                for tk in ("trade_balance", "exports", "imports"):
                    if tk in out["series"]:
                        ser = out["series"][tk]
                        if ser["unit"].strip().startswith("$"):
                            ser["points"] = [[p, round(to_local(v), 1)] for p, v in ser["points"]]
                            ser["unit"] = ser["unit"].replace("$", "₹", 1)
                            ser["label"] = ser["label"].replace(", $ ", ", ₹ ") \
                                                        .replace(", $", ", ₹")
                            print(f"  ok  {tk:<16} converted {'$'}->{'₹'} using {fx_rate}")
            else:
                print("note  fx_to_usd: no observations returned")
        else:
            print("note  fx_to_usd not set (no FRED_API_KEY) — "
                  "Dollarise will be unavailable on this page until next run.")
    except Exception as exc:
        print(f"FAIL  fx_to_usd        {exc}")

    with open("data-in.json", "w") as f:
        json.dump(out, f)
    print(f"\nWrote data-in.json with {len(out['series'])} series.")
    if failures:
        print(f"Missing: {', '.join(failures)} — the page will still render.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
