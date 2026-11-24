"""PPP conversion factors for the PPP switch (v2.0.16). Pure functions, no network, so tests run offline.

Source: World Bank, "PPP conversion factor, GDP (LCU per international $)" (PA.NUS.PPP), annual.
A value in local currency divided by that year's factor is in international dollars (current PPP).

Check against an outside source (the site's rule that every figure is checked): for each economy the
latest complete calendar year of OUR GDP, divided by that year's factor, must match the World Bank's own
GDP at PPP (NY.GDP.MKTP.PP.CD) within CHECK_TOLERANCE. If it does not (our GDP is in another currency or
unit than the World Bank's local currency, or a source differs), PPP is not offered for that economy and
the reason is recorded. No wrong figure is ever shown: a missing one is.

fetch_population.py fetches (daily) and calls build_doc(); merge_population.py calls apply_checks()
every run, after the fetch scripts have refreshed each economy's GDP. The document lives under the "ppp"
key of data-population.json (load_doc / save_doc), so no workflow change is needed to keep it.
"""
import datetime as dt
import re

FACTOR = "PA.NUS.PPP"
GDP_PPP = "NY.GDP.MKTP.PP.CD"
SOURCE = "World Bank, PPP conversion factor, GDP (LCU per international $) (PA.NUS.PPP), annual"
OUT = "data-population.json"   # kept under its "ppp" key: the workflow already commits this file
KEY = "ppp"
MIN_ECONOMIES = 50          # about 60 expected; allow a few to be temporarily absent
MAX_LAG_YEARS = 4           # newest factor anywhere must be at most this many years old
CHECK_TOLERANCE = 0.06      # our GDP / factor within 6% of the World Bank's GDP at PPP (latest year)
YEAR_TOLERANCE = 0.10       # every earlier year shown must also be within 10% (catches currency changes,
                            # e.g. Bulgaria's 1999 redenomination, and old GDP vintages); earlier years are not shown
ANNUAL_RATE = {"US", "Japan"}   # quarters published at an annual rate: a year is their mean


def parse_wb(payload, code_to_name):
    """World Bank JSON -> {site name: [[year, value], ...]} (sorted, positive floats only)."""
    if not isinstance(payload, list) or len(payload) < 2 or not isinstance(payload[1], list):
        raise ValueError("World Bank: unexpected response shape")
    out = {}
    for row in payload[1]:
        code = (row.get("country") or {}).get("id") or row.get("countryiso3code")
        name = code_to_name.get(code)
        if name is None or row.get("value") is None:
            continue
        year = str(row.get("date"))
        try:
            v = float(row["value"])
        except (TypeError, ValueError):
            continue
        if year.isdigit() and v > 0:
            out.setdefault(name, []).append([year, v])
    return {k: sorted(v) for k, v in out.items()}


def keep_best(new, prev):
    """Per economy, the new points unless they came back empty, shorter or older; then the previous."""
    out, kept = {}, []
    for name in sorted(set(new) | set(prev)):
        n, p = new.get(name), prev.get(name)
        if n and (not p or (len(n) >= len(p) and n[-1][0] >= p[-1][0])):
            out[name] = n
        elif p:
            out[name] = p
            kept.append(name)
    return out, kept


def build_doc(factor_payload, gdp_payload, prev_doc, code_to_name, today=None):
    """The data-ppp.json document to write, or raise if it must not be written."""
    today = today or dt.date.today()
    fac_new = parse_wb(factor_payload, code_to_name)
    gdp_new = parse_wb(gdp_payload, code_to_name) if gdp_payload is not None else {}
    prev = (prev_doc or {}).get("countries", {})
    fac, kept = keep_best(fac_new, {k: v.get("points", []) for k, v in prev.items()})
    gdp, _ = keep_best(gdp_new, {k: v.get("gdp_ppp", []) for k, v in prev.items()})
    if len(fac_new) < MIN_ECONOMIES:
        raise ValueError(f"only {len(fac_new)} economies came back (need {MIN_ECONOMIES}); not writing")
    newest = max(int(p[-1][0]) for p in fac.values())
    if newest < today.year - MAX_LAG_YEARS:
        raise ValueError(f"newest PPP year is {newest}; too old, not writing")
    name_to_code = {v: k for k, v in code_to_name.items()}
    countries = {}
    for n in sorted(fac):
        c = {"wb_code": name_to_code.get(n), "points": [[y, round(v, 6)] for y, v in fac[n]],
             "gdp_ppp": [[y, round(v)] for y, v in gdp.get(n, [])]}
        old = prev.get(n) or {}
        for k in ("ok", "check", "reason"):           # the last check stands until apply_checks reruns it
            if k in old:
                c[k] = old[k]
        countries[n] = c
    return {
        "updated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": SOURCE, "unit": "LCU per international $", "freq": "years",
        "countries": countries,
        "missing": {n: "No World Bank PPP conversion factor came back for this economy."
                    for n in sorted(code_to_name.values()) if n not in countries},
        "kept_previous": kept,
    }


