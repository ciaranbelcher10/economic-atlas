#!/usr/bin/env python3
"""Verify every figure the Atlas serves, raw and transformed, against a source outside the Atlas.

Run from the repo root on a machine with normal internet access (Ciaran's Mac):

    SSL_CERT_FILE=$(python3 -m certifi) python3 tools/verify_all.py
    SSL_CERT_FILE=$(python3 -m certifi) python3 tools/verify_all.py uk de     # some economies only

Read-only: it changes no site file. Standard library only. Downloads are cached in .verify_cache/ (one file per
URL, kept for 12 hours), so a run that is interrupted resumes where it stopped and a rerun is quick.

PART A  every stored series against the source it cites (tools/probe_external_all.py: FRED, World Bank,
        Eurostat, BIS, IMF WEO, OECD, OpenDOSM).
PART B  every transformation the site applies, rebuilt here independently from the data files, against the
        published equivalent:
          gdp_lcu          annual GDP, national currency         IMF WEO NGDP
          gdp_usd          annual GDP, US$                       IMF WEO NGDPD, World Bank NY.GDP.MKTP.CD
          gdp_pc_usd       GDP per person, US$                   IMF WEO NGDPDPC, World Bank NY.GDP.PCAP.CD
          gdp_pc_lcu       GDP per person, national currency     World Bank NY.GDP.PCAP.CN
          real_growth      annual real GDP growth                IMF WEO NGDP_RPCH, World Bank NY.GDP.MKTP.KD.ZG
          real_usd_ratio   real GDP in US$ (the site's single-rate conversion) / nominal US$ GDP, latest year:
                           near 1 for a sensible level, near 0 for a stale base year (Argentina)
          cpi_annual       mean of monthly y/y inflation          IMF WEO PCPIPCH (annual average)
          unemp_annual     mean unemployment rate                IMF WEO LUR
          fx_annual        mean exchange rate, units per US$     World Bank PA.NUS.FCRF
          ca_gdp           current account, % of GDP              IMF WEO BCA_NGDPD
          exports_usd / imports_usd / trade_usd   goods trade in US$, annual   World Bank BX/BM.GSR.MRCH.CD
        plus the site's own published US$ figures (rankings pages) against the same outside figures.

SEVERITY (agreed 15 Nov 2026)
  SERIOUS  level gap over 5%, rate gap over 0.3 points (0.5 for the annual-average approximations), a unit or
           exchange-rate sized error (ratio near 10^k or near the exchange rate), or a source with a later period
  MINOR    a gap under those limits
  BASIS    a known definitional difference (fiscal years, BoP vs customs trade); listed, not counted as errors
  OK       within 0.5% for levels, 0.1 points for rates

Writes verify_report.csv (every comparison) and verify_summary.txt, and prints the serious list. With
probe_external_report.csv from an earlier run present it also lists series that matched before and do not now.
"""
import csv, glob, hashlib, io, json, math, os, re, sys, time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import probe_external_all as P   # noqa: E402

CACHE = ".verify_cache"
CACHE_HOURS = 12
YEARS = range(2015, 2026)        # annual comparisons
FY_ECONOMIES = {"in": "April-March fiscal year", "eg": "July-June fiscal year", "pk": "July-June fiscal year"}
GDP_ANNUAL_RATE = {"us", "jp"}   # quarterly GDP published at an annual rate: the year is the mean of its quarters
os.makedirs(CACHE, exist_ok=True)

# ---------- cached fetch (wraps the probe's get) ----------
_raw_get = P.get
def cached_get(url, tries=3):
    fn = os.path.join(CACHE, hashlib.sha1(url.encode()).hexdigest())
    if os.path.exists(fn) and time.time() - os.path.getmtime(fn) < CACHE_HOURS * 3600:
        return open(fn, encoding="utf-8").read()
    if "api.imf.org" in url:   # the IMF's SDMX 3.0 API answers CSV only when asked for it
        import urllib.request
        last = None
        for i in range(4):
            try:
                req = urllib.request.Request(url, headers=dict(P.UA, Accept="text/csv"))
                with urllib.request.urlopen(req, timeout=120, context=P.CTX) as r:
                    txt = r.read().decode("utf-8", "replace")
                break
            except Exception as e:
                last = e; time.sleep(3 * (i + 1))
        else:
            raise RuntimeError(f"{type(last).__name__}: {str(last)[:80]}")
    else:
        txt = _raw_get(url, tries=max(tries, 4))
    with open(fn, "w", encoding="utf-8") as fh:
        fh.write(txt)
    return txt
P.get = cached_get

def imf(code, cc):
    try:
        return P.imf_weo(code, cc).get(code, {})
    except Exception:
        return {}

def wb(code, cc):
    try:
        return P.worldbank(code, cc).get(code, {})
    except Exception:
        return {}

# ---------- reading the site's own data, independently of the page code ----------
def scale_of(unit):
    u = re.sub(r"\s*\(.*\)$", "", str(unit or "")).strip()
    return 1e6 if u.endswith("m") else 1e9 if u.endswith("bn") else 1e12 if u.endswith("tn") else 1.0

