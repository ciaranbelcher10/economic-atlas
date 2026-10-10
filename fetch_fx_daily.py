"""
Daily exchange rates for every country page's Markets tab, ChartMaker and
My Dashboard: writes one data-fx-<suffix>.json per country.

Every rate is dollars, euros or pounds per unit of the home currency (see
fx_config.py), so a rise always means a stronger home currency.

Sources
-------
* Federal Reserve H.10 daily noon buying rates, via FRED (FRED_API_KEY),
  for the 17 currencies it covers. The Fed publishes H.10 weekly, so the
  newest daily observation can be up to a week old; the tile says which day.
* World Bank PA.NUS.FCRF (official rate, annual average) for the 8
  currencies with no free official daily or monthly series. Read from the
  country's own data file, which its fetch script already refreshes, so this
  script must run AFTER the country fetch scripts.

Arithmetic is exact and stated in each pair's citation: an inverted rate is
1 / the published rate, a cross rate is the ratio of two published rates on
the same day (daily) or of their annual averages (annual).

Each pair stores:
  daily    the last three years of trading days (tiles use the newest)
  points   full history for charts: month-end for daily sources (the
           current month shows its latest day), annual for World Bank
  confirmed_at  when this run fetched it; a pair this run could not build
           is carried over from the previous file with its old stamp, so its
           freshness light turns amber rather than lying.
"""
import redact_stream  # noqa: F401  (v1.7.42: masks api_key= in all output)
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone

import requests

import fx_config as C

FRED_URL = ("https://api.stlouisfed.org/fred/series/observations"
            "?series_id={sid}&api_key={key}&file_type=json&observation_start=1971-01-01")
DAILY_YEARS = 3


def fetch_fred_daily(sid, key):
    r = requests.get(FRED_URL.format(sid=sid, key=key), timeout=60,
                     headers={"User-Agent": "economic-atlas/0.1"})
    r.raise_for_status()
    out = {}
    for o in r.json().get("observations", []):
        v = o.get("value")
        if v in (None, "", "."):
            continue
        try:
            f = float(v)
        except ValueError:
            continue
        if f > 0:
            out[o["date"]] = f
    if not out:
        raise ValueError("no observations")
    return out


def usd_per_unit_daily(raw):
    """{code: {date: US$ per 1 unit}} from the raw H.10 series."""
    u = {}
    for code, (sid, usd_per) in C.H10.items():
        if sid in raw:
            u[code] = {d: (v if usd_per else 1.0 / v) for d, v in raw[sid].items()}
    return u


def annual_mean(daily, year):
    vals = [v for d, v in daily.items() if d.startswith(str(year))]
    return sum(vals) / len(vals) if len(vals) >= 200 else None


def month_end(daily_pts):
    by = {}
    for d, v in daily_pts:
        by[d[:7]] = v          # sorted input: last day of each month wins
    return sorted(by.items())


def sig(v):
    return float(f"{v:.6g}")


def describe(home, quote):
    hn, qn = C.NAME[home], C.QUOTE_NAME[quote]
    title = f"{hn[0].upper() + hn[1:]} in {qn}"
    unit = C.home_unit(home)
    desc = (f"How many {qn} {unit} buys. A rising number means a stronger {hn}."
            if home != "USD" else f"How many {qn} one US dollar buys. A rising number means a stronger dollar.")
    return title, desc


