#!/usr/bin/env python3
"""v1.9.138: name the currency in every data file whose own currency shares the $ glyph.

Australia, Brazil, Canada, Mexico and South Africa stored their own currencies as a bare "$m" (and "$" per
person), so "$" meant US dollars on some pages and local dollars, reais or rand on others; every page had to
keep a list of exceptions, and a list missed Thailand. From v1.9.138 "$" means US dollars only, and these five
store AUD, BRL, CAD, MXN and ZAR. The fetch scripts write the same units from the next data run.

Idempotent. Run from the repo root.
"""
import json, os, re

CODE = {"au": "AUD", "br": "BRL", "ca": "CAD", "mx": "MXN", "za": "ZAR"}
KEYS = ("gdp_level", "gdp_real", "gdp_real_annual", "gdp_level_annual", "trade_balance", "exports", "imports",
        "gdp_per_capita")

def main():
    for cc, code in CODE.items():
        p = f"data-{cc}.json"
        raw = open(p).read()
        d = json.loads(raw)
        n = 0
        for k in KEYS:
            s = d.get("series", {}).get(k)
            if not s or not str(s.get("unit", "")).startswith("$"):
                continue
            s["unit"] = code + str(s["unit"])[1:]
            if k in ("trade_balance", "exports", "imports"):
                s["label"] = s.get("label", "").replace(", $ ", " ").replace(", $", "")
            n += 1
        if n:
            indent = 2 if raw.lstrip().startswith("{\n") or "\n  \"" in raw[:200] else None
            with open(p, "w") as f:
                json.dump(d, f, indent=indent)
        print(f"{p}: {n} series relabelled")

if __name__ == "__main__":
    main()
