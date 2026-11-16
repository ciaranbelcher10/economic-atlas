#!/usr/bin/env python3
"""v1.9.139: put the IMF monthly goods trade (imf_trade.py) into the stored data files for Brazil, Canada, Denmark,
South Korea and Mexico now, converted exactly as their fetch scripts will convert it on the next data run (each
script's own _fx_rate_for_period over the stored monthly-average exchange-rate history). Replaces the OECD quarterly
trade balance on FRED, which did not match national customs figures. Also Morocco, Indonesia, Pakistan and Peru
unemployment: the national rate from the IMF World Economic Outlook (LUR) in place of the ILO modelled estimate.
Poland's trade in zloty at the ECB's monthly rates (was euros). Run from the repo root, with network access.
Idempotent.
"""
import importlib
import json
import os
import sys

sys.path.insert(0, os.getcwd())
import imf_trade
import imf_weo

ECON = {"br": ("BRA", "BRL"), "ca": ("CAN", "CAD"), "dk": ("DNK", "DKK"), "kr": ("KOR", "₩"), "mx": ("MEX", "MXN")}
SUFFIX = ("not seasonally adjusted)", "not seasonally adjusted, converted from US$ at each month's average rate)")


def main():
    for cc, (iso, unit_code) in ECON.items():
        mod = importlib.import_module(f"fetch_{cc}")
        path = f"data-{cc}.json"
        d = json.load(open(path, encoding="utf-8"))
        fx = d["fx_to_usd"]
        hist = fx["history"]
        conv = lambda v, p: v * mod._fx_rate_for_period(hist, p, fx["rate"])
        if fx.get("direction") != "divide":
            raise SystemExit(f"{cc}: expected a local-per-US$ rate (divide)")
        for key, pts in imf_trade.series(iso).items():
            d["series"][key] = {
                "label": imf_trade.LABEL[key].replace(*SUFFIX),
                "unit": f"{unit_code}m", "freq": "months",
                "points": [[p, round(conv(v, p), 1)] for p, v in pts],
                "confirmed_at": d.get("updated", "")[:16] + "Z" if d.get("updated") else None,
            }
        json.dump(d, open(path, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
        tb = d["series"]["trade_balance"]["points"]
        print(f"{cc}: trade {tb[0][0]} to {tb[-1][0]}, latest {tb[-1][1]} {unit_code}m")


def unemployment():
    lab = "Unemployment rate, national definition, annual, actual years (IMF World Economic Outlook, LUR)"
    for cc, iso in (("ma", "MAR"), ("id", "IDN"), ("pk", "PAK"), ("pe", "PER")):
        path = f"data-{cc}.json"
        d = json.load(open(path, encoding="utf-8"))
        pts = imf_weo.fetch(iso, "LUR")
        if not pts:
            raise SystemExit(f"{cc}: IMF WEO LUR unavailable")
        d["series"]["unemployment"] = {**d["series"].get("unemployment", {}), "label": lab, "unit": "%",
                                       "freq": "years", "points": pts}
        json.dump(d, open(path, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
        print(f"{cc}: unemployment {pts[0][0]} to {pts[-1][0]}, latest {pts[-1][1]}")


def poland():
    import ecb_exr
    import fetch_pl
    path = "data-pl.json"
    d = json.load(open(path, encoding="utf-8"))
    exp, imp = fetch_pl.fetch_eurostat_trade_world_pl("EXP"), fetch_pl.fetch_eurostat_trade_world_pl("IMP")
    rates = ecb_exr.fetch_monthly("PLN")
    if not (exp and imp and rates):
        raise SystemExit("pl: Eurostat or ECB unavailable")
    ex, im = ecb_exr.to_national(exp, rates), ecb_exr.to_national(imp, rates)
    im_by = dict(im)
    bal = [[p, round(v - im_by[p], 1)] for p, v in ex if p in im_by]
    note = "Eurostat, world partner, converted from euro at each month's ECB reference rate"
    S = d["series"]
    S["exports"] = {"label": f"Exports, goods ({note})", "unit": "PLNm", "freq": "months", "points": ex}
    S["imports"] = {"label": f"Imports, goods ({note})", "unit": "PLNm", "freq": "months", "points": im}
    S["trade_balance"] = {"label": f"Trade balance, goods ({note}, exports less imports)", "unit": "PLNm",
                          "freq": "months", "points": bal}
    json.dump(d, open(path, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(f"pl: trade {bal[0][0]} to {bal[-1][0]}, latest {bal[-1][1]} PLNm")


if __name__ == "__main__":
    main()
    unemployment()
    poland()
