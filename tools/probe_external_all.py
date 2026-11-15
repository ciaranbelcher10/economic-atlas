#!/usr/bin/env python3
"""External check of every served series against the source it cites.

Run from the repo root on a machine with normal internet access:
    python3 tools/probe_external_all.py            # all economies
    python3 tools/probe_external_all.py uk de      # some economies

Read-only. Standard library only. Writes probe_external_report.csv and
prints a summary. For each (economy, series) it pulls the cited source
independently (FRED, World Bank, Eurostat, BIS, ECB, IMF WEO, OECD, OpenDOSM),
then finds the transform that lines the source up with what the site serves
(identity, rescaling, year-on-year, period-on-period, trailing four-quarter
sum, annual mean) and reports:

    MATCH     every overlapping point within tolerance
    DIFF      at least one overlapping point outside tolerance (worst shown)
    NEWER     matches, but the source has a later period than the site
    NOMATCH   source pulled, but no transform lines it up (needs a look)
    NOCODE    the citation names no pullable series (checked by hand instead)
    ERROR     the source could not be pulled (network, renamed series)
"""
import csv, glob, io, json, math, os, re, ssl, sys, time, urllib.request, urllib.error
try:
    import certifi
    CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    CTX = ssl.create_default_context()
from concurrent.futures import ThreadPoolExecutor

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15", "Accept": "application/json, text/csv, */*"}
TOL_REL, TOL_ABS = 0.002, 0.051      # 0.2% for levels, 0.05 for rates/percentages
LOOKBACK = 40                        # compare the latest 40 overlapping points

ISO3 = {"uk":"GBR","us":"USA","ez":"EMU","de":"DEU","fr":"FRA","it":"ITA","es":"ESP","nl":"NLD","be":"BEL","at":"AUT",
 "pt":"PRT","ie":"IRL","fi":"FIN","gr":"GRC","lu":"LUX","sk":"SVK","si":"SVN","ee":"EST","lv":"LVA","lt":"LTU","cy":"CYP",
 "mt":"MLT","hr":"HRV","bg":"BGR","ro":"ROU","hu":"HUN","cz":"CZE","pl":"POL","dk":"DNK","se":"SWE","no":"NOR","is":"ISL",
 "ch":"CHE","tr":"TUR","jp":"JPN","cn":"CHN","in":"IND","kr":"KOR","au":"AUS","nz":"NZL","ca":"CAN","mx":"MEX","br":"BRA",
 "ar":"ARG","cl":"CHL","co":"COL","pe":"PER","za":"ZAF","ng":"NGA","eg":"EGY","ma":"MAR","sa":"SAU","il":"ISR","id":"IDN",
 "my":"MYS","ph":"PHL","sg":"SGP","th":"THA","vn":"VNM","pk":"PAK","hk":"HKG","tw":"TWN"}
CITE_NAME = {"ar": "Argentina", "au": "Australia", "at": "Austria", "be": "Belgium", "br": "Brazil", "bg": "Bulgaria", "ca": "Canada", "uk": "UK", "cl": "Chile", "cn": "China", "co": "Colombia", "hr": "Croatia", "cy": "Cyprus", "cz": "Czechia", "dk": "Denmark", "eg": "Egypt", "ee": "Estonia", "ez": "Eurozone", "fi": "Finland", "fr": "France", "de": "Germany", "gr": "Greece", "hk": "Hong Kong", "hu": "Hungary", "is": "Iceland", "in": "India", "id": "Indonesia", "ie": "Ireland", "il": "Israel", "it": "Italy", "jp": "Japan", "lv": "Latvia", "lt": "Lithuania", "lu": "Luxembourg", "my": "Malaysia", "mt": "Malta", "mx": "Mexico", "ma": "Morocco", "nl": "Netherlands", "nz": "New Zealand", "ng": "Nigeria", "no": "Norway", "pk": "Pakistan", "pe": "Peru", "ph": "Philippines", "pl": "Poland", "pt": "Portugal", "ro": "Romania", "sa": "Saudi Arabia", "sg": "Singapore", "sk": "Slovakia", "si": "Slovenia", "za": "South Africa", "kr": "South Korea", "es": "Spain", "se": "Sweden", "ch": "Switzerland", "tw": "Taiwan", "th": "Thailand", "tr": "Turkey", "us": "US", "vn": "Vietnam"}
EUROSTAT_GEO = {"uk":"UK","gr":"EL","ez":"EA21"}
TODAY = time.strftime("%Y-%m")

def get(url, tries=3):
    last = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=(150 if "worldbank" in url else 60), context=CTX) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code in (400, 404): raise
            last = e
        except Exception as e:
            last = e
        time.sleep(2 * (i + 1))
    raise RuntimeError(f"{type(last).__name__}: {str(last)[:80]}")

def preflight():
    key = os.environ.get("FRED_API_KEY")
    tests = {
        "FRED": ("https://api.stlouisfed.org/fred/series/observations?series_id=GDP&limit=1&file_type=json&api_key=" + key)
                if key else "https://fred.stlouisfed.org/graph/fredgraph.csv?id=GDP",
        "World Bank": "https://api.worldbank.org/v2/country/GBR/indicator/SP.POP.TOTL?format=json&per_page=1",
        "Eurostat": "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_hicp_manr?geo=DE&lastTimePeriod=1",
        "IMF": "https://www.imf.org/external/datamapper/api/v1/NGDP_RPCH/GBR",
        "BIS": "https://stats.bis.org/api/v1/data/WS_CBPOL/M.GB/all?lastNObservations=1&format=csv",
        "OECD": "https://sdmx.oecd.org/public/rest/dataflow/OECD.SDD.STES/DSD_STES@DF_CLI",
    }
    if not key:
        print("Note: FRED_API_KEY is not set; using FRED's public CSV, which often times out.")
    ok = 0
    for name, url in tests.items():
        try:
            get(url, tries=1); print(f"  reachable  {name}"); ok += 1
        except Exception as e:
            print(f"  BLOCKED    {name}: {e}")
    return ok > 0

# ---------- period helpers ----------
def to_period(date, freq):
    date = str(date).strip()
    m = re.match(r"(\d{4})-(\d{2})(?:-\d{2})?$", date)
    q = re.match(r"(\d{4})-?Q([1-4])$", date)
    y = re.match(r"(\d{4})$", date)
    mm = re.match(r"(\d{4})M(\d{2})$", date)
    if q: return f"{q.group(1)}-Q{q.group(2)}"
    if mm: return f"{mm.group(1)}-{mm.group(2)}"
    if m:
        yr, mo = int(m.group(1)), int(m.group(2))
        if freq == "quarters": return f"{yr}-Q{(mo - 1) // 3 + 1}"
        if freq == "years": return str(yr)
        return f"{yr}-{mo:02d}"
    if y: return y.group(1)
    return None

def prev_period(p, back=1):
    q = re.match(r"(\d{4})-Q([1-4])$", p); m = re.match(r"(\d{4})-(\d{2})$", p)
    if q:
        n = int(q.group(1)) * 4 + int(q.group(2)) - 1 - back
        return f"{n // 4}-Q{n % 4 + 1}"
    if m:
        n = int(m.group(1)) * 12 + int(m.group(2)) - 1 - back
        return f"{n // 12}-{n % 12 + 1:02d}"
    if re.match(r"\d{4}$", p): return str(int(p) - back)
    return None

def per_year(p):
    return 4 if "-Q" in p else (12 if re.match(r"\d{4}-\d{2}$", p) else 1)

# ---------- sources ----------
def fred(code, freq):
    key = os.environ.get("FRED_API_KEY")
    out = {}
    if key:
        js = json.loads(get("https://api.stlouisfed.org/fred/series/observations?series_id="
                            + code + "&api_key=" + key + "&file_type=json"))
        for o in js.get("observations", []):
            if o.get("value") in (".", "", None): continue
            p = to_period(o["date"], freq)
            if p: out[p] = float(o["value"])
        return {code: out}
    txt = get("https://fred.stlouisfed.org/graph/fredgraph.csv?id=" + code)
    for row in list(csv.reader(io.StringIO(txt)))[1:]:
        if len(row) < 2 or row[1] in (".", ""): continue
        p = to_period(row[0], freq)
        if p: out[p] = float(row[1])
    return {code: out}

def worldbank(code, cc):
    txt = get(f"https://api.worldbank.org/v2/country/{ISO3[cc]}/indicator/{code}?format=json&per_page=400")
    js = json.loads(txt)
    rows = js[1] if isinstance(js, list) and len(js) > 1 and js[1] else []
    return {code: {r["date"]: float(r["value"]) for r in rows if r.get("value") is not None}}

def eurostat(ds, cc, freq):
    geos = ["EA21", "EA20", "EA"] if cc == "ez" else [EUROSTAT_GEO.get(cc, cc.upper())]
    txt = None
    for geo in geos:
        try:
            txt = get(f"https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/{ds}?geo={geo}&sinceTimePeriod=2015")
            if '"value":{}' not in txt.replace(" ", ""): break
        except Exception:
            continue
    if txt is None: raise RuntimeError("no euro-area geo code returned data")
    js = json.loads(txt)
    ids, size = js["id"], js["size"]
    cats = [sorted(js["dimension"][d]["category"]["index"].items(), key=lambda kv: kv[1]) for d in ids]
    tdim = ids.index("time")
    out = {}
    for flat, v in js["value"].items():
        flat = int(flat); idx = []
        for s in reversed(size):
            idx.append(flat % s); flat //= s
        idx.reverse()
        key = "|".join(cats[i][idx[i]][0] for i in range(len(ids)) if i != tdim and size[i] > 1)
        p = to_period(cats[tdim][idx[tdim]][0].replace("-", "") if "Q" in cats[tdim][idx[tdim]][0] else cats[tdim][idx[tdim]][0], freq)
        if p: out.setdefault(ds + ":" + key, {})[p] = float(v)
    return out

def bis(cc):
    txt = get(f"https://stats.bis.org/api/v1/data/WS_CBPOL/M.{cc.upper() if cc != 'uk' else 'GB'}/all?startPeriod=2000&format=csv")
    out = {}
    for row in csv.DictReader(io.StringIO(txt)):
        p = to_period(row.get("TIME_PERIOD", ""), "months")
        if p and row.get("OBS_VALUE") not in (None, ""): out[p] = float(row["OBS_VALUE"])
    return {"WS_CBPOL": out}

def imf_weo(code, cc):
    js = json.loads(get(f"https://www.imf.org/external/datamapper/api/v1/{code}/{ISO3[cc]}"))
    vals = js.get("values", {}).get(code, {}).get(ISO3[cc], {})
    return {code: {str(k): float(v) for k, v in vals.items() if v is not None}}

def oecd_bci(cc):
    txt = get(f"https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_CLI,/{ISO3[cc]}.M.BCICP...AA...H?startPeriod=2010-01&format=csvfilewithlabels")
    out = {}
    for row in csv.DictReader(io.StringIO(txt)):
        p = to_period(row.get("TIME_PERIOD", ""), "months")
        if p and row.get("OBS_VALUE"): out[p] = float(row["OBS_VALUE"])
    return {"BCICP": out}

def opendosm(dataset):
    js = json.loads(get(f"https://api.data.gov.my/data-catalogue?id={dataset}&limit=100000"))
    cols = {}
    for r in js:
        p = to_period(r.get("date", ""), "months")
        if not p: continue
        tag = "|".join(f"{k}={v}" for k, v in r.items() if isinstance(v, str) and k != "date")
        for k, v in r.items():
            if isinstance(v, (int, float)):
                cols.setdefault(f"{dataset}:{tag}:{k}", {})[p] = float(v)
    return cols

# ---------- citation parsing ----------
RX = {
 "fred": re.compile(r"\bFRED(?: series)?\s+([A-Z0-9_]{4,})|\b([A-Z]{2,}[A-Z0-9]{3,}(?:M|Q|A)\d{3}[A-Z]?)\b|\b(CP0000[A-Z]{2}M086NEST|IRLTLT01[A-Z]{2}M156N|DEX[A-Z]{4})\b"),
 "wb": re.compile(r"\b((?:NY|SP|NE|BN|BX|GC|FP|PA|SL)\.[A-Z0-9.]+[A-Z0-9])\b"),
 "eurostat": re.compile(r"Eurostat[^·]*?\b([a-z]{3,5}_[a-z0-9_]+|tei[a-z]{2}\d{3})\b"),
 "weo": re.compile(r"World Economic Outlook \(([A-Z_]+)\)|\b(NGDP_RPCH|PCPIPCH|GGXCNL_NGDP|GGXWDG_NGDP|BCA_NGDPD|LUR)\b"),
 "dosm": re.compile(r"OpenDOSM ([a-z_]+)"),
}

def plan(source):
    s = source or ""
    m = RX["fred"].search(s)
    if m: return ("fred", next(g for g in m.groups() if g))
    m = RX["wb"].search(s)
    if m: return ("wb", m.group(1))
    m = RX["eurostat"].search(s)
    if m: return ("eurostat", m.group(1))
    m = RX["weo"].search(s)
    if m: return ("weo", next(g for g in m.groups() if g))
    m = RX["dosm"].search(s)
    if m: return ("dosm", m.group(1))
    if "WS_CBPOL" in s or ("BIS" in s and "policy" in s.lower()): return ("bis", "WS_CBPOL")
    if "BCICP" in s: return ("oecd_bci", "BCICP")
    return (None, None)

# ---------- matching ----------
def fx_rate(fx, p):
    h = (fx or {}).get("history") or []
    if not h: return (fx or {}).get("rate")
    y = p[:4]; q = re.match(r"(\d{4})-Q([1-4])$", p)
    if q:
        s0 = (int(q.group(2)) - 1) * 3 + 1
        want = [f"{y}-{m:02d}" for m in (s0, s0 + 1, s0 + 2)]
        m = [v for k, v in h if k in want]
    elif re.match(r"\d{4}-\d{2}$", p):
        m = [v for k, v in h if k == p]
    else:
        m = [v for k, v in h if k.startswith(y)]
    if not m: m = [v for k, v in h if k[:4] == y] or [v for k, v in h if k == y]
    if not m:   # as the site does: the nearest period in the history
        def mk(x):
            mm = re.match(r"(\d{4})(?:-(\d{2}))?", x); return int(mm.group(1)) * 12 + (int(mm.group(2)) - 1 if mm.group(2) else 6)
        t = mk(p if "-Q" not in p else p[:4] + "-%02d" % ((int(p[-1]) - 1) * 3 + 2))
        m = [min(h, key=lambda kv: abs(mk(kv[0]) - t))[1]]
    return sum(m) / len(m) if m else None

def transforms(src, fx=None):
    keys = sorted(src)
    yield "identity", src
    if fx and fx.get("history"):
        for k in (1, 1e-3, 1e-6):
            out = {}
            for p, v in src.items():
                r = fx_rate(fx, p)
                if r: out[p] = (v * r if fx.get("direction") == "divide" else v / r) * k
            yield f"to local currency x{k:g}", out
    for k in (1e-3, 1e3, 1e-6, 1e6, 1e-9, 1e9):
        yield f"x{k:g}", {p: v * k for p, v in src.items()}
    yield "yoy%", {p: (src[p] / src[q] - 1) * 100 for p in keys
                   for q in [prev_period(p, per_year(p))] if q in src and src[q]}
    yield "pop%", {p: (src[p] / src[q] - 1) * 100 for p in keys
                   for q in [prev_period(p)] if q in src and src[q]}
    if any("-Q" in p for p in keys):
        s4 = {}
        for p in keys:
            w = [p, prev_period(p), prev_period(p, 2), prev_period(p, 3)]
            if all(x in src for x in w): s4[p] = sum(src[x] for x in w)
        yield "sum4q", s4
        for k in (1e-3, 1e3):
            yield f"sum4q x{k:g}", {p: v * k for p, v in s4.items()}

def compare(ours, theirs):
    common = sorted(set(ours) & set(theirs))[-LOOKBACK:]
    if len(common) < 3: return None
    worst, wp = 0.0, None
    for p in common:
        a, b = ours[p], theirs[p]
        tol = max(abs(b) * TOL_REL, TOL_ABS if abs(b) < 1000 else 0)
        dev = abs(a - b) - tol
        if dev > worst: worst, wp = dev, p
    med = sorted(abs(ours[p] - theirs[p]) / (abs(theirs[p]) + 1e-9) for p in common)[len(common) // 2]
    return {"n": len(common), "worst_excess": worst, "worst_period": wp, "median_rel": med,
            "ours": ours.get(wp) if wp else None, "theirs": theirs.get(wp) if wp else None}

def check(cc, key, series, source, fx=None):
    ours = {p: v for p, v in series.get("points", []) if v is not None}
    kind, code = plan(source)
    row = {"economy": cc, "series": key, "kind": kind or "", "code": code or "", "our_latest": "", "src_latest": ""}
    if ours: row["our_latest"] = max(ours)
    if not kind: return {**row, "status": "NOCODE"}
    freq = series.get("freq", "")
    try:
        if kind == "fred": cand = fred(code, freq)
        elif kind == "wb": cand = worldbank(code, cc)
        elif kind == "eurostat": cand = eurostat(code, cc, freq)
        elif kind == "weo": cand = imf_weo(code, cc)
        elif kind == "dosm": cand = opendosm(code)
        elif kind == "bis": cand = bis(cc)
        elif kind == "oecd_bci": cand = oecd_bci(cc)
    except Exception as e:
        return {**row, "status": "ERROR", "detail": str(e)[:120]}
    best = None
    for cname, src in cand.items():
        for tname, t in transforms(src, fx):
            r = compare(ours, t)
            if r and (best is None or (r["worst_excess"], r["median_rel"]) < (best[2]["worst_excess"], best[2]["median_rel"])):
                best = (cname, tname, r, t)
    if not best or best[2]["median_rel"] > 0.05:
        return {**row, "status": "NOMATCH", "detail": f"{len(cand)} candidate series"}
    cname, tname, r, t = best
    row.update({"matched": cname, "transform": tname, "overlap": r["n"], "src_latest": max(t)})
    if r["worst_excess"] > 0:
        return {**row, "status": "DIFF", "detail": f"{r['worst_period']}: site {r['ours']} vs source {r['theirs']}"}
    past = [p for p in t if p[:7] <= TODAY and (len(p) > 4 or p < TODAY[:4])]
    if past and max(past) > max(ours):
        return {**row, "status": "NEWER", "detail": f"source has {max(t)}, site stops at {max(ours)}"}
    return {**row, "status": "MATCH"}

def main():
    args = sys.argv[1:]
    recheck = None
    if args and args[0] == "--recheck":
        recheck = {(r["economy"], r["series"]) for r in csv.DictReader(open(args[1])) if r["status"] not in ("MATCH", "NOCODE")}
        args = args[2:]
        print(f"rechecking {len(recheck)} series from the last report")
    want = set(a.lower() for a in args)
    if not preflight(): sys.exit(1)
    cites = json.load(open("data-metric-sources.json"))
    jobs = []
    for f in sorted(glob.glob("data-??.json")):
        cc = f[5:7]
        if want and cc not in want: continue
        d = json.load(open(f))
        cn = CITE_NAME.get(cc)
        for key, s in d.get("series", {}).items():
            src = ((cites.get(cn) or {}).get(key) or {}).get("source", "") if cn else ""
            if not src: src = s.get("label", "")
            jobs.append((cc, key, s, src, d.get("fx_to_usd")))
    if recheck is not None: jobs = [j for j in jobs if (j[0], j[1]) in recheck]
    print(f"checking {len(jobs)} series ...", flush=True)
    with ThreadPoolExecutor(3 if recheck is not None else 6) as ex:
        rows = list(ex.map(lambda j: check(*j), jobs))
    cols = ["economy", "series", "status", "kind", "code", "matched", "transform", "overlap", "our_latest", "src_latest", "detail"]
    outname = "probe_external_recheck.csv" if recheck is not None else "probe_external_report.csv"
    with open(outname, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore"); w.writeheader(); w.writerows(rows)
    from collections import Counter
    c = Counter(r["status"] for r in rows)
    print("summary:", dict(c))
    for st in ("DIFF", "NEWER", "NOMATCH", "ERROR"):
        for r in [r for r in rows if r["status"] == st][:60]:
            print(f"{st:8} {r['economy']:3} {r['series']:22} {r.get('code',''):24} {r.get('detail','')}")
    print("full report:", outname)

if __name__ == "__main__":
    main()
