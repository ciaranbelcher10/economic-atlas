#!/usr/bin/env python3
"""READ-ONLY probe: Statistics Iceland (PxWeb) monthly goods trade vs data-is.json.

Why: the Iceland fetcher drops IMF ITG months where imports equal exports
exactly (drop_mirrored): 2013-03, 2013-04 and 2026-01. Those months are blank
on the charts. The issuing office may hold real figures for them, and may also
start well before our 2006-01.

Nothing is written to the repo. Run it from the repo root on a machine with
network access (the build container's allowlist blocks px.hagstofa.is).

Step 1  discover candidate tables (walks the PxWeb tree, prints trade tables):
    python3 tools/probe_is_trade.py discover

Step 2  show one table's variables so the right selections can be made:
    python3 tools/probe_is_trade.py meta <TABLE_PATH>

Step 3  fetch the months of interest and compare with data-is.json:
    python3 tools/probe_is_trade.py fetch <TABLE_PATH> \
        --select "Flokkun=Total" --months 2013-02 2013-03 2013-04 2013-05 2025-12 2026-01 2026-02
    (repeat --select VAR=VALUE for each non-time variable until the query is small;
     VALUE may be a code or a label)

Report back: the table path, the earliest month in the table, and the output of step 3.
Compare levels in ISK million against data-is.json (stored at the BIS monthly
average rate from US$, so expect a gap; the check is that 2013-03/04 and 2026-01
have real, unequal exports and imports at source, and what history depth exists).
"""
import argparse
import itertools
import json
import re
import sys

import requests

BASE = "https://px.hagstofa.is/pxen/api/v1/en"
UA = {"User-Agent": "economic-atlas-probe/1.0 (read-only)"}
KEYWORDS = re.compile(r"trade|export|import", re.I)


def get(path):
    r = requests.get(f"{BASE}/{path}".rstrip("/"), headers=UA, timeout=60)
    r.raise_for_status()
    return r.json()


def discover(path="", depth=0, maxdepth=4):
    try:
        nodes = get(path)
    except Exception as e:  # keep walking if one branch fails
        print(f"{'  ' * depth}[error {path}: {e}]")
        return
    for n in nodes:
        full = f"{path}/{n['id']}".lstrip("/")
        text = n.get("text", "")
        if n.get("type") == "t":
            if KEYWORDS.search(text) or KEYWORDS.search(n["id"]):
                print(f"TABLE {full}\n      {text}")
        elif depth < maxdepth and (depth < 1 or KEYWORDS.search(text) or KEYWORDS.search(n["id"])
                                   or re.search(r"econom|efnahag|utanr", full, re.I)):
            discover(full, depth + 1, maxdepth)


def meta(path):
    m = get(path)
    print(m.get("title"))
    for v in m["variables"]:
        vals = list(zip(v["values"], v["valueTexts"]))
        print(f"\nVARIABLE {v['code']} ({v['text']}), {len(vals)} values"
              f"{'  [TIME]' if v.get('time') else ''}")
        for code, text in vals[:8]:
            print(f"   {code!r:14} {text}")
        if len(vals) > 8:
            print(f"   ... last: {vals[-1][0]!r} {vals[-1][1]}")


def month_codes(var, months):
    """Map 'YYYY-MM' to this table's time codes (PxWeb uses 'YYYYMmm' or 'YYYYMM')."""
    have = set(var["values"])
    out = []
    for ym in months:
        y, mm = ym.split("-")
        for cand in (f"{y}M{mm}", f"{y}{mm}", f"{y}-{mm}"):
            if cand in have:
                out.append(cand)
                break
        else:
            print(f"  [no time code for {ym} in this table]")
    return out


def fetch(path, selects, months):
    m = get(path)
    query = []
    sel = {}
    for s in selects:
        k, v = s.split("=", 1)
        sel.setdefault(k, []).append(v)
    for var in m["variables"]:
        if var.get("time"):
            vals = month_codes(var, months)
        elif var["code"] in sel:
            want = sel[var["code"]]
            vals = [c for c, t in zip(var["values"], var["valueTexts"]) if c in want or t in want]
        else:
            vals = var["values"]
        query.append({"code": var["code"], "selection": {"filter": "item", "values": vals}})
    cells = 1
    for q in query:
        cells *= max(1, len(q["selection"]["values"]))
    print(f"query would return {cells} cells")
    if cells > 5000:
        sys.exit("too many cells; add more --select VAR=VALUE filters")
    r = requests.post(f"{BASE}/{path}", headers=UA, timeout=120,
                      json={"query": query, "response": {"format": "json-stat2"}})
    r.raise_for_status()
    js = r.json()
    dims, ids, sizes = js["dimension"], js["id"], js["size"]
    labels = [list(dims[i]["category"]["label"].values()) for i in ids]
    stored = json.load(open("data-is.json", encoding="utf-8"))["series"]
    exp = dict(map(tuple, stored["exports"]["points"]))
    imp = dict(map(tuple, stored["imports"]["points"]))
    idx = 0
    for combo in itertools.product(*[range(n) for n in sizes]):
        val = js["value"][idx]
        idx += 1
        desc = " | ".join(labels[d][i] for d, i in enumerate(combo))
        print(f"{desc:80} {val}")
    print("\nStored in data-is.json (ISK million at BIS monthly average, from IMF US$):")
    for ym in months:
        print(f"  {ym}: exports={exp.get(ym)} imports={imp.get(ym)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["discover", "meta", "fetch"])
    ap.add_argument("table", nargs="?")
    ap.add_argument("--select", action="append", default=[])
    ap.add_argument("--months", nargs="*", default=["2013-02", "2013-03", "2013-04", "2013-05",
                                                      "2025-12", "2026-01", "2026-02"])
    a = ap.parse_args()
    if a.cmd == "discover":
        discover()
    elif not a.table:
        sys.exit("table path required")
    elif a.cmd == "meta":
        meta(a.table)
    else:
        fetch(a.table, a.select, a.months)


if __name__ == "__main__":
    main()