def is_usd_series(series):
    lab = series.get("label", "")
    return str(series.get("unit", "")).startswith("$") and ("NY.GDP.MKTP.CD" in lab or "US$" in lab)

def annual(series, how, cc=""):
    """{year: value}: annual points as they are; quarters summed (or averaged); months averaged or summed.
    A year is used only when every period in it is published."""
    pts = {str(p): v for p, v in series.get("points", []) if v is not None}
    freq = series.get("freq", "")
    out = {}
    for y in range(1990, 2027):
        y = str(y)
        if freq == "years":
            if y in pts: out[y] = pts[y]
            continue
        ps = [f"{y}-Q{q}" for q in range(1, 5)] if freq == "quarters" else [f"{y}-{m:02d}" for m in range(1, 13)]
        vals = [pts.get(p) for p in ps]
        if any(v is None for v in vals): continue
        out[y] = sum(vals) / len(vals) if how == "mean" else sum(vals)
    return out

def fx_annual(fx):
    """Mean units of national currency per US$, by year."""
    if not fx or not fx.get("history"): return {}
    by = {}
    for p, v in fx["history"]:
        if v: by.setdefault(str(p)[:4], []).append(v)
    out = {}
    for y, vs in by.items():
        m = sum(vs) / len(vs)
        out[y] = 1 / m if fx.get("direction") == "multiply" else m
    return out

def site_rankings():
    """US$ GDP (bn) and US$ per person published on the rankings pages: what readers see."""
    out = {}
    for name, f, scale in (("gdp_usd_site", "rankings/gdp-by-country.html", 1e9),
                           ("gdp_pc_usd_site", "rankings/gdp-per-capita-by-country.html", 1e9)):
        if not os.path.exists(f): continue
        s = open(f, encoding="utf-8").read()
        for c, v, y in re.findall(r'data-country="([^"]+)" data-value="([^"]+)"[^>]*?data-period="(\d{4})', s):
            out.setdefault(name, {})[c] = (y, float(v) * scale)
    return out

# ---------- grading ----------
def grade(ours, theirs, kind):
    """kind: 'level' (relative gap) or 'rate' / 'rate_approx' (absolute gap in points)."""
    if ours is None or theirs is None: return ("NOSOURCE", None)
    if kind == "level":
        if theirs == 0: return ("NOSOURCE", None)
        r = ours / theirs
        gap = (r - 1) * 100
        for k in (1e3, 1e6, 1e9, 1e-3, 1e-6, 1e-9):
            if abs(r / k - 1) < 0.05: return ("SERIOUS", gap)          # unit error
        if abs(gap) <= 0.5: return ("OK", gap)
        return ("SERIOUS" if abs(gap) > 5 else "MINOR", gap)
    gap = ours - theirs
    lim = 0.5 if kind == "rate_approx" else 0.3
    if abs(gap) <= 0.1: return ("OK", gap)
    return ("SERIOUS" if abs(gap) > lim else "MINOR", gap)

def compare_years(rows, cc, check, ours, theirs, kind, source, basis=""):
    common = [y for y in YEARS if str(y) in ours and str(y) in theirs]
    if not common:
        rows.append(dict(economy=cc, check=check, source=source, status="NOSOURCE", detail="no overlapping year"))
        return
    worst = None
    for y in common:
        st, gap = grade(ours[str(y)], theirs[str(y)], kind)
        rank = {"OK": 0, "MINOR": 1, "SERIOUS": 2}.get(st, 0)
        if worst is None or rank > worst[0] or (rank == worst[0] and abs(gap or 0) > abs(worst[3] or 0)):
            worst = (rank, st, y, gap)
    _, st, y, gap = worst
    latest = max(common)
    lst, lgap = grade(ours[str(latest)], theirs[str(latest)], kind)
    if basis and st in ("MINOR", "SERIOUS"): st = "BASIS"
    rows.append(dict(economy=cc, check=check, source=source, status=st, years=f"{min(common)}-{latest}",
                     worst_year=y, worst_gap=None if gap is None else round(gap, 3),
                     latest_year=latest, latest_site=round(ours[str(latest)], 3), latest_source=round(theirs[str(latest)], 3),
                     latest_gap=None if lgap is None else round(lgap, 3), detail=basis))

