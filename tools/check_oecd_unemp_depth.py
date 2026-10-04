#!/usr/bin/env python3
"""Read-only pre-deploy check for v1.6.43: does OECD's monthly unemployment
history reach back as far as what the site serves for KOR, ISR and TUR?

The series guard accepts a more current source even with shorter history
(verdict "new-current"), so if OECD starts later the switch would quietly
drop years from the charts. Prints one line per country and exits 1 if any
would lose history. Needs access to sdmx.oecd.org.
"""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import requests, oecd_unemp  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
bad = 0
for iso, f in (("KOR", "data-kr.json"), ("ISR", "data-il.json"), ("TUR", "data-tr.json")):
    site = json.load(open(os.path.join(ROOT, f), encoding="utf-8"))["series"]["unemployment"]["points"]
    r = requests.get(oecd_unemp.url(iso), timeout=90, headers=oecd_unemp.UA)
    pts = oecd_unemp.parse(r.text) if r.ok else []
    if not pts:
        print(f"{iso}: OECD status={r.status_code}, no points"); bad += 1
    else:
        loses = pts[0][0] > site[0][0]
        bad += loses
        print(f"{iso}: site {site[0][0]}..{site[-1][0]} ({len(site)})  oecd {pts[0][0]}..{pts[-1][0]} ({len(pts)})"
              + ("  WOULD LOSE HISTORY" if loses else "  ok"))
    time.sleep(5)
sys.exit(1 if bad else 0)
