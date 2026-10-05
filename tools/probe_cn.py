#!/usr/bin/env python3
"""Scope China before building it: which official sources answer, how deep
and how current each series is.

Read-only: writes nothing, imported by nothing, never scheduled.
    FRED_API_KEY=... python3 tools/probe_cn.py > probe_cn.txt
Needs outbound access to FRED, OECD, IMF, BIS, World Bank and NBS (not the
sandbox). Each check prints one summary line; a SUMMARY table closes the run.
A failure is a result, not an error: the point is to see what exists.
"""
from __future__ import annotations

import csv, io, json, os, re, sys, time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
UA = {"User-Agent": "economic-atlas/0.1 (+https://theeconomicatlas.com)"}
KEY = os.environ.get("FRED_API_KEY", "").strip()
RESULTS = []


def summarise(name, pts, note=""):
    pts = [p for p in (pts or []) if p and p[1] is not None]
    if not pts:
        RESULTS.append((name, "EMPTY", 0, "", "", note))
        print(f"EMPTY  {name}  {note}")
        return
    pts.sort(key=lambda p: str(p[0]))
    tail = ", ".join(f"{p[0]}={p[1]}" for p in pts[-3:])
    RESULTS.append((name, "ok", len(pts), str(pts[0][0]), str(pts[-1][0]), note))
    print(f"ok     {name}  {len(pts)} pts {pts[0][0]}..{pts[-1][0]}  last: {tail}  {note}")


def fail(name, exc):
    RESULTS.append((name, "FAIL", 0, "", "", str(exc)[:120]))
    print(f"FAIL   {name}  {str(exc)[:200]}")


def get(url, accept=None, timeout=60):
    h = dict(UA)
    if accept:
        h["Accept"] = accept
    r = requests.get(url, timeout=timeout, headers=h)
    r.raise_for_status()
    return r


def run(name, fn, note=""):
    try:
        summarise(name, fn(), note)
    except Exception as exc:
        fail(name, exc)
    time.sleep(1)


# ---------- FRED ----------
def fred(sid):
    if not KEY:
        raise RuntimeError("FRED_API_KEY not set")
    r = get(f"https://api.stlouisfed.org/fred/series/observations?series_id={sid}"
            f"&api_key={KEY}&file_type=json&observation_start=1990-01-01")
    return [[o["date"][:7], float(o["value"])] for o in r.json()["observations"] if o["value"] not in (".", "")]


def fred_search(text):
    if not KEY:
        print("skip FRED search (no key)")
        return
    r = get("https://api.stlouisfed.org/fred/series/search?search_text=" + requests.utils.quote(text)
            + f"&api_key={KEY}&file_type=json&limit=15&order_by=popularity")
    print(f"\n-- FRED search: {text}")
    for s in r.json().get("seriess", []):
        print(f"   {s['id']:<24} {s['frequency_short']:>2} {s['observation_start']}..{s['observation_end']}  {s['title'][:80]}")
    time.sleep(1)


# ---------- OECD ----------
def oecd_csv(url):
    r = get(url, accept="text/csv", timeout=90)
    return list(csv.DictReader(io.StringIO(r.text)))


def oecd_series(url, filt=None):
    rows = oecd_csv(url)
    groups = {}
    for row in rows:
        if filt and not filt(row):
            continue
        k = tuple((c, row.get(c, "")) for c in ("FREQ", "MEASURE", "UNIT_MEASURE", "TRANSFORMATION", "ADJUSTMENT", "METHODOLOGY") if c in row)
        try:
            groups.setdefault(k, []).append([row["TIME_PERIOD"], float(row["OBS_VALUE"])])
        except (KeyError, ValueError):
            pass
    if not groups:
        return []
    for k, v in groups.items():
        v.sort()
        print(f"   variant {dict(k)}: {len(v)} pts {v[0][0]}..{v[-1][0]}")
    return max(groups.values(), key=lambda v: (v[-1][0], len(v)))


O = "https://sdmx.oecd.org/public/rest/data/"


# ---------- IMF ----------
def imf_csv(url):
    r = get(url, accept="text/csv", timeout=90)
    pts = []
    for row in csv.DictReader(io.StringIO(r.text)):
        per = (row.get("TIME_PERIOD") or "").replace("-M", "-")
        v = row.get("OBS_VALUE") or ""
        if per and v:
            try:
                pts.append([per, float(v)])
            except ValueError:
                pass
    return pts


