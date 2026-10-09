"""Find the data source behind CZSO's "Calendar of events" (v1.7.33).

csu.gov.cz/calendar-of-events renders nothing server side ("Loading..."):
a widget named "udalosti" (events) fills it from an API, with a category
"rychle-informace" (News releases). The API address lives in the widget
bundle /resources/statistika/widgets/main.js. This script downloads that
bundle and any script chunks it names, and prints every string that looks
like an API path, plus the text around each "udalost" mention.

    python3 tools/probe_czso_api.py

Read-only; writes ~/probe_czso_api.txt (upload that file).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import urljoin

import requests

BASE = "https://csu.gov.cz/resources/statistika/widgets/main.js"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36", "Accept-Language": "en"}
STR = re.compile(r"""["'`]([^"'`\s]{0,200}(?:api|rest|udalost|kalendar|rychle|graphql|json)[^"'`\s]{0,200})["'`]""", re.I)
CHUNK = re.compile(r"""["']([\w./-]+\.js)["']""")
OUT = Path.home() / "probe_czso_api.txt"


def main() -> int:
    s = requests.Session()
    s.headers.update(UA)
    lines, seen, queue = [], set(), [BASE]
    while queue and len(seen) < 40:
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        try:
            r = s.get(url, timeout=40)
        except requests.RequestException as exc:
            lines.append(f"FAIL {url} {exc}")
            continue
        text = r.text
        lines.append(f"\n===== {r.status_code} {len(text)} bytes {url}")
        for m in sorted(set(STR.findall(text))):
            lines.append(f"  str: {m}")
        for m in list(re.finditer(r"udalost", text, re.I))[:15]:
            lines.append(f"  ctx: {text[max(0, m.start() - 300):m.start() + 300]!r}")
        for c in CHUNK.findall(text):
            nxt = urljoin(url, c)
            if "csu.gov.cz" in nxt and nxt not in seen:
                queue.append(nxt)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(l for l in lines if l.startswith(("=====", "FAIL", "\n====="))))
    print(f"Wrote {OUT}: upload that file.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
