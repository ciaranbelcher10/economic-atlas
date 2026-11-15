#!/usr/bin/env python3
"""v1.9.138: bring the stored data files in line with the verification fixes now, so the site is right from the
moment the package lands rather than after the next data run. Each value comes from the same fetch functions the
data run uses, so the next run reproduces it.

  Switzerland  gdp_level in CHF (calendar-year sums of SECO's quarters), gdp_real / gdp_growth / gdp_real_annual
               from SECO via the OECD quarterly national accounts (was World Bank US$ and a stale FRED copy)
  Thailand     gdp_level in baht (World Bank NY.GDP.MKTP.CN; the US$ fallback had been kept by the guard)
  Korea        debt_gdp and deficit: the current IMF WEO edition (an older edition's 1995-2024 had been kept)
  Euro area    current_account: EA21 from 1999 (the stored series mixed EA20 and EA21 by year)
  Israel       gdp_level / gdp_real to four decimals of a million shekels (1960s values rounded to 0.6, 0.7 ...)
  India        unemployment labelled as the urban rate it is until the data run fetches the all-India rate

Then run merge_population.py (per person, usd_anchor). Run from the repo root, with network access. Idempotent.
"""
import json
import os
import sys

sys.path.insert(0, os.getcwd())
os.environ.setdefault("OECD_TURN_GROUP", "ALL")

import fetch_ch
import fetch_ez
import fetch_il
import fetch_th
import imf_weo


def load(cc):
    with open(f"data-{cc}.json", encoding="utf-8") as f:
        return json.load(f)


def save(cc, d):
    with open(f"data-{cc}.json", "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, separators=(",", ":"))


def stamp(d):
    return d.get("updated", "")[:16] + "Z" if d.get("updated") else None


def switzerland():
    d = load("ch"); S = d["series"]
    real_q = fetch_ch.fetch_qna_gdp("L")
    nominal = fetch_ch.calendar_year_sums(fetch_ch.fetch_qna_gdp("V"))
    S["gdp_level"] = {"label": "GDP, current prices, calendar year (sum of seasonally adjusted quarters; SECO via OECD quarterly national accounts, T0102)",
                      "unit": "CHFm", "freq": "years", "points": nominal, "confirmed_at": stamp(d)}
    S["gdp_real"] = {"label": "Real GDP, chain-linked volume, seasonally adjusted (SECO via OECD quarterly national accounts, T0102)",
                     "unit": "CHFm", "freq": "quarters", "points": real_q, "confirmed_at": stamp(d)}
    S["gdp_growth"] = {"label": "Real GDP growth, QoQ, seasonally adjusted (derived from SECO real GDP via OECD quarterly national accounts)",
                       "unit": "%", "freq": "quarters", "points": fetch_ch.yoy_from_level(real_q, 1), "confirmed_at": stamp(d)}
    S["gdp_real_annual"] = {"label": "Real GDP, trailing 4-quarter sum (derived from SECO real GDP via OECD quarterly national accounts)",
                            "unit": "CHFm", "freq": "quarters", "confirmed_at": stamp(d),
                            "points": [[real_q[i][0], round(sum(v for _, v in real_q[i - 3:i + 1]), 1)] for i in range(3, len(real_q))]}
    save("ch", d)
    print(f"ch: gdp_level {nominal[0][0]}-{nominal[-1][0]} CHF; gdp_real {real_q[0][0]}-{real_q[-1][0]}")


def thailand():
    d = load("th"); S = d["series"]
    raw = fetch_th.fetch_worldbank("NY.GDP.MKTP.CN")
    pts = [[p, round(v / 1e6, 1)] for p, v in raw]
    S["gdp_level"] = {"label": "GDP, current prices, baht (World Bank, NY.GDP.MKTP.CN, annual)",
                      "unit": "THBm", "freq": "years", "points": pts, "confirmed_at": stamp(d)}
    save("th", d)
    print(f"th: gdp_level {pts[0][0]}-{pts[-1][0]} THB, latest {pts[-1][1]}")


def korea():
    d = load("kr"); S = d["series"]
    for key, ind, label in (("debt_gdp", imf_weo.DEBT, "General government gross debt, % of GDP (IMF WEO)"),
                            ("deficit", imf_weo.DEFICIT, "General government net lending/borrowing, % of GDP (IMF WEO)")):
        pts = imf_weo.fetch("KOR", ind)
        if not pts:
            raise SystemExit(f"kr {key}: IMF WEO unavailable")
        S[key] = {**S.get(key, {}), "label": label, "unit": "%", "freq": "years", "points": pts}
        print(f"kr: {key} {pts[0][0]}-{pts[-1][0]}, {pts[-2]}")
    save("kr", d)


def euro_area():
    d = load("ez"); S = d["series"]
    pts = fetch_ez.fetch_eurostat_current_account()
    if not pts:
        raise SystemExit("ez current_account: Eurostat unavailable")
    S["current_account"] = {**S.get("current_account", {}), "points": pts, "unit": "%", "freq": "years",
                            "label": "Current account balance, % of GDP, euro area (21 members, EA21) vs rest of world (Eurostat bop_gdp6_q)"}
    save("ez", d)
    print(f"ez: current_account {pts[0][0]}-{pts[-1][0]}")


def israel():
    d = load("il"); S = d["series"]
    for key, code in (("gdp_level", "NY.GDP.MKTP.CN"), ("gdp_real", "NY.GDP.MKTP.KN")):
        raw = fetch_il.fetch_worldbank(code)
        if raw and key in S:
            S[key]["points"] = [[p, round(v / 1e6, 4)] for p, v in raw]
    save("il", d)
    print(f"il: gdp_level from {S['gdp_level']['points'][0]}")


def india():
    d = load("in"); S = d["series"]
    if "unemployment" in S:
        S["unemployment"]["label"] = "Unemployment rate, persons 15+, Current Weekly Status, urban areas only (PLFS/MoSPI)"
        save("in", d)
        print("in: unemployment labelled urban")


if __name__ == "__main__":
    for fn in (switzerland, thailand, korea, euro_area, israel, india):
        fn()
