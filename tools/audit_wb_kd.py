"""Audit (v1.8.5): our real GDP growth against the World Bank's NY.GDP.MKTP.KD.

Governance rule (methodology page): the site's real-dollar GDP is our own
national real series converted at one rate, so its growth equals the
statistics office's. KD is a published, independent estimate used only as
a check. A recent year where the two disagree by more than THRESHOLD_PP is a
finding to investigate: usually a revision KD has not caught up with, but
possibly a broken or mis-chained series on our side.

Read-only. Run from the repo root:  python3 tools/audit_wb_kd.py
Exit 1 if any finding is not in REVIEWED (so it can gate a release).

Older years are ignored: the 17 Oct 2026 probe found long-past gaps (Turkey
7.3pp in 2002) that reflect base-year and vintage differences, not errors.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import probe_wb_kd as P  # noqa: E402

THRESHOLD_PP = 2.0
RECENT_YEARS = 4          # the last four years both series have

# Findings already investigated, with the reason, as (economy, year): reason.
# Add an entry only after checking the national release; never to silence.
REVIEWED: dict = {
    ("Ireland", 2025): "CSO Annual National Accounts 2025 (2 Jul 2026): GDP +8.0%, matching ours (+7.97%). "
                       "KD's +12.3% is the earlier quarterly-accounts estimate the CSO has since revised.",
}

# EU members: Eurostat's own annual real growth (nama_10_gdp, chain-linked
# volumes, % change on the previous year) is the national figure as the
# statistics office last reported it. Where ours agrees with it within
# EUROSTAT_TOL_PP, the gap is KD's vintage, not our series, and is shown
# as "vintage" without failing. Where ours disagrees with Eurostat too, our
# series is suspect: that stays a FINDING.
EUROSTAT_TOL_PP = 0.5
EU2 = {"AUT": "AT", "BEL": "BE", "BGR": "BG", "HRV": "HR", "CYP": "CY", "CZE": "CZ", "DNK": "DK",
       "EST": "EE", "FIN": "FI", "FRA": "FR", "DEU": "DE", "GRC": "EL", "HUN": "HU", "IRL": "IE",
       "ITA": "IT", "LVA": "LV", "LTU": "LT", "LUX": "LU", "MLT": "MT", "NLD": "NL", "POL": "PL",
       "PRT": "PT", "ROU": "RO", "SVK": "SK", "SVN": "SI", "ESP": "ES", "SWE": "SE"}
EUROSTAT = ("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/nama_10_gdp"
            "?geo={geo}&unit=CLV_PCH_PRE&na_item=B1GQ&format=JSON&lang=EN")


def eurostat_growth(iso3):
    """{year: % real growth} from Eurostat, or {} if not an EU member or unreachable."""
    geo = EU2.get(iso3)
    if not geo:
        return {}
    try:
        r = P.requests.get(EUROSTAT.format(geo=geo), timeout=60)
        r.raise_for_status()
        j = r.json()
        idx = j["dimension"]["time"]["category"]["index"]
        return {int(t): j["value"][str(i)] for t, i in idx.items() if str(i) in j["value"]}
    except Exception as exc:
        print(f"  (Eurostat check unavailable for {iso3}: {exc})")
        return {}


def main():
    findings, checked, no_kd = [], 0, []
    for name, iso, path in P.ECONOMIES:
        try:
            k = P.kd(iso)
        except Exception as exc:
            print(f"ERROR {name}: {exc}")
            findings.append((name, None, None))
            continue
        if not k:
            no_kd.append(name)
            continue
        ours, _ = P.ours_annual(path)
        gk, go = P.growth(k), P.growth(ours)
        common = sorted(set(gk) & set(go))[-RECENT_YEARS:]
        checked += 1
        es = None
        for y in common:
            gap = go[y] - gk[y]
            if abs(gap) > THRESHOLD_PP:
                why = REVIEWED.get((name, y))
                tag = "reviewed" if why else "FINDING"
                if not why:
                    if es is None:
                        es = eurostat_growth(iso)
                    if y in es and abs(go[y] - es[y]) <= EUROSTAT_TOL_PP:
                        tag, why = "vintage", f"Eurostat nama_10_gdp {es[y]:+.1f}% agrees with ours; KD is the older vintage"
                    elif y in es:
                        why = f"Eurostat nama_10_gdp {es[y]:+.1f}% disagrees with ours too: check our series"
                print(f"{tag:<8} {name:<14} {y}  ours {go[y]:+.2f}%  KD {gk[y]:+.2f}%  gap {gap:+.2f}pp"
                      + (f"  ({why})" if why else ""))
                if tag == "FINDING":
                    findings.append((name, y, gap))
        time.sleep(0.3)
    print(f"\nKD audit: {checked} economies checked over their last {RECENT_YEARS} common years, "
          f"threshold {THRESHOLD_PP}pp; no KD series: {', '.join(no_kd) or 'none'}")
    print(f"open findings: {len(findings)}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