# ---------- part B, one economy ----------
def part_b(cc, d, rk):
    rows = []
    s = d.get("series", {})
    fx = d.get("fx_to_usd")
    fxa = fx_annual(fx)
    basis = FY_ECONOMIES.get(cc, "")
    g = s.get("gdp_level")
    if g:
        how = "mean" if cc in GDP_ANNUAL_RATE else "sum"
        lev = {y: v * scale_of(g["unit"]) for y, v in annual(g, how, cc).items()}
        if is_usd_series(g):
            usd = lev
        else:
            compare_years(rows, cc, "gdp_lcu", {y: v / 1e9 for y, v in lev.items()}, imf("NGDP", cc), "level", "IMF WEO NGDP", basis)
            usd = {y: v / fxa[y] for y, v in lev.items() if y in fxa} if fxa else {}
        compare_years(rows, cc, "gdp_usd", {y: v / 1e9 for y, v in usd.items()}, imf("NGDPD", cc), "level", "IMF WEO NGDPD", basis)
        compare_years(rows, cc, "gdp_usd", usd, wb("NY.GDP.MKTP.CD", cc), "level", "World Bank NY.GDP.MKTP.CD", basis)
        r = s.get("gdp_real")
        if r and usd:
            real = {y: v * scale_of(r["unit"]) for y, v in annual(r, how, cc).items()}
            gr = {y: (real[y] / real[str(int(y) - 1)] - 1) * 100 for y in real if str(int(y) - 1) in real}
            compare_years(rows, cc, "real_growth", gr, imf("NGDP_RPCH", cc), "rate", "IMF WEO NGDP_RPCH", basis)
            compare_years(rows, cc, "real_growth", gr, wb("NY.GDP.MKTP.KD.ZG", cc), "rate", "World Bank NY.GDP.MKTP.KD.ZG", basis)
            ly = max(set(real) & set(usd), default=None)
            if ly and not is_usd_series(g) and ly in fxa:
                ratio = real[ly] / fxa[ly] / usd[ly]
                st = "SERIOUS" if ratio < 0.2 or ratio > 5 else ("MINOR" if ratio < 0.5 or ratio > 2 else "OK")
                rows.append(dict(economy=cc, check="real_usd_ratio", source="real GDP in US$ / nominal US$ GDP",
                                 status=st, latest_year=ly, latest_site=round(ratio, 4),
                                 detail="the site's single-rate conversion; near 0 means a stale base year"))
    pc = s.get("gdp_per_capita")
    if pc:
        pca = annual(pc, "sum", cc)
        if str(pc.get("unit", "")).startswith("$") and g and is_usd_series(g):
            pcu = pca
        else:
            compare_years(rows, cc, "gdp_pc_lcu", pca, wb("NY.GDP.PCAP.CN", cc), "level", "World Bank NY.GDP.PCAP.CN", basis)
            pcu = {y: v / fxa[y] for y, v in pca.items() if y in fxa}
        compare_years(rows, cc, "gdp_pc_usd", pcu, imf("NGDPDPC", cc), "level", "IMF WEO NGDPDPC", basis)
        compare_years(rows, cc, "gdp_pc_usd", pcu, wb("NY.GDP.PCAP.CD", cc), "level", "World Bank NY.GDP.PCAP.CD", basis)
    c = s.get("cpi")
    if c and c.get("unit") == "%":
        compare_years(rows, cc, "cpi_annual", annual(c, "mean", cc), imf("PCPIPCH", cc), "rate_approx", "IMF WEO PCPIPCH")
    u = s.get("unemployment")
    if u:
        compare_years(rows, cc, "unemp_annual", annual(u, "mean", cc), imf("LUR", cc), "rate_approx", "IMF WEO LUR")
    if fxa:
        eur = (d.get("fx_to_usd") or {}).get("pair", "").startswith("EUR")
        compare_years(rows, cc, "fx_annual", fxa, wb("PA.NUS.FCRF", cc), "level", "World Bank PA.NUS.FCRF",
                      "series held in euros; the World Bank reports the former national currency" if eur and cc not in ("ez",) else "")
    ca = s.get("current_account")
    if ca and ca.get("unit") == "%":
        compare_years(rows, cc, "ca_gdp", annual(ca, "mean", cc), imf("BCA_NGDPD", cc), "rate", "IMF WEO BCA_NGDPD")
    for key, code in (("exports", "BX.GSR.MRCH.CD"), ("imports", "BM.GSR.MRCH.CD")):
        t = s.get(key)
        if t and fxa:
            tu = {y: v * scale_of(t["unit"]) / (1 if str(t["unit"]).startswith("US$") else fxa[y])
                  for y, v in annual(t, "sum", cc).items() if y in fxa}
            compare_years(rows, cc, key + "_usd", tu, wb(code, cc), "level", f"World Bank {code} (balance of payments)",
                          "goods on a balance-of-payments basis; customs figures differ by a few per cent")
    # what readers see on the rankings
    name = P.CITE_NAME.get(cc)
    for key, check, imfc, wbc in (("gdp_usd_site", "gdp_usd_rankings", "NGDPD", "NY.GDP.MKTP.CD"),
                                  ("gdp_pc_usd_site", "gdp_pc_usd_rankings", "NGDPDPC", "NY.GDP.PCAP.CD")):
        hit = rk.get(key, {}).get(name)
        if hit:
            y, v = hit
            ours = {y: v / 1e9} if key == "gdp_usd_site" else {y: v}
            compare_years(rows, cc, check, ours, imf(imfc, cc), "level", f"IMF WEO {imfc}", basis)
            compare_years(rows, cc, check, {y: v} if key == "gdp_pc_usd_site" else {y: v}, wb(wbc, cc), "level",
                          f"World Bank {wbc}", basis)
    return rows


