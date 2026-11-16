#!/usr/bin/env python3
"""v2.0: euro-area goods trade with full history. Replaces the twelve-month Eurostat teiet010/teiet110 series in
data-ez.json with Eurostat ext_st_easitc (EA21, partner EXT_EA21, seasonally and calendar adjusted, EUR million,
monthly from 2002-01), exactly as fetch_ez.py now fetches it. The recent months are identical in both tables.
Run from the repo root, with network access. Idempotent.
"""
import json
import os
import sys

sys.path.insert(0, os.getcwd())
import fetch_ez


def main():
    exp, imp = fetch_ez._fetch_eurostat_easitc("EXP"), fetch_ez._fetch_eurostat_easitc("IMP")
    if not exp or not imp:
        raise SystemExit("ext_st_easitc unavailable; nothing changed")
    path = "data-ez.json"
    d = json.load(open(path, encoding="utf-8"))
    s = d["series"]
    old = {k: dict(s[k]["points"]) for k in ("exports", "imports") if k in s}
    for k, pts in (("exports", exp), ("imports", imp)):
        for p, v in pts:
            if p in old.get(k, {}) and abs(old[k][p] - v) > 0.05:
                raise SystemExit(f"{k} {p}: stored {old[k][p]} differs from ext_st_easitc {v}; check before replacing")
    imp_by = dict(imp)
    tb = [[p, round(v - imp_by[p], 1)] for p, v in exp if p in imp_by]
    lab = fetch_ez.EASITC_LABELS
    for k, pts in (("exports", exp), ("imports", imp), ("trade_balance", tb)):
        s[k] = {**{a: b for a, b in s.get(k, {}).items() if a != "points"},
                "label": lab[k], "unit": "€m", "freq": "months", "points": pts}
    with open(path, "w") as f:
        json.dump(d, f)  # same format as fetch_ez.py writes
    print(f"ez: trade {tb[0][0]} to {tb[-1][0]}, {len(tb)} months, latest {tb[-1][1]} €m")


if __name__ == "__main__":
    main()