def build_pair(country, home, quote, u_daily, prev_data):
    n = C.SCALE.get(home, 1)
    key = C.pair_key(home, quote)
    title, desc = describe(home, quote)
    base = dict(key=key, home=home, quote=quote, title=title, description=desc,
                quote_symbol=C.quote_symbol(quote, home), base_unit=C.home_unit(home), scale=n)

    def u_of(code):
        return None if code == "USD" else u_daily.get(code)

    if home in C.ANNUAL:
        fx = (prev_data or {}).get("fx_to_usd") or {}
        hist = [(p, v) for p, v in (fx.get("history") or []) if v]
        if not hist or fx.get("direction") != "divide" or not str(hist[-1][0]).isdigit():
            return None
        pts = []
        for y, per_usd in hist:
            usd = 1.0 / per_usd
            if quote == "USD":
                val = usd
            else:
                q = u_of(quote)
                qa = annual_mean(q, y) if q else None
                if qa is None:
                    continue
                val = usd / qa
            pts.append([str(y), sig(val * n)])
        start = C.SERIES_START.get(home)
        if start:
            pts = [p for p in pts if p[0] >= start[0]]
            base["description"] += f" Starts in {start[0]}, with {start[1]}; earlier years are in older currency units."
        if len(pts) < 2:
            return None
        if quote == "USD":
            src = (f"World Bank series PA.NUS.FCRF \u00b7 official exchange rate, annual average, "
                   f"shown as {n:,} \u00f7 the published {home} per US$.")
            short = "World Bank \u00b7 PA.NUS.FCRF"
        else:
            src = (f"Derived: World Bank PA.NUS.FCRF annual average ({home} per US$) and the annual average of "
                   f"Federal Reserve H.10 {C.H10[quote][0]}, "
                   f"{C.SYMBOL[quote]} per {C.home_unit(home)} = (US$ per {C.home_unit(home)}) \u00f7 (US$ per {C.SYMBOL[quote]}1).")
            short = f"Derived \u00b7 PA.NUS.FCRF, {C.H10[quote][0]}"
        return dict(base, freq="years", points=pts, source=src, source_short=short)

    # Daily sources
    uh, uq = u_of(home), u_of(quote)
    if (home != "USD" and uh is None) or (quote != "USD" and uq is None):
        return None
    dates = sorted(set(uh or {}) & set(uq or {})) if home != "USD" and quote != "USD" \
        else sorted((uh or uq).keys())
    daily = []
    for d in dates:
        h = 1.0 if home == "USD" else uh[d]
        q = 1.0 if quote == "USD" else uq[d]
        daily.append([d, sig(h / q * n)])
    if len(daily) < 2:
        return None
    ids = [C.H10[c][0] for c in (home, quote) if c != "USD"]
    if len(ids) == 1:
        sid = ids[0]
        published_direct = (home != "USD" and C.H10[home][1] and quote == "USD")
        if published_direct:
            how = "as published"
        elif home == "USD":
            how = f"1 \u00f7 the published US$ per {C.SYMBOL[quote]}1"
        else:
            how = f"{n:,} \u00f7 the published {home} per US$"
        src = f"Federal Reserve H.10 (FRED series {sid}) \u00b7 noon buying rate, New York; {how}."
        short = f"Fed H.10 \u00b7 {sid} \u00b7 published weekly"
    else:
        src = (f"Derived from Federal Reserve H.10 series {ids[0]} and {ids[1]} (FRED) on each trading day: "
               f"{C.SYMBOL[quote]} per {C.home_unit(home)} = (US$ per {C.home_unit(home)}) \u00f7 (US$ per {C.SYMBOL[quote]}1).")
        short = f"Derived \u00b7 {ids[0]}, {ids[1]} \u00b7 published weekly"
    cutoff = (date.today() - timedelta(days=365 * DAILY_YEARS)).isoformat()
    return dict(base, freq="months", points=[[p, v] for p, v in month_end(daily)],
                daily=[p for p in daily if p[0] >= cutoff], source=src, source_short=short)


def main(base_dir="."):
    key = os.environ.get("FRED_API_KEY", "")
    raw, failed = {}, []
    for code, (sid, _) in C.H10.items():
        try:
            if not key:
                raise RuntimeError("FRED_API_KEY not set")
            raw[sid] = fetch_fred_daily(sid, key)
            print(f"  ok  {sid:<8} {len(raw[sid]):>6} daily observations (to {max(raw[sid])})")
        except Exception as exc:
            failed.append(sid)
            print(f"FAIL  {sid:<8} {exc}")
    u = usd_per_unit_daily(raw)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    for country, (home, suffix, quotes) in C.COUNTRY_FX.items():
        path = os.path.join(base_dir, C.fx_file(suffix))
        try:
            with open(path) as f:
                prev_pairs = {p["key"]: p for p in json.load(f).get("pairs", [])}
        except Exception:
            prev_pairs = {}
        try:
            with open(os.path.join(base_dir, C.data_file(suffix))) as f:
                country_data = json.load(f)
        except Exception:
            country_data = {}
        pairs = []
        for q in quotes:
            k = C.pair_key(home, q)
            try:
                p = build_pair(country, home, q, u, country_data)
            except Exception as exc:
                print(f"FAIL  {country} {k}: {exc}")
                p = None
            if p:
                # A pair only confirms if it reaches at least as far as before.
                old = prev_pairs.get(k)
                if old and old.get("points") and p["points"][-1][0] < old["points"][-1][0]:
                    print(f"KEPT  {country} {k}: new data ends {p['points'][-1][0]}, previous {old['points'][-1][0]}")
                    p = old
                else:
                    p["confirmed_at"] = now
            elif k in prev_pairs:
                p = prev_pairs[k]
                print(f"CARRIED OVER {country} {k}")
            if p:
                pairs.append(p)
        if not pairs:
            continue
        with open(path, "w") as f:
            json.dump({"country": country, "home": home, "updated": now, "pairs": pairs}, f,
                      separators=(",", ":"))
        latest = ", ".join(f"{p['quote_symbol']}{p['points'][-1][1]} per {p['base_unit']}" for p in pairs)
        print(f"  ok  {country:<13} {latest}")
    return 1 if len(failed) == len(C.H10) else 0


if __name__ == "__main__":
    sys.exit(main())