# ---------- PART C: series the probe could not map to a code (OECD prices and labour, ECB IRS) ----------
import threading
_oecd_lock = threading.Lock()
OECD_PRICES = ["https://sdmx.oecd.org/public/rest/data/OECD.SDD.TPS,DSD_PRICES@DF_PRICES_ALL,1.0",
               "https://sdmx.oecd.org/public/rest/data/OECD.SDD.TPS,DSD_PRICES_COICOP2018@DF_PRICES_C2018_ALL,1.0"]
OECD_UNEMP = "https://sdmx.oecd.org/public/rest/data/OECD.SDD.TPS,DSD_LFS@DF_IALFS_UNE_M,1.0/"

def _oecd_csv(url, group_cols):
    """OECD answers 429 when hit quickly: one request at a time, two seconds apart (cached afterwards)."""
    with _oecd_lock:
        fn = os.path.join(CACHE, hashlib.sha1(url.encode()).hexdigest())
        fresh = os.path.exists(fn) and time.time() - os.path.getmtime(fn) < CACHE_HOURS * 3600
        txt = cached_get(url)
        if not fresh:
            time.sleep(2)
    out = {}
    for row in csv.DictReader(io.StringIO(txt)):
        per = P.to_period(row.get("TIME_PERIOD", ""), "")
        v = row.get("OBS_VALUE")
        if not per or v in (None, ""):
            continue
        key = "|".join(row.get(c, "") for c in group_cols)
        out.setdefault(key, {})[per] = float(v)
    return out

def oecd_cpi(cc, freq):
    f = "Q" if freq == "quarters" else "M"
    out = {}
    for base in OECD_PRICES:
        for tail in (f"CPI.IX._T..", f"CPI.PA._T..GY", f"CPI.PA._T..G1"):
            try:
                out.update({base[-25:] + ":" + k: v for k, v in _oecd_csv(
                    f"{base}/{P.ISO3[cc]}.{f}..{tail}?format=csvfile&startPeriod=2010",
                    ["METHODOLOGY", "UNIT_MEASURE", "ADJUSTMENT", "TRANSFORMATION"]).items()})
            except Exception:
                continue
    return out

def oecd_unemp(cc):
    return _oecd_csv(f"{OECD_UNEMP}{P.ISO3[cc]}.UNE_LF_M.._Z.Y._T.Y_GE15..M?format=csvfile&startPeriod=2010",
                     ["ADJUSTMENT", "AGE"])

def ecb_irs(key):
    txt = cached_get(f"https://data-api.ecb.europa.eu/service/data/IRS/{key}?format=csvdata&startPeriod=2010")
    out = {}
    for row in csv.DictReader(io.StringIO(txt)):
        per = P.to_period(row.get("TIME_PERIOD", ""), "months")
        if per and row.get("OBS_VALUE"):
            out[per] = float(row["OBS_VALUE"])
    return {"IRS:" + key: out}

def part_c(cc, key, series, source):
    """A Part A NOCODE row, retried against the sources the probe does not read."""
    s = source or ""
    try:
        if re.search(r"OECD (live prices|prices database)", s):
            cand = oecd_cpi(cc, series.get("freq", ""))
            kind = "oecd_prices"
        elif "DF_IALFS_UNE_M" in s:
            cand = oecd_unemp(cc); kind = "oecd_lfs"
        elif re.search(r"\bM\.[A-Z]{2}\.L\.L40\.CI\.0000\.[A-Z]{3}\.N\.Z\b", s):
            k = re.search(r"\bM\.[A-Z]{2}\.L\.L40\.CI\.0000\.[A-Z]{3}\.N\.Z\b", s).group(0)
            cand = ecb_irs(k); kind = "ecb_irs"
        else:
            return None
    except Exception as e:
        return {"economy": cc, "series": key, "status": "ERROR", "kind": "C", "detail": str(e)[:120]}
    ours = {p: v for p, v in series.get("points", []) if v is not None}
    best = None
    for cname, src in cand.items():
        for tname, t in P.transforms(src):
            r = P.compare(ours, t)
            if r and (best is None or (r["worst_excess"], r["median_rel"]) < (best[2]["worst_excess"], best[2]["median_rel"])):
                best = (cname, tname, r, t)
    row = {"economy": cc, "series": key, "kind": kind, "code": "", "our_latest": max(ours) if ours else ""}
    if not best or best[2]["median_rel"] > 0.05:
        return {**row, "status": "NOMATCH", "detail": f"{len(cand)} candidate series"}
    cname, tname, r, t = best
    row.update({"matched": cname, "transform": tname, "overlap": r["n"], "src_latest": max(t)})
    if r["worst_excess"] > 0:
        return {**row, "status": "DIFF", "detail": f"{r['worst_period']}: site {r['ours']} vs source {r['theirs']}"}
    past = [p for p in t if p[:7] <= P.TODAY and (len(p) > 4 or p < P.TODAY[:4])]
    if past and max(past) > max(ours):
        return {**row, "status": "NEWER", "detail": f"source has {max(t)}, site stops at {max(ours)}"}
    return {**row, "status": "MATCH"}


