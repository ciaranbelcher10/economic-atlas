"""Follow-up calendar probe (v1.7.30): Stats NZ's main releases, OpenDOSM's next month.

    python3 tools/probe_calendar_nz.py    # writes ~/probe_cal_nz.txt (a text report to upload)

Stats NZ: the release-calendar page's HTML only holds the "Other" table; the
main releases (CPI, GDP, labour market) load from a script. This keeps the
scripts, lists every URL they mention that looks like an endpoint, and tries
the likely ones, printing the first lines of any that answer with data.
OpenDOSM: tries ways to ask for next month's grid and checks for a Next.js
data block. Read-only; writes only the report file.
"""
import re
from pathlib import Path
from urllib.parse import urljoin

import requests

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
OUT = Path.home() / "probe_cal_nz.txt"
s = requests.Session(); s.headers.update(UA)
lines = []
def log(x=""):
    print(x); lines.append(str(x))

def get(url):
    try:
        r = s.get(url, timeout=40)
        return r
    except requests.RequestException as e:
        log(f"  FAIL {url}: {e}")
        return None

log("== Stats NZ release calendar")
base = "https://www.stats.govt.nz/release-calendar/"
r = get(base)
if r is not None:
    t = r.text
    log(f"  {r.status_code} {len(t)} chars")
    srcs = sorted(set(re.findall(r'<script[^>]+src="([^"]+)"', t)))
    log(f"  script files: {srcs[:15]}")
    inline = re.findall(r"<script(?![^>]+src)[^>]*>(.*?)</script>", t, re.S)
    cands = set()
    for blob in [t] + inline:
        for u in re.findall(r'["\'](/[A-Za-z0-9_\-/]*(?:api|release|calendar|graphql|feed|json)[A-Za-z0-9_\-/\.?=&%]*)["\']', blob, re.I):
            cands.add(u)
        for u in re.findall(r'https?://[^"\'\s<>]*(?:api|release|calendar|graphql)[^"\'\s<>]*', blob, re.I):
            cands.add(u)
    for src in srcs:
        if "stats" in src or src.startswith("/"):
            js = get(urljoin(base, src))
            if js is not None and js.status_code == 200:
                for u in re.findall(r'["\'](/[A-Za-z0-9_\-/]*(?:api|release|calendar)[A-Za-z0-9_\-/\.?=&%]*)["\']', js.text, re.I):
                    cands.add(u)
    log(f"  endpoint-like URLs found ({len(cands)}):")
    for u in sorted(cands)[:60]:
        log(f"    {u}")
    for u in ["https://www.stats.govt.nz/release-calendar/?type=upcoming", "https://www.stats.govt.nz/api/release-calendar",
              "https://www.stats.govt.nz/release-calendar/getReleases", "https://www.stats.govt.nz/release-calendar/data"] + \
             [urljoin(base, c) for c in sorted(cands) if re.search(r"api|getrelease|json", c, re.I)][:10]:
        x = get(u)
        if x is not None:
            body = x.text[:400].replace("\n", " ")
            log(f"  try {x.status_code} {x.headers.get('content-type','')[:30]} {u}\n      {body}")
    for kw in ["Consumers price index", "Labour market statistics", "Gross domestic product"]:
        i = t.lower().find(kw.lower())
        log(f"  '{kw}' in raw page: {i >= 0}" + (f" :: {t[max(0, i-200):i+150]!r}" if i >= 0 else ""))

log("\n== OpenDOSM next month")
for u in ["https://open.dosm.gov.my/publications/upcoming", "https://open.dosm.gov.my/publications/upcoming?month=11&year=2026",
          "https://open.dosm.gov.my/publications/upcoming?date=2026-11"]:
    x = get(u)
    if x is not None:
        lab = re.findall(r">((?:January|February|March|April|May|June|July|August|September|October|November|December) 20\d\d)<", x.text)
        nd = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.{0,600})', x.text, re.S)
        log(f"  {x.status_code} {u}  month label(s) {lab[:2]}  __NEXT_DATA__: {nd.group(1)[:600]!r}" if nd else f"  {x.status_code} {u}  month label(s) {lab[:2]}  no __NEXT_DATA__")
        for m in sorted(set(re.findall(r'https://api[^"\'\s<>]+', x.text)))[:10]:
            log(f"    api url: {m}")

OUT.write_text("\n".join(lines))
print(f"\nwrote {OUT}  ({OUT.stat().st_size // 1024} KB): upload this file")