def scale_of(unit):
    m = re.search(r"(tn|bn|m|k)$", re.sub(r"\s*\(.*\)\s*$", "", str(unit or "")).strip())
    return {"tn": 1e12, "bn": 1e9, "m": 1e6, "k": 1e3}[m.group(1)] if m else 1


def calendar_years(gdp, country):
    """{year: GDP in whole currency units} for complete calendar years only (never a part year)."""
    if not gdp or "%" in str(gdp.get("unit", "")):
        return {}
    pts = [(str(p), float(v)) for p, v in gdp.get("points", []) if v is not None]
    sc, out = scale_of(gdp.get("unit")), {}
    if gdp.get("freq") == "years":
        return {p: v * sc for p, v in pts if re.fullmatch(r"\d{4}", p)}
    by = {}
    for p, v in pts:
        m = re.fullmatch(r"(\d{4})-Q([1-4])", p)
        if m:
            by.setdefault(m.group(1), []).append(v)
    for y, qs in by.items():
        if len(qs) == 4:
            out[y] = (sum(qs) / 4 if country in ANNUAL_RATE else sum(qs)) * sc
    return out


def check_one(name, entry, gdp_series):
    """(ok, check, reason) for one economy: our GDP / factor against the World Bank's GDP at PPP,
    in the latest year all three exist (within CHECK_TOLERANCE), and back year by year while each is
    within YEAR_TOLERANCE. check["from"] is the first year shown: PPP is never shown before it."""
    fac = {y: v for y, v in entry.get("points", [])}
    wb = {y: v for y, v in entry.get("gdp_ppp", [])}
    ours = calendar_years(gdp_series, name)
    years = sorted(y for y in ours if y in fac and y in wb)
    if not years:
        return False, None, "No year with our GDP, the PPP factor and the World Bank's GDP at PPP to check against."
    y = years[-1]
    mine = ours[y] / fac[y]
    diff = mine / wb[y] - 1
    first = y
    for yy in reversed(years[:-1]):
        if abs(ours[yy] / fac[yy] / wb[yy] - 1) > YEAR_TOLERANCE:
            break
        first = yy
    check = {"year": y, "ours": round(mine), "world_bank": round(wb[y]), "diff_pct": round(100 * diff, 2), "from": first}
    if abs(diff) > CHECK_TOLERANCE:
        return False, check, (f"Our {y} GDP at PPP differs from the World Bank's by {100 * diff:+.1f}% "
                              f"(limit {100 * CHECK_TOLERANCE:.0f}%), so PPP is not offered.")
    return True, check, None


def apply_checks(doc, gdp_by_country):
    """Rerun the check for every economy against its current GDP. Returns the number changed."""
    changed = 0
    for name, entry in (doc.get("countries") or {}).items():
        ok, check, reason = check_one(name, entry, gdp_by_country.get(name))
        new = {"ok": ok, "check": check, "reason": reason}
        if any(entry.get(k) != v for k, v in new.items()):
            changed += 1
            entry["ok"], entry["check"] = ok, check
            if reason:
                entry["reason"] = reason
            else:
                entry.pop("reason", None)
    return changed


def load_doc(path=OUT):
    """The PPP document from data-population.json, or {} when there is none yet."""
    import json, os
    if not os.path.exists(path):
        return {}
    try:
        return (json.load(open(path, encoding="utf-8")) or {}).get(KEY) or {}
    except ValueError:
        return {}


def save_doc(doc, path=OUT):
    """Write the PPP document into data-population.json, leaving the population figures as they are."""
    import json, os
    whole = {}
    if os.path.exists(path):
        try:
            whole = json.load(open(path, encoding="utf-8")) or {}
        except ValueError:
            whole = {}
    whole[KEY] = doc
    with open(path, "w", encoding="utf-8") as f:
        json.dump(whole, f, ensure_ascii=False, separators=(",", ":"))
