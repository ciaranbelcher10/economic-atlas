"""Probe official release-calendar pages (China, Malaysia, New Zealand; Czechia,
Hungary and Romania added v1.7.33).

    python3 tools/probe_calendar.py            # saves pages to ~/probe_cal/, prints a report
    python3 tools/probe_calendar.py cz         # only candidates named cz_*, and writes
                                               # ~/probe_cal_cz.txt: the report plus every
                                               # page exactly as served (upload that file)

.zip uploads do not reach the chat, so the filtered run writes one text file
with each page's raw markup unchanged (v1.7.31 lesson: stripped dumps hid
live markup the parser then broke on).

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
    # Czechia (v1.7.33). The CNB's Bank Board page lists the year's meetings,
    # monetary policy ones marked; decisions at 2.30 p.m. Prague time.
    ("cz_cnb_bank_board", "https://www.cnb.cz/en/about_cnb/bank-board/", ["Bank Board meeting on monetary policy", "2026"]),
    ("cz_cnb_dates_2027", "https://www.cnb.cz/en/cnb-news/news/Dates-of-the-CNB-Boards-meetings-in-2027", ["monetary policy", "2027"]),
    ("cz_czso_home", "https://csu.gov.cz/home", ["Calendar"]),
    ("cz_czso_calendar_old", "https://czso.cz/csu/czso/calendar-of-news-releases", ["News Releases"]),
    ("cz_czso_calendar_events", "https://csu.gov.cz/calendar-of-events", ["2026"]),
    # Hungary
    ("hu_mnb_council", "https://www.mnb.hu/en/monetary-policy/the-monetary-council", ["Monetary Council"]),
    ("hu_ksh_calendar", "https://www.ksh.hu/release_calendar", ["2026"]),
    ("hu_ksh_home", "https://www.ksh.hu/?lang=en", ["Calendar"]),
    # Romania
    ("ro_nbr_home", "https://www.bnr.ro/Home.aspx", ["monetary policy"]),
    ("ro_ins_calendar", "https://insse.ro/cms/en/calendar", ["2026"]),
    ("ro_ins_home", "https://insse.ro/cms/en", ["Calendar"]),
    # second round (v1.7.35): pages the first probe pointed to
    ("hu_ksh_catalog", "https://www.ksh.hu/katalogus/", ["script"]),
    ("ro_nbr_meetings", "https://www.bnr.ro/2506-calendarul-sedintelor-consiliului-de-administratie-pe-probleme-de-politica-monetara", ["2026"]),
    ("ro_nbr_meetings_en", "https://www.bnr.ro/en/2506-calendarul-sedintelor-consiliului-de-administratie-pe-probleme-de-politica-monetara", ["2026"]),
    ("ro_ins_calendar_http", "http://www.insse.ro/cms/en/calendar", ["2026"]),
]

LINK_RE = re.compile(r'href="([^"#]+)"[^>]*>(.*?)</a>', re.I | re.S)
LINK_HINT = re.compile(r"calendar|schedule|upcoming|release dates|announcement dates|monetary policy", re.I)


def main():
    OUT.mkdir(exist_ok=True)
    only = sys.argv[1].lower() if len(sys.argv) > 1 else None
    todo = [c for c in CANDIDATES if not only or c[0].startswith(only + "_")]
    if not todo:
        print(f"no candidates named {only}_*")
        return 1
    dump = []
    s = requests.Session()
    s.headers.update(UA)
    for name, url, markers in todo:
        try:
            r = s.get(url, timeout=40, allow_redirects=True)
        except requests.RequestException as e:
            print(f"FAIL  {name:<22} {url}\n      {type(e).__name__}: {e}\n")
            continue
        ext = ".pdf" if "pdf" in r.headers.get("content-type", "") else ".html"
        (OUT / f"{name}{ext}").write_bytes(r.content)
        text = r.text if ext == ".html" else ""
        dump.append((name, r.url, r.status_code, text if ext == ".html" else "[pdf, see ~/probe_cal]"))
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
    print(f"Saved pages to {OUT}.")
    if only:
        path = Path.home() / f"probe_cal_{only}.txt"
        with open(path, "w", encoding="utf-8") as f:
            for name, url, code, text in dump:
                f.write(f"\n===== PAGE {name} {code} {url}\n{text}\n===== END {name}\n")
        print(f"Wrote {path}: upload that file (pages exactly as served).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