# ---------- PART D: the remaining sources with public APIs, the probe's missed FRED codes, and per person ----------
IMF_API = "https://api.imf.org/external/sdmx/3.0/data/dataflow/IMF.STA/"
QNA = "https://sdmx.oecd.org/public/rest/data/OECD.SDD.NAD,DSD_NAMAIN1@DF_QNA,1.1/"
FINMARK = "https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_FINMARK/"
CLI = "https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_CLI/"
BCRP = "https://estadisticas.bcrp.gob.pe/estadisticas/series/api/{code}/json/2010-1/2026-12"
CSD = "https://www.censtatd.gov.hk/api/get.php?id={id}&lang=en&full_series=1"
DOSM = "https://api.data.gov.my/data-catalogue?id={id}&limit=100000"
MESES = {"Ene": 1, "Feb": 2, "Mar": 3, "Abr": 4, "May": 5, "Jun": 6, "Jul": 7, "Ago": 8, "Sep": 9, "Set": 9,
         "Oct": 10, "Nov": 11, "Dic": 12}

def _csv_groups(txt, cols, filt=None):
    out = {}
    for row in csv.DictReader(io.StringIO(txt)):
        if filt and any(row.get(k) != v for k, v in filt.items()):
            continue
        per = P.to_period((row.get("TIME_PERIOD") or "").replace("-M", "-"), "")
        v = row.get("OBS_VALUE")
        if not per or v in (None, "", "NaN"):
            continue
        try:
            out.setdefault("|".join(row.get(c, "") for c in cols), {})[per] = float(v)
        except ValueError:
            pass
    return out

def imf_itg(cc):
    g = _csv_groups(cached_get(IMF_API + f"ITG/~/{P.ISO3[cc]}.*.*.M?c[TIME_PERIOD]=ge:2010-M01"),
                    ["INDICATOR", "VALUATION", "UNIT"])
    xg = next((v for k, v in g.items() if k.startswith("XG|") and k.endswith("|USD")), None)
    mg = next((v for k, v in g.items() if k.startswith("MG|") and k.endswith("|USD")), None)
    if xg and mg:
        g["balance|USD"] = {p: xg[p] - mg[p] for p in xg if p in mg}
    for cur in {k.split("|")[-1] for k in g if not k.endswith("|USD")}:
        x = next((v for k, v in g.items() if k.startswith("XG|") and k.endswith("|" + cur)), None)
        m = next((v for k, v in g.items() if k.startswith("MG|") and k.endswith("|" + cur)), None)
        if x and m:
            g["balance|" + cur] = {p: x[p] - m[p] for p in x if p in m}
    return g

def imf_cpi(cc):
    return _csv_groups(cached_get(IMF_API + f"CPI/~/{P.ISO3[cc]}.CPI._T.*.M?c[TIME_PERIOD]=ge:2010-M01"),
                       ["TYPE_OF_TRANSFORMATION", "INDEX_TYPE", "COICOP_1999"])

def oecd_qna(cc):
    with _oecd_lock:
        txt = cached_get(QNA + f"Q..{P.ISO3[cc]}..........?startPeriod=2010&format=csvfile")
        time.sleep(2)
    return _csv_groups(txt, ["TRANSACTION", "PRICE_BASE", "ADJUSTMENT", "UNIT_MEASURE", "TRANSFORMATION"],
                       {"TRANSACTION": "B1GQ"})

def oecd_finmark(cc):
    with _oecd_lock:
        txt = cached_get(FINMARK + f"{P.ISO3[cc]}.M.........?format=csvfile&startPeriod=2010-01")
        time.sleep(2)
    return _csv_groups(txt, ["MEASURE", "UNIT_MEASURE"], {"MEASURE": "IRLT"})

def oecd_bci_ez():
    with _oecd_lock:
        txt = cached_get(CLI + "EA20.M.BCICP...AA...H?format=csvfile&startPeriod=2010")
        time.sleep(2)
    return _csv_groups(txt, ["MEASURE"])

def bcrp(code):
    js = json.loads(cached_get(BCRP.format(code=code)))
    out = {}
    for row in js.get("periods") or []:
        n = row.get("name", "").strip()
        m = re.fullmatch(r"([A-Z][a-z]{2})\.(\d{4})", n)
        q = re.fullmatch(r"T([1-4])\.(\d{2})", n)
        per = f"{m.group(2)}-{MESES[m.group(1)]:02d}" if m and m.group(1) in MESES else \
              (f"{2000 + int(q.group(2)) if int(q.group(2)) < 50 else 1900 + int(q.group(2))}-Q{q.group(1)}" if q else None)
        try:
            v = float((row.get("values") or [""])[0])
        except ValueError:
            continue
        if per:
            out[per] = v
    return {code: out}

