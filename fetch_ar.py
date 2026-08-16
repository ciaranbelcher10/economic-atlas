"""Fetch Argentina economic series and write data-ar.json.

Run:  FRED_API_KEY=yourkey python3 fetch_ar.py
Sources: FRED (free key required: fred.stlouisfed.org), OECD, World Bank,
IMF World Economic Outlook (via FRED, for fiscal series).
In GitHub Actions the key comes from the FRED_API_KEY repository secret.

Argentina build note: derived from fetch_id.py (most recent non-OECD,
World-Bank-member, IMF-WEO-fiscal page at build time) per the v2
country-build framework. Argentina is neither an OECD, EU, nor EEA/EFTA
member. IMPORTANT DATA-QUALITY NOTE, separate from anything technical:
Argentina's official INDEC CPI figures from 2007-2015 are widely
regarded by independent economists and the IMF as having understated
true inflation during that period; data since a 2016 methodology
overhaul is generally considered credible again. This is disclosed on
the page itself (footer and CPI panel description) -- it is not
something this fetch script can detect or correct, since it comes from
the same INDEC series either way.

VERIFICATION NOTES (checked against each series' own FRED/OECD page via
web_search before wiring in -- sandbox network cannot reach
fred.stlouisfed.org/sdmx.oecd.org directly, so these are page-content
confirmations, not live API test calls; the first real Actions run is
still the genuine test):
- gdp_real (NGDPRNSAXDCARQ): CONFIRMED live (through Q1 2026), IMF
  International Financial Statistics, quarterly. IMPORTANT: this is
  NOT seasonally adjusted (NSA) -- no SA version was confirmed
  available for Argentina during this build, unlike most other pages
  here. Regular swings between quarters partly reflect seasonal
  patterns on top of the (already extreme) underlying trend.
- gdp_level (World Bank NY.GDP.MKTP.CD, country=ARG): standard
  fetch_worldbank() mechanism, same raw-USD-to-$m scale correction
  (1e-6) as every other country using this indicator family. Argentina
  IS a World Bank member (unlike Taiwan, which was skipped this batch
  specifically because it is not), so this mechanism applies normally.
- unemployment (World Bank SL.UEM.TOTL.ZS, modeled ILO estimate):
  same mechanism used for Indonesia. No OECD LRHUTTTT-family series
  applies since Argentina is not an OECD member; a real quarterly
  INDEC-sourced series exists (per published figures) but no verified
  live FRED mirror of it was found during this build, so the annual
  World Bank modeled estimate is used instead.
- debt_gdp (GGGDTAARA188N) / deficit (GGNLBAARA188N): CONFIRMED live
  (through 2024, updated Apr 2025), IMF World Economic Outlook, general
  government, % of GDP, ANNUAL. Same IMF-WEO FRED family used for
  Turkey/Indonesia/Poland -- individually confirmed for Argentina
  specifically, not assumed. Expect large swings around Argentina's
  repeated debt restructurings and defaults -- that's real, not a
  data error.
- participation_rate / policy_rate / bond_yield_10y / current_account:
  NOT included. No clean live source individually confirmed for any of
  these during this build -- genuine, disclosed gaps, not guesses.
- fx_to_usd (CCUSMA02ARM618N): seen referenced via ALFRED under the
  equivalent series ID pattern used successfully for Turkey/Indonesia/
  Poland's OECD monthly-average FX family, but not independently
  re-confirmed with a direct full-observations page view during this
  build the way the other series above were. Included on the strength
  of the consistent naming pattern across three prior countries, but
  worth a specific check on the first real Actions run given
  Argentina's unusually complex multiple-exchange-rate history
  (official vs parallel/"blue" market rates) -- if this comes back
  wrong or empty, that's the first thing to investigate.
- cpi: wired in via OECD's live SDMX prices system (same proven query
  structure used for every other country on this site), REF_AREA=ARG.
  Not individually executed end-to-end for Argentina before this build
  -- check the Actions log on first real run. See the build note above
  and the page's own footer for the separate INDEC data-quality caveat.
- business_confidence: OECD BCICP via SDMX, same multi-query fallback
  pattern used for every other country, REF_AREA=ARG. Best-effort, not
  individually confirmed.
- trade_balance: standard OECD merchandise trade, monthly -- not
  individually confirmed for Argentina's specific data availability;
  best-effort, check the first Actions log.
- fdi: World Bank, same indicator code used for every other country
  (BX.KLT.DINV.WD.GD.ZS), country=ARG. Not individually confirmed for
  Argentina's specific data availability -- standard World Bank annual
  lag applies.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

import requests

# key: (fred_id, freq 'm'|'q'|'a', label, unit, transform None|'yoy'|'mom'|'qoq', scale)
FRED_SERIES = {
    "gdp_real": ("NGDPRNSAXDCARQ", "q", "Real GDP, current national prices, NSA (IMF IFS)", "ARSm", None, 1.0),
    "gdp_level": ("NGDPSAXDCARQ", "q", "Nominal GDP, current prices, SA (IMF IFS) -- note: SA, "
                  "while gdp_real above is NSA, since no matching-adjustment nominal series was "
                  "confirmed live; both are genuinely ARS-denominated so this doesn't reintroduce "
                  "the currency-mismatch issue this was added to fix", "ARSm", None, 1.0),
    "debt_gdp": ("GGGDTAARA188N", "a", "General government gross debt, % of GDP (IMF WEO)", "%", None, 1.0),
    "deficit": ("GGNLBAARA188N", "a", "General government net lending/borrowing, % of GDP (IMF WEO)", "%", None, 1.0),
    "fx_raw": ("ARGCCUSMA02STM", "m", "ARS per USD, average of daily rates (OECD)", "ARS", None, 1.0),
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
    return f"{y}-{m:02d}"


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
    for p, v in points:
        dedup[p] = v
    return sorted([[p, v] for p, v in dedup.items()], key=lambda x: x[0])


def yoy_from_level(points: list, lag: int) -> list:
    return [[points[i][0], round((points[i][1] / points[i - lag][1] - 1) * 100, 2)]
            for i in range(lag, len(points)) if points[i - lag][1]]


# ---- OECD business confidence (Argentina) — free SDMX API, no key ----
OECD_BASE = "https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_CLI"
OECD_QUERIES = [
    f"{OECD_BASE}/ARG.M.BCICP...AA...H?format=csvfile&startPeriod=1990",
    f"{OECD_BASE}/ARG.M.BCICP......?format=csvfile&startPeriod=1990",
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
                if low.get("REF_AREA", "ARG") != "ARG":
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
            print(f"  [oecd-bci] {len(rows)} matching rows after filtering -- no usable data")
        except Exception as exc:
            print(f"  [oecd-bci] parsing failed: {exc}")
            continue
    return None

# ---- OECD live CPI -- same proven query structure used across the site,
# pointed at Argentina. See the build note above for the separate,
# well-documented 2007-2015 INDEC data-quality caveat.
OECD_PRICES_BASE = "https://sdmx.oecd.org/public/rest/data/OECD.SDD.TPS,DSD_PRICES@DF_PRICES_ALL,1.0"


def fetch_oecd_cpi(areas: tuple, freq: str) -> list | None:
    import csv
    import io

    lag = 4 if freq == "Q" else 12
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
            return 0.0

    def to_yoy(pts):
        return [[pts[i][0], round((pts[i][1] / pts[i - lag][1] - 1) * 100, 2)]
                for i in range(lag, len(pts)) if pts[i - lag][1]] or None

    def parse_groups(text: str, area: str, tag: str) -> dict:
        reader = list(csv.DictReader(io.StringIO(text)))
        if not reader:
            print(f"  [oecd-cpi] {tag} 0 CSV rows; raw response (first 300 chars): {text[:300]!r}")
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
                    continue
                candidates = []
                for gkey, rows in groups.items():
                    pts = sorted([[p, v] for p, v in rows.items()], key=lambda x: x[0])
                    candidates.append((pts[-1][0], len(pts), gkey, pts))
                candidates.sort(key=lambda t: (t[0], t[1]), reverse=True)
                for last_period, n, gkey, pts in candidates:
                    age = period_age_days(last_period)
                    if age > max_age_days:
                        print(f"  [oecd-cpi] {tag} {gkey} REJECTED stale: {n} points ending {last_period}")
                        continue
                    out = pts if not needs_yoy else to_yoy(pts)
                    if not out:
                        continue
                    print(f"  [oecd-cpi] {tag} {gkey} SUCCESS: {len(out)} points, {out[0][0]} to {out[-1][0]}")
                    return out
                continue
            except Exception as exc:
                print(f"  [oecd-cpi] {tag} parsing failed: {exc}")
                continue
    return None

# ---- World Bank (Argentina) — free API, no key ----
WB_URL = ("https://api.worldbank.org/v2/country/ARG/indicator/"
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


INDEC_IPC_URL = "https://www.indec.gob.ar/ftp/cuadros/economia/serie_ipc_divisiones.csv"


def fetch_indec_cpi_yoy() -> list | None:
    """Argentina's own national statistics office (INDEC) publishes this CSV
    directly and keeps it current with each monthly IPC release (confirmed
    via INDEC's own press releases through Apr 2026 as of this build) --
    genuinely live, unlike every FRED/OECD mirror and the datos.gob.ar open
    data API we checked (that catalog is frozen since mid-2025, orphaned by
    a 2023-24 ministry restructuring).

    IMPORTANT: the exact column layout of this CSV was NOT verified before
    this build -- the sandbox used to build this site can't reach
    indec.gob.ar (network egress is allowlisted to a small set of
    dev-tooling domains only) and web-based inspection tools couldn't read
    the raw bytes either. So instead of guessing a column position, this
    parses defensively: it decodes with a couple of likely encodings, tries
    comma then semicolon as the delimiter (INDEC has used both across
    different files), and finds the "Nivel general" column by matching its
    header text rather than assuming a fixed index. If any of that doesn't
    hold on the real file, this returns None and cpi simply stays a
    disclosed gap rather than silently feeding wrong numbers -- check the
    Actions log on the first real run to see exactly what it found.
    """
    r = requests.get(INDEC_IPC_URL, timeout=60,
                     headers={"User-Agent": "economic-atlas/0.1"})
    r.raise_for_status()
    import csv
    import io
    import re

    raw = r.content
    text = None
    for enc in ("utf-8-sig", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        print("  [indec-ipc] could not decode response as text")
        return None

    for delim in (";", ","):
        try:
            rows = list(csv.reader(io.StringIO(text), delimiter=delim))
        except Exception:
            continue
        if not rows or len(rows[0]) < 2:
            continue
        header = [h.strip().lower() for h in rows[0]]
        date_col = 0
        general_col = None
        for i, h in enumerate(header):
            norm = re.sub(r"[^a-z0-9]", "", h)
            if "nivelgeneral" in norm or norm == "general":
                general_col = i
                break
        if general_col is None:
            continue
        points = []
        for row in rows[1:]:
            if len(row) <= max(date_col, general_col):
                continue
            date_raw = row[date_col].strip()
            val_raw = row[general_col].strip().replace(",", ".")
            m = re.match(r"(\d{4})-(\d{1,2})", date_raw)
            if not m:
                continue
            period = f"{m.group(1)}-{int(m.group(2)):02d}"
            try:
                points.append([period, float(val_raw)])
            except ValueError:
                continue
        if len(points) >= 24:
            points.sort(key=lambda p: p[0])
            yoy = [[points[i][0], round((points[i][1] / points[i - 12][1] - 1) * 100, 2)]
                   for i in range(12, len(points)) if points[i - 12][1]]
            if yoy:
                print(f"  [indec-ipc] delimiter={delim!r} SUCCESS: {len(yoy)} points, "
                      f"{yoy[0][0]} to {yoy[-1][0]}")
                return yoy
        print(f"  [indec-ipc] delimiter={delim!r} found header but only "
              f"{len(points)} usable rows -- rejecting")
    print("  [indec-ipc] could not locate a 'Nivel general' column with "
          "either delimiter; raw header row: " + repr(text.splitlines()[0][:200]
          if text.splitlines() else "(empty)"))
    return None


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
            if name == "fx_raw":
                continue
            try:
                raw = fetch_fred(sid, freq, key)
                if scale != 1.0:
                    raw = [[p, v * scale] for p, v in raw]
                points = raw
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

        # gdp_growth: derived as QoQ from the real-GDP level series above.
        # NOTE: lag=1 is genuine quarter-on-quarter for quarterly data --
        # lag=4 (the old value) is YoY, which duplicated the separately-
        # computed gdpYoY frontend variable under a card titled "QoQ".
        # See the Switzerland Bug 6 writeup for the full diagnosis.
        if "gdp_real" in out["series"]:
            level_pts = out["series"]["gdp_real"]["points"]
            growth_pts = yoy_from_level(level_pts, 1)
            if growth_pts:
                out["series"]["gdp_growth"] = {
                    "label": "Real GDP growth, QoQ (derived from NGDPRNSAXDCARQ)",
                    "unit": "%", "freq": "quarters", "points": growth_pts,
                }
                print(f"  ok  gdp_growth      {len(growth_pts):>5} observations (derived QoQ)")

        try:
            sid, freq, _, _, _, _ = FRED_SERIES["fx_raw"]
            fx_pts = fetch_fred(sid, freq, key)
            if fx_pts:
                fx_period, fx_rate = fx_pts[-1]
                out["fx_to_usd"] = {"pair": "ARS/USD", "rate": fx_rate,
                                     "as_of": fx_period, "direction": "divide"}
                print(f"  ok  fx_to_usd        1 observation ({fx_period}, {fx_rate})")
            else:
                print("note  fx_to_usd: no observations returned")
        except Exception as exc:
            print(f"FAIL  fx_to_usd        {exc}")

    extras = [
        ("business_confidence", lambda: fetch_oecd_bci(),
         "Business confidence indicator, LT avg = 100 (OECD BCICP)", "index", "months"),
        ("cpi", lambda: fetch_indec_cpi_yoy(),
         "CPI, all items, YoY (INDEC, national statistics office)", "%", "months"),
        ("unemployment", lambda: fetch_worldbank("SL.UEM.TOTL.ZS"),
         "Unemployment, total (modeled ILO estimate, World Bank)", "%", "years"),
        ("fdi", lambda: fetch_worldbank("BX.KLT.DINV.WD.GD.ZS"),
         "FDI net inflows, % of GDP (World Bank)", "%", "years"),
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

    if "cpi" not in out["series"]:
        # INDEC's CSV parse didn't produce anything usable (see the
        # [indec-ipc] log lines above for why). Fall back to OECD's live
        # prices system as a second attempt before giving up and leaving
        # cpi as a disclosed gap.
        try:
            oecd_pts = fetch_oecd_cpi(("ARG",), "M")
            if oecd_pts:
                out["series"]["cpi"] = {
                    "label": "CPI, all items, YoY (OECD live prices system)",
                    "unit": "%", "freq": "months", "points": oecd_pts,
                }
                print(f"  ok  cpi (OECD fallback) {len(oecd_pts):>5} observations "
                      f"({oecd_pts[0][0]} to {oecd_pts[-1][0]}, months)")
                if "cpi" in failures:
                    failures.remove("cpi")
        except Exception as exc:
            print(f"FAIL  cpi (OECD fallback) {exc}")

    if "gdp_level" not in out["series"]:
        # NGDPSAXDCARQ above (via FRED_SERIES) is now the primary source,
        # genuinely denominated in ARS -- matching gdp_real and the site's
        # local-currency-by-default convention. This World Bank USD series
        # is now only a fallback, clearly labeled as USD so the frontend's
        # isAlreadyUSD() guard (added this session) correctly skips
        # re-converting it if this fallback ever gets used.
        try:
            raw_gdp = fetch_worldbank("NY.GDP.MKTP.CD")
            if not raw_gdp:
                raise ValueError("no usable response")
            scaled_gdp = [[p, round(v / 1e6, 1)] for p, v in raw_gdp]
            out["series"]["gdp_level"] = {
                "label": "GDP, current prices (World Bank, NY.GDP.MKTP.CD -- USD, "
                         "fallback: NGDPSAXDCARQ unavailable this run)",
                "unit": "$m", "freq": "years", "points": scaled_gdp,
            }
            print(f"  ok  gdp_level (WB USD fallback) {len(scaled_gdp):>5} observations "
                  f"({scaled_gdp[0][0]} to {scaled_gdp[-1][0]}, years)")
            if "gdp_level" in failures:
                failures.remove("gdp_level")
        except Exception as exc:
            failures.append("gdp_level")
            print(f"FAIL  gdp_level (WB USD fallback) {exc}")

    # Carry forward any series that failed THIS run but succeeded on a
    # previous run, so a transient failure doesn't permanently wipe good
    # data from the live page. See the Switzerland/Chile/Colombia Bug 7
    # writeup -- applied here to close the same gap for Argentina.
    try:
        with open("data-ar.json") as f:
            _prev_for_merge = json.load(f)
    except Exception:
        _prev_for_merge = {}
    _prev_series = _prev_for_merge.get("series", {})
    carried_over = []
    for k, v in _prev_series.items():
        if k not in out["series"]:
            out["series"][k] = v
            carried_over.append(k)
    if carried_over:
        print(f"CARRIED OVER from previous run (failed this run, kept prior data rather than deleting it): {', '.join(carried_over)}")
    if not out.get("fx_to_usd") and _prev_for_merge.get("fx_to_usd"):
        out["fx_to_usd"] = _prev_for_merge["fx_to_usd"]
        print("CARRIED OVER fx_to_usd from previous run")

    if not out["series"]:
        print("\nNothing fetched.")
        return 1

    try:
        with open("data-ar.json") as f:
            prev_full = json.load(f)
    except Exception:
        prev_full = {}
    prev_meta = prev_full.get("new_points_meta")
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

    with open("data-ar.json", "w") as f:
        json.dump(out, f)
    print(f"\nWrote data-ar.json with {len(out['series'])} series.")
    if failures:
        print(f"Missing: {', '.join(failures)} — the page will still render.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
