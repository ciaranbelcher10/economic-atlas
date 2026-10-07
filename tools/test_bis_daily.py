"""Offline tests for bis_daily.extend (v1.7.13). Run: python3 tools/test_bis_daily.py"""
import io, os, sys
from contextlib import redirect_stdout
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import bis_daily

N = F = 0
def check(ok, msg):
    global N, F
    N += 1
    if not ok: F += 1; print("FAIL:", msg)

class R:
    def __init__(self, text="", code=200): self.text, self.status_code = text, code
    def raise_for_status(self):
        if self.status_code >= 400: raise RuntimeError(f"HTTP {self.status_code}")

def daily(rows): return "TIME_PERIOD,OBS_VALUE\n" + "\n".join(f"{d},{v}" for d, v in rows)
SEEN = []
def install(resp):
    def g(url, **kw):
        SEEN.append(url)
        if isinstance(resp, Exception): raise resp
        return resp
    bis_daily.requests.get = g

M = [["2026-07", 3.0], ["2026-08", 3.0]]
def run(resp, monthly=M, area="MY"):
    install(resp)
    with redirect_stdout(io.StringIO()):
        return bis_daily.extend([list(p) for p in monthly], area, "test")

# extends when the daily agrees at the join; month-end value wins
out = run(R(daily([("2026-08-29", 3.0), ("2026-09-04", 3.0), ("2026-09-10", 2.75), ("2026-10-06", 2.75)])))
check(out == M + [["2026-09", 2.75], ["2026-10", 2.75]], f"extends with month-end daily values: {out}")
check("D.MY" in SEEN[-1] and "startPeriod=2026-08-01" in SEEN[-1], f"asks D.<area> from the last monthly month: {SEEN[-1]}")
run(R(daily([("2026-08-29", 3.0)])), area="CN"); check("D.CN" in SEEN[-1], "China queries D.CN")
# nothing newer: unchanged
check(run(R(daily([("2026-08-29", 3.0)]))) == M, "no newer daily months: unchanged")
# planted faults: all leave the monthly series as it is
check(run(R(daily([("2026-08-29", 4.35), ("2026-09-04", 4.35)]))) == M, "different measure at the join (mismatch) is not spliced")
check(run(R(daily([("2026-09-04", 2.75)]))) == M, "no overlap month to check: not spliced")
check(run(R("", code=503)) == M, "HTTP error: unchanged")
check(run(RuntimeError("timeout")) == M, "network exception: unchanged")
check(run(R("garbage,,\n1,2")) == M, "unparseable CSV: unchanged")
check(run(R(daily([("2026-08", 3.0), ("2026-09", 2.75)]))) == M, "monthly-shaped periods are not taken as daily")
check(run(R(daily([("2026-08-29", 3.0), ("2026-09-04", "NaN")]))) == M, "NaN observations ignored")
check(run(R(daily([])), monthly=[]) == [], "empty monthly: unchanged")
print(f"{N} checks, {F} failures")
sys.exit(1 if F else 0)
