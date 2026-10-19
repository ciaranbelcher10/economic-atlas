#!/usr/bin/env python3
"""READ-ONLY: pull the total, import-total and balance rows for EVERY month of one
Statistics Iceland PxWeb table into a CSV. Nothing in the repo is changed.

  python3 tools/probe_is_trade_full.py <TABLE_PATH> <OUT.csv>
"""
import csv
import itertools
import re
import sys

import requests

BASE = "https://px.hagstofa.is/pxen/api/v1/en"
UA = {"User-Agent": "economic-atlas-probe/1.0 (read-only)"}


def main(path, out):
    r = requests.get(f"{BASE}/{path}", headers=UA, timeout=60)
    r.raise_for_status()
    meta = r.json()
    print(meta.get("title"))
    query = []
    for v in meta["variables"]:
        if v.get("time"):
            vals = v["values"]
            shown = f"{vals[0]} .. {vals[-1]} ({len(vals)} periods)"
        else:
            if len(v["values"]) > 1:
                vals = [c for c, t in zip(v["values"], v["valueTexts"]) if re.search(r"total|balance", t, re.I)]
            else:
                vals = v["values"]
            shown = [t for c, t in zip(v["values"], v["valueTexts"]) if c in vals]
        print(f"  {v['code']}: {shown}")
        query.append({"code": v["code"], "selection": {"filter": "item", "values": vals}})
    cells = 1
    for q in query:
        cells *= max(1, len(q["selection"]["values"]))
    print(f"  cells requested: {cells}")
    if cells > 20000:
        sys.exit("too many cells; stop and send me the lines above")
    r = requests.post(f"{BASE}/{path}", headers=UA, timeout=180,
                      json={"query": query, "response": {"format": "json-stat2"}})
    r.raise_for_status()
    js = r.json()
    ids, sizes = js["id"], js["size"]
    labels = [list(js["dimension"][i]["category"]["label"].values()) for i in ids]
    n = 0
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(ids + ["value"])
        for idx, combo in enumerate(itertools.product(*[range(s) for s in sizes])):
            w.writerow([labels[d][i] for d, i in enumerate(combo)] + [js["value"][idx]])
            n += 1
    print(f"wrote {n} rows to {out}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
