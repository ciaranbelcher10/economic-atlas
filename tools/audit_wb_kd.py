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
REVIEWED: dict = {}


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
        for y in common:
            gap = go[y] - gk[y]
            if abs(gap) > THRESHOLD_PP:
                tag = "reviewed" if (name, y) in REVIEWED else "FINDING"
                print(f"{tag:<8} {name:<14} {y}  ours {go[y]:+.2f}%  KD {gk[y]:+.2f}%  gap {gap:+.2f}pp"
                      + (f"  ({REVIEWED[(name, y)]})" if tag == "reviewed" else ""))
                if tag == "FINDING":
                    findings.append((name, y, gap))
        time.sleep(0.3)
    print(f"\nKD audit: {checked} economies checked over their last {RECENT_YEARS} common years, "
          f"threshold {THRESHOLD_PP}pp; no KD series: {', '.join(no_kd) or 'none'}")
    print(f"open findings: {len(findings)}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
