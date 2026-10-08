"""Probe official release-calendar pages for China, Malaysia and New Zealand.

    python3 tools/probe_calendar.py            # saves pages to ~/probe_cal/, prints a report
    cd ~ && zip -qr probe_cal.zip probe_cal    # upload probe_cal.zip to Claude

Read-only: writes nothing inside the repo. Each candidate is an official
publisher URL; the report shows status, size, whether expected text is
present, and every link on the page that looks like a calendar or schedule,
so a moved page can still be found. Parsers are written against these saved
copies, never against guesses.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import urljoin

import requests

OUT = Path.home() / "probe_cal"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
      "Accept-Language": "en"}

# name, url, markers expected on the right page
CANDIDATES = [
    ("rbnz_decisions", "https://www.rbnz.govt.nz/monetary-policy/monetary-policy-decisions", ["Monetary Policy", "2026"]),
    ("rbnz_dates_news", "https://www.rbnz.govt.nz/hub/news/2025/10/monetary-policy-and-financial-stability-report-dates-august-2026-to-february-2027", ["28 October 2026", "9 December 2026"]),
    ("rbnz_upcoming", "https://www.rbnz.govt.nz/monetary-policy/about-monetary-policy/monetary-policy-announcement-dates", ["2026"]),
    ("statsnz_calendar", "https://www.stats.govt.nz/release-calendar/", ["Consumers price index", "Gross domestic product"]),
    ("statsnz_calendar_alt", "https://www.stats.govt.nz/release-calendar", ["Consumers price index"]),
    ("statsnz_upcoming", "https://www.stats.govt.nz/news-and-latest-releases/upcoming-releases/", ["release"]),
    ("bnm_mps_nov2025", "https://www.bnm.gov.my/-/monetary-policy-statement-06112025", ["Schedule of Monetary Policy", "2026"]),
    ("bnm_mpc_page", "https://www.bnm.gov.my/monetary-policy-committee", ["Monetary Policy Committee"]),
    ("bnm_mps_list", "https://www.bnm.gov.my/monetary-stability/monetary-policy-statements", ["Monetary Policy Statement"]),
    ("dosm_calendar", "https://www.dosm.gov.my/portal-main/release-calendar", ["Consumer Price Index", "2026"]),
    ("dosm_arc", "https://www.dosm.gov.my/portal-main/advance-release-calendar", ["2026"]),
    ("opendosm_calendar", "https://open.dosm.gov.my/publications/upcoming", ["2026"]),
    ("nbs_calendar_index", "https://www.stats.gov.cn/english/PressRelease/ReleaseCalendar/", ["Regular Press Release Calendar"]),
    ("nbs_calendar_2026", "https://www.stats.gov.cn/english/PressRelease/ReleaseCalendar/202512/t20251226_1962154.html", ["Consumer Price Index", "Oct"]),
]

LINK_RE = re.compile(r'href="([^"#]+)"[^>]*>(.*?)</a>', re.I | re.S)
LINK_HINT = re.compile(r"calendar|schedule|upcoming|release dates|announcement dates|monetary policy", re.I)


def main():
    OUT.mkdir(exist_ok=True)
    s = requests.Session()
    s.headers.update(UA)
    for name, url, markers in CANDIDATES:
        try:
            r = s.get(url, timeout=40, allow_redirects=True)
        except requests.RequestException as e:
            print(f"FAIL  {name:<22} {url}\n      {type(e).__name__}: {e}\n")
            continue
        ext = ".pdf" if "pdf" in r.headers.get("content-type", "") else ".html"
        (OUT / f"{name}{ext}").write_bytes(r.content)
        text = r.text if ext == ".html" else ""
        found = [m for m in markers if m.lower() in text.lower()]
        tag = "ok  " if r.status_code == 200 and len(found) == len(markers) else "WARN"
        print(f"{tag}  {name:<22} {r.status_code} {len(r.content):>8} bytes  final={r.url}")
        print(f"      markers {len(found)}/{len(markers)} found: {found}")
        links = []
        for href, label in LINK_RE.findall(text):
            label = re.sub(r"<[^>]+>|\s+", " ", label).strip()
            if LINK_HINT.search(label) or LINK_HINT.search(href):
                links.append(f"{label[:60]} -> {urljoin(r.url, href)}")
        for l in sorted(set(links))[:12]:
            print(f"      link: {l}")
        print()
    print(f"Saved pages to {OUT}. Now: cd ~ && zip -qr probe_cal.zip probe_cal  and upload probe_cal.zip")


if __name__ == "__main__":
    sys.exit(main())