def csd(table):
    js = json.loads(cached_get(CSD.format(id=table)))
    out = {}
    for row in js.get("dataSet") or []:
        per = str(row.get("period", ""))
        m = re.fullmatch(r"(\d{4})(\d{2})", per)
        if not m:
            continue
        p = f"{m.group(1)}-Q{int(m.group(2)) // 3}" if row.get("freq") == "Q" and m.group(2) in ("03", "06", "09", "12") \
            else f"{m.group(1)}-{m.group(2)}"
        try:
            out.setdefault(f"{row.get('sv')}|{row.get('svDesc')}|{row.get('freq')}", {})[p] = float(row.get("figure"))
        except (TypeError, ValueError):
            pass
    if table == "410-50001":   # total exports less imports, the visible trade balance
        ex = next((v for k, v in out.items() if "export" in k.lower() and "total" in k.lower()), None)
        im = next((v for k, v in out.items() if "import" in k.lower()), None)
        if ex and im:
            out["balance"] = {p: ex[p] - im[p] for p in ex if p in im}
    return out

def dosm(dataset):
    rows = json.loads(cached_get(DOSM.format(id=dataset)))
    out = {}
    for r in rows:
        d = str(r.get("date", ""))
        per = P.to_period(d, "quarters" if dataset.startswith("gdp_qtr") else "months")
        if not per:
            continue
        tag = "|".join(f"{k}={v}" for k, v in sorted(r.items()) if isinstance(v, str) and k != "date")
        for k, v in r.items():
            if isinstance(v, (int, float)):
                out.setdefault(f"{dataset}:{tag}:{k}", {})[per] = float(v)
    if dataset.startswith("trade_sitc"):
        tot = {k: v for k, v in out.items() if "section=overall" in k or "section=total" in k}
        ex = next((v for k, v in tot.items() if k.endswith(":exports")), None)
        im = next((v for k, v in tot.items() if k.endswith(":imports")), None)
        if ex and im:
            out["balance"] = {p: ex[p] - im[p] for p in ex if p in im}
    return out

def eurostat_trade_local(cc, key):
    """Eurostat goods trade in euros, converted to national currency at each month's ECB rate (both fetched here)."""
    geo = P.EUROSTAT_GEO.get(cc, cc.upper())
    js = json.loads(cached_get("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/ext_st_27_2020msbec"
                               f"?geo={geo}&partner=WORLD&bclas_bec=TOTAL&unit=MIO_EUR&sinceTimePeriod=2015-01"))
    ids, size = js["id"], js["size"]
    cats = [sorted(js["dimension"][d]["category"]["index"].items(), key=lambda kv: kv[1]) for d in ids]
    tdim = ids.index("time")
    flows = {}
    for flat, v in js["value"].items():
        flat = int(flat); idx = []
        for sz in reversed(size):
            idx.append(flat % sz); flat //= sz
        idx.reverse()
        k = "|".join(cats[i][idx[i]][0] for i in range(len(ids)) if i != tdim and size[i] > 1)
        p = P.to_period(cats[tdim][idx[tdim]][0], "months")
        if p:
            flows.setdefault(k, {})[p] = float(v)
    cur = {"cz": "CZK", "hu": "HUF", "ro": "RON", "pl": "PLN"}.get(cc)
    if cur:
        rates = {}
        txt = cached_get(f"https://data-api.ecb.europa.eu/service/data/EXR/M.{cur}.EUR.SP00.A?format=csvdata&startPeriod=2015-01")
        for row in csv.DictReader(io.StringIO(txt)):
            per = P.to_period(row.get("TIME_PERIOD", ""), "months")
            if per and row.get("OBS_VALUE"):
                rates[per] = float(row["OBS_VALUE"])
        flows = {k + "|in " + cur: {p: v * rates[p] for p, v in s.items() if p in rates} for k, s in flows.items()}
    x = next((v for k, v in flows.items() if k.startswith("EXP")), None)
    m = next((v for k, v in flows.items() if k.startswith("IMP")), None)
    if x and m:
        flows["balance"] = {p: x[p] - m[p] for p in x if p in m}
    return flows

def ecb_fm(key):
    txt = cached_get(f"https://data-api.ecb.europa.eu/service/data/FM/{key}?format=csvdata&startPeriod=2010")
    out = {}
    for row in csv.DictReader(io.StringIO(txt)):
        per = P.to_period(row.get("TIME_PERIOD", ""), "months")
        if per and row.get("OBS_VALUE"):
            out[per] = float(row["OBS_VALUE"])
    return {"FM:" + key: out}

FRED_EXTRA = re.compile(r"\b((?:NGDP|CLVMNAC|CPMNAC)[A-Z0-9]{6,})\b|FRED series (GDP)\b")