# ---------- World Bank ----------
def wb(ind):
    r = get(f"https://api.worldbank.org/v2/country/CHN/indicator/{ind}?format=json&per_page=200")
    j = r.json()
    if len(j) < 2 or not j[1]:
        return []
    return [[d["date"], d["value"]] for d in j[1] if d["value"] is not None]


# ---------- BIS ----------
def bis(key):
    r = get(f"https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CBPOL/1.0/{key}?format=csv", accept="text/csv")
    return [[row["TIME_PERIOD"], float(row["OBS_VALUE"])] for row in csv.DictReader(io.StringIO(r.text))
            if row.get("OBS_VALUE") not in (None, "", "NaN")]


# ---------- NBS (National Bureau of Statistics) ----------
NBS = "https://data.stats.gov.cn/english/easyquery.htm"


def nbs_tree(db, node="zb"):
    r = requests.post(NBS, data={"id": node, "dbcode": db, "wdcode": "zb", "m": "getTree"},
                      headers=UA, timeout=60, verify=False)
    print(f"\n-- NBS tree {db}/{node}: status={r.status_code}")
    try:
        for n in r.json()[:40]:
            print(f"   {n.get('id'):<12} parent={n.get('isParent')}  {n.get('name')}")
    except Exception:
        print("   not JSON:", r.text[:200].replace("\n", " "))
    time.sleep(1)


def nbs_query(db, code, last="LAST36"):
    params = {"m": "QueryData", "dbcode": db, "rowcode": "zb", "colcode": "sj", "wds": "[]",
              "dfwds": json.dumps([{"wdcode": "zb", "valuecode": code}, {"wdcode": "sj", "valuecode": last}])}
    r = requests.get(NBS, params=params, headers=UA, timeout=60, verify=False)
    r.raise_for_status()
    j = r.json()
    names = {n["code"]: n["cname"] for w in j["returndata"]["wdnodes"] if w["wdcode"] == "zb" for n in w["nodes"]}
    by = {}
    for dn in j["returndata"]["datanodes"]:
        if not dn["data"]["hasdata"]:
            continue
        zb = next(w["valuecode"] for w in dn["wds"] if w["wdcode"] == "zb")
        sj = next(w["valuecode"] for w in dn["wds"] if w["wdcode"] == "sj")
        by.setdefault(zb, []).append([sj, dn["data"]["data"]])
    for zb, v in by.items():
        v.sort()
        print(f"   {zb:<14} {names.get(zb, '')[:60]:<60} {len(v)} pts {v[0][0]}..{v[-1][0]} last={v[-1][1]}")
    return max(by.values(), key=len) if by else []


