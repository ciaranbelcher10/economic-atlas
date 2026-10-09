"""Offline tests for Poland's NBP reference rate (fetch_pl.fetch_policy_rate,
v1.7.34). Run: python3 tools/test_fetch_pl_policy.py"""
from __future__ import annotations

import io, os, sys
from contextlib import redirect_stdout

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import fetch_pl as F  # noqa: E402
import bis_daily  # noqa: E402

N, BAD = [0], []
def check(ok, msg):
    N[0] += 1
    if not ok:
        BAD.append(msg); print("FAIL", msg)

class R:
    def __init__(self, text="", code=200): self.text, self.status_code = text, code
    def raise_for_status(self):
        if self.status_code >= 400: raise RuntimeError(self.status_code)

def months(a, b):
    y, m = int(a[:4]), int(a[5:]); out = []
    while f"{y}-{m:02d}" <= b:
        out.append(f"{y}-{m:02d}"); m += 1
        if m == 13: y, m = y + 1, 1
    return out

ROWS = [[p, 24.0 if p < "1998-06" else 5.75] for p in months("1995-01", "2026-08")]
def csvtxt(rows): return "TIME_PERIOD,OBS_VALUE\n" + "".join(f"{p},{v}\n" for p, v in rows)
_orig_get = bis_daily.requests.get
def run(rows, daily="TIME_PERIOD,OBS_VALUE\n2026-08-31,5.75\n2026-09-30,5.75\n"):
    seen = []
    def get(url, **kw):
        seen.append(url)
        return R(csvtxt(rows)) if "M.PL" in url else R(daily)
    bis_daily.requests.get = get
    try:
        with redirect_stdout(io.StringIO()):
            return F.fetch_policy_rate(get=get), seen
    finally:
        bis_daily.requests.get = _orig_get

pts, seen = run(ROWS)
check(pts[0][0] == "1998-02", f"served from February 1998: {pts[0]}")
check(not any(p < "1998-02" for p, v in pts), "nothing before the reference rate existed")
check(pts[-1][0] == "2026-09", f"BIS daily extends past the monthly series: {pts[-1]}")
check(any("WS_CBPOL/1.0/M.PL" in u for u in seen), "asks BIS for M.PL")
try:
    run(ROWS[:-1] + [["2026-08", 575.0]])
    check(False, "an implausible value is refused")
except ValueError as e:
    check("implausible" in str(e), "an implausible value is refused")
try:
    run([[p, 20.0] for p in months("1995-01", "1997-12")])
    check(False, "a series ending before 1998 is refused")
except ValueError as e:
    check("no observations" in str(e), "a series ending before 1998 is refused")
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "fetch_pl.py")).read()
check('("policy_rate", fetch_policy_rate,' in src, "policy_rate is in fetch_pl's extras")
print(f"{N[0]} checks, {len(BAD)} failures")
sys.exit(1 if BAD else 0)
