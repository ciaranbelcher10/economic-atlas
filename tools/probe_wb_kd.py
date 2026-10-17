"""Probe (v1.8.4): World Bank NY.GDP.MKTP.KD (GDP, constant 2015 US$)
coverage for every economy on the site, before deciding whether Real +
Dollarise should use it instead of converting local real GDP at one rate.

Read-only: fetches from api.worldbank.org, reads data-*.json, writes nothing.
Run from the repo root:  python3 tools/probe_wb_kd.py

For each economy it prints the KD span and latest year, the latest year of
our own gdp_real, and the largest gap (percentage points) between KD's
annual growth and the growth of our real series summed to calendar years,
over the years both have. A large gap means KD and our series are not
measuring the same thing (rebasing, a different national-accounts vintage).
"""
import json
import sys
import time

import requests

KD = "https://api.worldbank.org/v2/country/{iso}/indicator/NY.GDP.MKTP.KD?format=json&per_page=200"

ECONOMIES = [
    ('UK', 'GBR', 'data-uk.json'),
    ('US', 'USA', 'data-us.json'),
    ('Eurozone', 'EMU', 'data-ez.json'),
    ('Japan', 'JPN', 'data-jp.json'),
    ('India', 'IND', 'data-in.json'),
    ('Canada', 'CAN', 'data-ca.json'),
    ('Australia', 'AUS', 'data-au.json'),
    ('South Korea', 'KOR', 'data-kr.json'),
    ('Israel', 'ISR', 'data-il.json'),
    ('Mexico', 'MEX', 'data-mx.json'),
    ('Brazil', 'BRA', 'data-br.json'),
    ('South Africa', 'ZAF', 'data-za.json'),
    ('Morocco', 'MAR', 'data-ma.json'),
    ('Germany', 'DEU', 'data-de.json'),
    ('France', 'FRA', 'data-fr.json'),
    ('Italy', 'ITA', 'data-it.json'),
    ('Spain', 'ESP', 'data-es.json'),
    ('Netherlands', 'NLD', 'data-nl.json'),
    ('Denmark', 'DNK', 'data-dk.json'),
    ('Ireland', 'IRL', 'data-ie.json'),
    ('Norway', 'NOR', 'data-no.json'),
    ('Chile', 'CHL', 'data-cl.json'),
    ('Colombia', 'COL', 'data-co.json'),
    ('Turkey', 'TUR', 'data-tr.json'),
    ('Indonesia', 'IDN', 'data-id.json'),
    ('Poland', 'POL', 'data-pl.json'),
    ('Switzerland', 'CHE', 'data-ch.json'),
    ('Argentina', 'ARG', 'data-ar.json'),
    ('Sweden', 'SWE', 'data-se.json'),
    ('Singapore', 'SGP', 'data-sg.json'),
    ('Austria', 'AUT', 'data-at.json'),
    ('Thailand', 'THA', 'data-th.json'),
    ('China', 'CHN', 'data-cn.json'),
    ('Malaysia', 'MYS', 'data-my.json'),
    ('New Zealand', 'NZL', 'data-nz.json'),
    ('Belgium', 'BEL', 'data-be.json'),
    ('Portugal', 'PRT', 'data-pt.json'),
    ('Finland', 'FIN', 'data-fi.json'),
    ('Greece', 'GRC', 'data-gr.json'),
    ('Czechia', 'CZE', 'data-cz.json'),
    ('Hungary', 'HUN', 'data-hu.json'),
    ('Romania', 'ROU', 'data-ro.json'),
    ('Saudi Arabia', 'SAU', 'data-sa.json'),
    ('Slovakia', 'SVK', 'data-sk.json'),
    ('Croatia', 'HRV', 'data-hr.json'),
    ('Bulgaria', 'BGR', 'data-bg.json'),
    ('Lithuania', 'LTU', 'data-lt.json'),
    ('Estonia', 'EST', 'data-ee.json'),
    ('Latvia', 'LVA', 'data-lv.json'),
    ('Slovenia', 'SVN', 'data-si.json'),
    ('Luxembourg', 'LUX', 'data-lu.json'),
    ('Cyprus', 'CYP', 'data-cy.json'),
    ('Malta', 'MLT', 'data-mt.json'),
    ('Philippines', 'PHL', 'data-ph.json'),
    ('Taiwan', 'TWN', 'data-tw.json'),
    ('Vietnam', 'VNM', 'data-vn.json'),
    ('Nigeria', 'NGA', 'data-ng.json'),
    ('Egypt', 'EGY', 'data-eg.json'),
    ('Peru', 'PER', 'data-pe.json'),
    ('Hong Kong', 'HKG', 'data-hk.json'),
    ('Iceland', 'ISL', 'data-is.json'),
    ('Pakistan', 'PAK', 'data-pk.json'),
]


def kd(iso):
    for attempt in range(3):
        try:
            r = requests.get(KD.format(iso=iso), timeout=60)
            r.raise_for_status()
            body = r.json()
            if len(body) < 2 or not body[1]:
                return {}
            return {int(x["date"]): x["value"] for x in body[1] if x.get("value") is not None}
        except Exception as exc:
            if attempt == 2:
                raise
            time.sleep(5 * (attempt + 1))


def ours_annual(path):
    try:
        d = json.load(open(path))
    except FileNotFoundError:
        return {}, None
    s = d.get("series", {})
    real = s.get("gdp_real_annual") or s.get("gdp_real")
    if not real:
        return {}, None
    by = {}
    for p, v in real["points"]:
        by.setdefault(int(str(p)[:4]), []).append(v)
    freq = real.get("freq")
    need = {"quarters": 4, "months": 12}.get(freq, 1)
    return {y: sum(v) for y, v in by.items() if len(v) == need}, real.get("unit")


def growth(series):
    ys = sorted(series)
    return {y: (series[y] / series[y - 1] - 1) * 100 for y in ys if y - 1 in series and series[y - 1]}


def main():
    print(f"{'economy':<14} {'iso':<4} {'KD span':<11} {'n':>3}  {'ours to':>7}  {'growth gap (pp)':>15}  note")
    missing, behind, gaps = [], [], []
    for name, iso, path in ECONOMIES:
        try:
            k = kd(iso)
        except Exception as exc:
            print(f"{name:<14} {iso:<4} ERROR {exc}")
            missing.append(name)
            continue
        ours, unit = ours_annual(path)
        ol = max(ours) if ours else None
        if not k:
            print(f"{name:<14} {iso:<4} {'none':<11} {0:>3}  {str(ol):>7}")
            missing.append(name)
            continue
        gk, go = growth(k), growth(ours)
        common = sorted(set(gk) & set(go))
        worst = max(((abs(gk[y] - go[y]), y) for y in common), default=None)
        note = []
        if ol and max(k) < ol:
            note.append(f"KD ends {ol - max(k)}y before ours")
            behind.append(name)
        if worst and worst[0] > 1.0:
            note.append(f"worst {worst[1]}")
            gaps.append(name)
        w = f"{worst[0]:.2f} ({len(common)}y)" if worst else "no overlap"
        print(f"{name:<14} {iso:<4} {min(k)}-{max(k):<6} {len(k):>3}  {str(ol):>7}  {w:>15}  {'; '.join(note)}")
        time.sleep(0.3)

    print()
    print(f"no KD series ({len(missing)}): {', '.join(missing) or 'none'}")
    print(f"KD ends before our real series ({len(behind)}): {', '.join(behind) or 'none'}")
    print(f"growth gap over 1pp in some year ({len(gaps)}): {', '.join(gaps) or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