def main():
    import urllib3
    urllib3.disable_warnings()
    print(f"China source probe, {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}\n")

    print("== FRED")
    for sid, what in [("DEXCHUS", "FX yuan per USD, daily"), ("CPALTT01CNM659N", "CPI YoY (OECD MEI)"),
                      ("CHNCPIALLMINMEI", "CPI index (OECD MEI)"), ("XTEXVA01CNM667S", "exports USD SA"),
                      ("XTIMVA01CNM667S", "imports USD SA"), ("CHNGDPNQDSMEI", "nominal GDP quarterly"),
                      ("INTDSRCNM193N", "discount rate"), ("IRLTLT01CNM156N", "10y yield (probably absent)"),
                      ("LRUN64TTCNQ156S", "unemployment (probably absent)")]:
        run(f"FRED {sid}", lambda s=sid: fred(s), what)
    for t in ("China gross domestic product", "China consumer price", "China interest rate",
              "China unemployment", "China exports", "China government bond"):
        try:
            fred_search(t)
        except Exception as exc:
            print("   search failed", exc)

    print("\n== OECD")
    run("OECD CPI C2018 CHN YoY", lambda: oecd_series(O + "OECD.SDD.TPS,DSD_PRICES_COICOP2018@DF_PRICES_C2018_ALL,1.0/CHN.M..CPI.PA._T..GY?format=csvfile&startPeriod=2015"))
    run("OECD CPI C1999 CHN YoY", lambda: oecd_series(O + "OECD.SDD.TPS,DSD_PRICES@DF_PRICES_ALL,1.0/CHN.M..CPI.PA._T..GY?format=csvfile&startPeriod=2015"))
    run("OECD CPI C2018 CHN index", lambda: oecd_series(O + "OECD.SDD.TPS,DSD_PRICES_COICOP2018@DF_PRICES_C2018_ALL,1.0/CHN.M..CPI.IX._T.._Z?format=csvfile&startPeriod=2000"))
    run("OECD BCI CHN", lambda: oecd_series(O + "OECD.SDD.STES,DSD_STES@DF_CLI/CHN.M.BCICP......?format=csvfile&startPeriod=1990"))
    run("OECD IRLT CHN", lambda: oecd_series(O + "OECD.SDD.STES,DSD_STES@DF_FINMARK/CHN..IRLT......?format=csvfile&startPeriod=1990"))
    run("OECD short rate CHN", lambda: oecd_series(O + "OECD.SDD.STES,DSD_STES@DF_FINMARK/CHN..IR3TIB......?format=csvfile&startPeriod=2000"))
    run("OECD unemployment CHN", lambda: oecd_series(O + "OECD.SDD.TPS,DSD_LFS@DF_IALFS_UNE_M,1.0/CHN..._Z.Y._T.Y_GE15..M?startPeriod=2015&format=csvfile"))
    run("OECD QNA CHN GDP", lambda: oecd_series(O + "OECD.SDD.NAD,DSD_NAMAIN1@DF_QNA,1.1/Q..CHN.S1..B1GQ......?startPeriod=2010&format=csvfile"))

    print("\n== IMF")
    import imf_weo
    for ind, what in [(imf_weo.DEBT, "gross debt % GDP"), (imf_weo.DEFICIT, "net lending % GDP")]:
        run(f"IMF WEO {ind}", lambda i=ind: imf_weo.fetch("CHN", i), what)
    run("IMF CPI index monthly", lambda: imf_csv("https://api.imf.org/external/sdmx/3.0/data/dataflow/IMF.STA/CPI/~/CHN.CPI._T.IX.M?c[TIME_PERIOD]=ge:2010-M01"))
    run("IMF MFS bond yield", lambda: imf_csv("https://api.imf.org/external/sdmx/3.0/data/dataflow/IMF.STA/MFS_IR/~/CHN.S13BOND_RT_PT_A_PT.M?c[TIME_PERIOD]=ge:1990-M01"))
    run("IMF MFS all CHN (rates list)", lambda: imf_csv("https://api.imf.org/external/sdmx/3.0/data/dataflow/IMF.STA/MFS_IR/~/CHN.*.M?c[TIME_PERIOD]=ge:2025-M01"),
        "wildcard; shows which rate series exist")

    print("\n== BIS policy rate")
    run("BIS WS_CBPOL M.CN", lambda: bis("M.CN"))

    print("\n== World Bank")
    for ind, what in [("NY.GDP.MKTP.CN", "GDP LCU"), ("NY.GDP.MKTP.KN", "real GDP LCU"),
                      ("NY.GDP.MKTP.KD.ZG", "real growth"), ("BX.KLT.DINV.WD.GD.ZS", "FDI % GDP"),
                      ("BN.CAB.XOKA.GD.ZS", "current account % GDP"), ("SL.UEM.TOTL.ZS", "unemployment ILO modelled"),
                      ("FP.CPI.TOTL.ZG", "CPI annual"), ("PA.NUS.FCRF", "FX annual avg")]:
        run(f"WB {ind}", lambda i=ind: wb(i), what)

    print("\n== NBS (National Bureau of Statistics of China)")
    for db in ("hgyd", "hgjd"):           # monthly, quarterly
        try:
            nbs_tree(db)
        except Exception as exc:
            print(f"   NBS tree {db} failed: {exc}")
    for db, code, what in [("hgyd", "A01", "monthly prices"), ("hgyd", "A0E", "monthly labour/unemployment"),
                           ("hgjd", "A01", "quarterly national accounts")]:
        run(f"NBS {db}/{code}", lambda d=db, c=code: nbs_query(d, c), what)

    print("\n== SUMMARY")
    for name, st, n, a, b, note in RESULTS:
        print(f"{st:<6} {name:<34} {n:>5}  {a:>9}..{b:<9} {note}")


if __name__ == "__main__":
    main()