def part_d(cc, key, series, source, fx):
    s = source or ""
    try:
        m = FRED_EXTRA.search(s)
        if "IMF international trade in goods" in s:
            cand, kind = imf_itg(cc), "imf_itg"
        elif re.search(r"IMF (consumer price index|[A-Z]{3}\.CPI)|IMF CPI", s):
            cand, kind = imf_cpi(cc), "imf_cpi"
        elif "DF_QNA" in s or "OECD quarterly national accounts" in s:
            cand, kind = oecd_qna(cc), "oecd_qna"
        elif "IRLT" in s:
            cand, kind = oecd_finmark(cc), "oecd_finmark"
        elif "BCICP" in s and cc == "ez":
            cand, kind = oecd_bci_ez(), "oecd_cli"
        elif "BCRP" in s and re.search(r"\b(PN\d{5}[A-Z]{2})\b", s):
            cand, kind = bcrp(re.search(r"\b(PN\d{5}[A-Z]{2})\b", s).group(1)), "bcrp"
        elif "C&SD" in s or "Census and Statistics Department" in s:
            cand, kind = csd("410-50001" if key in ("exports", "imports", "trade_balance") else "310-31001"), "csd"
        elif "OpenDOSM" in s:
            ds = re.search(r"OpenDOSM ([a-z_0-9]+)", s).group(1)
            cand, kind = dosm(ds), "opendosm"
        elif "ext_st_27_2020msbec" in s or (cc in ("at", "pl") and key == "trade_balance" and "Eurostat" in s):
            cand, kind = eurostat_trade_local(cc, key), "eurostat_trade"
        elif "FM.M.U2.EUR.4F.BB.U2_10Y.YLD" in s:
            cand, kind = ecb_fm("M.U2.EUR.4F.BB.U2_10Y.YLD"), "ecb_fm"
        elif m:
            code = m.group(1) or m.group(2)
            cand, kind = P.fred(code, series.get("freq", "")), "fred"
        else:
            return None
    except Exception as e:
        return {"economy": cc, "series": key, "status": "ERROR", "kind": "D", "detail": str(e)[:120]}
    ours = {p: v for p, v in series.get("points", []) if v is not None}
    best = None
    for cname, src in cand.items():
        for tname, t in P.transforms(src, fx):
            r = P.compare(ours, t)
            if r and (best is None or (r["worst_excess"], r["median_rel"]) < (best[2]["worst_excess"], best[2]["median_rel"])):
                best = (cname, tname, r, t)
    row = {"economy": cc, "series": key, "kind": kind, "code": "", "our_latest": max(ours) if ours else ""}
    if not best or best[2]["median_rel"] > 0.05:
        return {**row, "status": "NOMATCH", "detail": f"{len(cand)} candidate series"}
    cname, tname, r, t = best
    row.update({"matched": cname, "transform": tname, "overlap": r["n"], "src_latest": max(t)})
    if r["worst_excess"] > 0:
        return {**row, "status": "DIFF", "detail": f"{r['worst_period']}: site {r['ours']} vs source {r['theirs']}"}
    past = [p for p in t if p[:7] <= P.TODAY and (len(p) > 4 or p < P.TODAY[:4])]
    if past and max(past) > max(ours):
        return {**row, "status": "NEWER", "detail": f"source has {max(t)}, site stops at {max(ours)}"}
    return {**row, "status": "MATCH"}

PER_PERSON_KEYS = ("trade_balance", "exports", "imports", "net_debt", "deficit", "debt_interest")

def per_person(cc, d):
    """Trade, debt and borrowing per person: the site divides each period by that year's population (its own World
    Bank series). Rebuilt here from the stored series and the World Bank's population fetched afresh; also checks
    the site's population series equals the World Bank's for every year the site divides by."""
    rows = []
    s = d.get("series", {})
    site_pop = {str(p): v for p, v in (s.get("population") or {}).get("points", []) if v}
    wbpop = wb("SP.POP.TOTL", cc)
    if not site_pop or not wbpop:
        return rows
    for key in PER_PERSON_KEYS:
        t = s.get(key)
        if not t or not re.search(r"(m|bn|tn)$", str(t.get("unit", ""))):
            continue
        sc = scale_of(t["unit"])
        ours, theirs = {}, {}
        for p, v in t.get("points", []):
            y = str(p)[:4]
            if v is None or y not in site_pop or y not in wbpop or int(y) not in YEARS:
                continue
            ours[str(p)] = v * sc / site_pop[y]
            theirs[str(p)] = v * sc / wbpop[y]
        if not ours:
            continue
        gaps = [abs(ours[p] / theirs[p] - 1) * 100 for p in ours if theirs[p]]
        worst = max(gaps) if gaps else 0
        st = "OK" if worst <= 0.5 else ("SERIOUS" if worst > 5 else "MINOR")
        last = max(ours)
        rows.append(dict(economy=cc, check=key + "_per_person", source="stored series / World Bank SP.POP.TOTL",
                         status=st, worst_gap=round(worst, 3), latest_year=last, latest_site=round(ours[last], 2),
                         latest_source=round(theirs[last], 2)))
    return rows

