#!/usr/bin/env python3
"""Probe sources for the euro-area current account (% of GDP).

Why: fetch_ez.py asks the World Bank for BN.CAB.XOKA.GD.ZS on country EMU,
and the series has never appeared in data-ez.json (absent in every commit
checked back to 4 Oct). This probe confirms why, and tests replacements:

  WB    World Bank EMU aggregate (current source)          - root-cause check
  ES-Q  Eurostat bop_gdp6_q, CA balance, % of GDP, quarterly
  ES-A  same table, annual (sum of quarters not needed: table has A freq?)
  ECB   ECB BPS current account, EUR mn, quarterly -> annual sum,
        divided by Eurostat nominal GDP (namq_10_gdp B1GQ CP_MEUR) -> % GDP

Read-only. Prints each candidate's span and last 6 annual values so they
can be compared side by side (EA CA has run roughly +2% to +3% of GDP
in recent years).

    python3 tools/probe_ez_ca.py
"""
import json
import requests

UA = {"User-Agent": "economic-atlas/0.1 probe"}
ES = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"


def get(url, **kw):
    try:
        r = requests.get(url, timeout=60, headers=UA, **kw)
        print(f"    status={r.status_code} {url[:150]}")
        return r if r.ok else None
    except Exception as exc:
        print(f"    FAILED {exc}")
        return None


def jsonstat_series(text):
    j = json.loads(text)
    idx = j["dimension"]["time"]["category"]["index"]
    inv = {v: k for k, v in idx.items()}
    vals = j.get("value", {})
    items = vals.items() if isinstance(vals, dict) else enumerate(vals)
    out = {}
    # only valid when every non-time dimension has size 1
    sizes = j["size"]
    if any(s != 1 for d, s in zip(j["id"], sizes) if d != "time"):
        dims = {d: s for d, s in zip(j["id"], sizes) if s != 1}
        print(f"    NOTE: non-singleton dimensions {dims}; result ambiguous")
        return {}
    for k, v in items:
        if v is not None:
            out[inv[int(k)]] = float(v)
    return dict(sorted(out.items()))


def show(name, d):
    if not d:
        print(f"  {name}: no data\n")
        return
    ks = list(d)
    print(f"  {name}: {len(d)} pts, {ks[0]} to {ks[-1]}")
    for k in ks[-6:]:
        print(f"      {k}: {d[k]:.2f}")
    print()


def annualise_q(d):
    yrs = {}
    for k, v in d.items():
        y = k[:4]
        yrs.setdefault(y, []).append(v)
    return {y: sum(v) for y, v in yrs.items() if len(v) == 4}


print("== WB: World Bank BN.CAB.XOKA.GD.ZS, EMU (current source)")
r = get("https://api.worldbank.org/v2/country/EMU/indicator/BN.CAB.XOKA.GD.ZS"
        "?format=json&per_page=200")
if r is not None:
    p = r.json()
    rows = p[1] if isinstance(p, list) and len(p) > 1 and p[1] else []
    nonnull = {x["date"]: x["value"] for x in rows if x.get("value") is not None}
    print(f"    rows={len(rows)} non-null={len(nonnull)}  head={str(p)[:200]}")
    show("WB EMU", dict(sorted(nonnull.items())))

for freq, label in (("Q", "ES-Q"), ("A", "ES-A")):
    print(f"== {label}: Eurostat bop_gdp6_q, freq={freq}")
    for geo, partner in (("EA20", "EXT_EA20"), ("EA21", "EXT_EA21"),
                         ("EA20", "WRL_REST"), ("EA21", "WRL_REST")):
        url = (f"{ES}/bop_gdp6_q?format=JSON&lang=EN&freq={freq}&geo={geo}"
               f"&partner={partner}&bop_item=CA&stk_flow=BAL&unit=PC_GDP"
               f"&s_adj=NSA&sinceTimePeriod=1999")
        r = get(url)
        if r is not None:
            try:
                d = jsonstat_series(r.text)
                show(f"{label} {geo}/{partner}", d)
                if d:
                    break
            except Exception as exc:
                print(f"    parse failed: {exc}; {r.text[:200]!r}")

print("== ECB: BPS current account EUR mn (quarterly), / Eurostat GDP")
ecb = None
for key in ("Q.N.I9.W1.S1.S1.T.B.CA._Z._Z._Z.EUR._T._X.N",
            "Q.N.I8.W1.S1.S1.T.B.CA._Z._Z._Z.EUR._T._X.N"):
    r = get(f"https://data-api.ecb.europa.eu/service/data/BPS/{key}"
            "?format=csvdata&startPeriod=1999")
    if r is not None:
        import csv, io
        rows = list(csv.DictReader(io.StringIO(r.text)))
        d = {}
        for row in rows:
            try:
                d[row["TIME_PERIOD"]] = float(row["OBS_VALUE"])
            except (KeyError, ValueError):
                pass
        if d:
            ecb = dict(sorted(d.items()))
            print(f"    key {key}: {len(ecb)} quarters, "
                  f"{list(ecb)[0]} to {list(ecb)[-1]}")
            break
gdp = None
for geo in ("EA21", "EA20"):
    r = get(f"{ES}/namq_10_gdp?format=JSON&lang=EN&geo={geo}&unit=CP_MEUR"
            f"&na_item=B1GQ&s_adj=NSA&sinceTimePeriod=1999")
    if r is not None:
        try:
            gdp = jsonstat_series(r.text)
            if gdp:
                print(f"    GDP {geo}: {len(gdp)} quarters")
                break
        except Exception as exc:
            print(f"    GDP parse failed: {exc}")
if ecb and gdp:
    def qkey(k):  # ECB '2024-Q1' vs Eurostat '2024-Q1'
        return k.replace("Q", "Q")
    ca_a = annualise_q(ecb)
    gdp_a = annualise_q({qkey(k): v for k, v in gdp.items()})
    pct = {y: 100 * ca_a[y] / gdp_a[y] for y in ca_a if y in gdp_a}
    show("ECB/Eurostat annual % GDP", pct)
    qpct = {k: 100 * ecb[k] / gdp[k] for k in ecb if k in gdp}
    show("ECB/Eurostat quarterly % GDP (NSA)", qpct)

print("Done. Pick the candidate whose recent annual values agree and that"
      " reaches furthest forward.")