# ---------- main ----------
def main():
    want = {a.lower() for a in sys.argv[1:]}
    if not P.preflight(): sys.exit(1)
    files = [f for f in sorted(glob.glob("data-??.json")) if not want or f[5:7] in want]
    cites = json.load(open("data-metric-sources.json"))
    rk = site_rankings()

    jobs = []
    datas = {}
    for f in files:
        cc = f[5:7]; d = json.load(open(f)); datas[cc] = d
        cn = P.CITE_NAME.get(cc)
        for key, s in d.get("series", {}).items():
            src = ((cites.get(cn) or {}).get(key) or {}).get("source", "") if cn else ""
            jobs.append((cc, key, s, src or s.get("label", ""), d.get("fx_to_usd")))
    print(f"PART A: {len(jobs)} stored series against their cited source ...", flush=True)
    with ThreadPoolExecutor(4) as ex:
        a_rows = list(ex.map(lambda j: P.check(*j), jobs))
    nocode = [(j, r) for j, r in zip(jobs, a_rows) if r["status"] in ("NOCODE", "NOMATCH")]
    print(f"PART C: {len(nocode)} series with no probe code, retried against OECD prices/labour and ECB IRS ...", flush=True)
    with ThreadPoolExecutor(4) as ex:
        c_res = list(ex.map(lambda jr: part_c(jr[0][0], jr[0][1], jr[0][2], jr[0][3]), nocode))
    for (j, r), c in zip(nocode, c_res):
        if c and not (r["status"] == "NOMATCH" and c.get("status") in ("NOMATCH", "ERROR")):
            r.clear(); r.update(c); r["part"] = "C"
    left = [(j, r) for j, r in zip(jobs, a_rows) if r["status"] in ("NOCODE", "NOMATCH", "ERROR")]
    print(f"PART D: {len(left)} series still unchecked, tried against IMF, OECD national accounts, BCRP, C&SD, "
          f"OpenDOSM, Eurostat trade with ECB rates, ECB FM and FRED ...", flush=True)
    with ThreadPoolExecutor(4) as ex:
        d_res = list(ex.map(lambda jr: part_d(jr[0][0], jr[0][1], jr[0][2], jr[0][3], jr[0][4]), left))
    for (j, r), dres in zip(left, d_res):
        if dres and not (r["status"] in ("NOMATCH", "ERROR") and dres.get("status") in ("NOMATCH", "ERROR")):
            r.clear(); r.update(dres); r["part"] = "D"
    print(f"PART B: transformations for {len(datas)} economies ...", flush=True)
    with ThreadPoolExecutor(4) as ex:
        b_rows = [r for rs in ex.map(lambda kv: part_b(kv[0], kv[1], rk), datas.items()) for r in rs]
        b_rows += [r for rs in ex.map(lambda kv: per_person(kv[0], kv[1]), datas.items()) for r in rs]

    cols = ["part", "economy", "check", "series", "status", "source", "code", "transform", "years", "worst_year",
            "worst_gap", "latest_year", "latest_site", "latest_source", "latest_gap", "our_latest", "src_latest", "detail"]
    with open("verify_report.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore"); w.writeheader()
        for r in a_rows: w.writerow({"part": r.get("part", "A"), "check": "stored", "source": r.get("kind", ""), **r})
        for r in b_rows: w.writerow({"part": "B", **r})

    from collections import Counter
    lines = []
    ca, cb = Counter(r["status"] for r in a_rows), Counter(r["status"] for r in b_rows)
    lines.append(f"PART A stored series: {dict(ca)}")
    lines.append(f"PART B transformations: {dict(cb)}")
    moved = []
    if os.path.exists("probe_external_report.csv"):
        before = {(r["economy"], r["series"]): r["status"] for r in csv.DictReader(open("probe_external_report.csv"))}
        moved = [r for r in a_rows if before.get((r["economy"], r["series"])) == "MATCH" and r["status"] != "MATCH"]
        lines.append(f"Matched before, not now: {len(moved)}")
    lines.append("\nSERIOUS / DIFF / NOMATCH / ERROR")
    for r in a_rows:
        if r["status"] in ("DIFF", "NOMATCH", "ERROR", "NEWER"):
            lines.append(f"A {r['status']:8} {r['economy']:3} {r['series']:22} {r.get('code',''):22} {r.get('detail','')}")
    for r in b_rows:
        if r["status"] in ("SERIOUS", "MINOR", "BASIS"):
            lines.append(f"B {r['status']:8} {r['economy']:3} {r['check']:20} {r.get('source',''):34} "
                         f"worst {r.get('worst_year','')} {r.get('worst_gap','')}  latest {r.get('latest_year','')} "
                         f"site {r.get('latest_site','')} src {r.get('latest_source','')} {r.get('detail','')}")
    for r in moved:
        lines.append(f"MOVED {r['economy']} {r['series']} now {r['status']} {r.get('detail','')}")
    hand = [r for r in a_rows if r["status"] in ("NOCODE", "NOMATCH", "ERROR")]
    lines.append(f"\nTO HAND-CHECK ({len(hand)}): " + ", ".join(f"{r['economy']}:{r['series']}" for r in hand))
    open("verify_summary.txt", "w").write("\n".join(lines) + "\n")
    print("\n".join(lines[:3]))
    print(f"{sum(1 for r in b_rows if r['status']=='SERIOUS')} serious transformation results; "
          f"full list in verify_summary.txt, every comparison in verify_report.csv")

if __name__ == "__main__":
    main()
