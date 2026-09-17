"""Behavioural tests for inflation_sources.py.   python3 tools/test_inflation_sources.py"""
import os, sys
from datetime import datetime, timezone
sys.path.insert(0, os.environ.get("ATLAS_REPO") or os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import inflation_sources as inf

T = datetime(2026, 9, 16, tzinfo=timezone.utc)
cases = []
def check(name, got, want):
    cases.append((name, got == want, got, want))

lv = [["2024-01", 100.0], ["2024-02", 101.0], ["2025-01", 102.0], ["2025-03", 103.0], ["2025-02", 102.01]]
check("12-month rate matched by period", inf.hicp_yoy(sorted(lv)), [["2025-01", 2.0], ["2025-02", 1.0]])
check("gap does not shift comparisons", [p[0] for p in inf.hicp_yoy(sorted(lv))], ["2025-01", "2025-02"])

def months(n, start=(2015, 1), val=100.0, step=0.2):
    y, m = start; out = []
    for i in range(n):
        out.append([f"{y:04d}-{m:02d}", round(val + i * step, 3)])
        m += 1
        if m == 13: y, m = y + 1, 1
    return out

good = months(139)  # 2015-01 to 2026-07
s = inf.fetch_hicp(lambda sid, f, k: good, "CP0000SEM086NEST", "K")
check("HICP accepted with HICP label", (s["label"], s["freq"], s["points"][-1][0]), ("HICP, all items, YoY (Eurostat, CP0000SEM086NEST)", "months", "2026-07"))
check("HICP label stable, so the guard can graft", inf.hicp_label("CP0000PLM086NEST"), "HICP, all items, YoY (Eurostat, CP0000PLM086NEST)")
check("HICP failure returns None, never another measure", inf.fetch_hicp(lambda *a: 1/0, "CP0000SEM086NEST", "K"), None)
check("HICP too short returns None", inf.fetch_hicp(lambda *a: months(20), "CP0000SEM086NEST", "K"), None)
try:
    inf.fetch_hicp(lambda *a: good, "CPIAUCSL", "K"); bad_id = "accepted"
except ValueError:
    bad_id = "refused"
check("a non-HICP id is refused outright", bad_id, "refused")
check("no key returns None", inf.fetch_hicp(lambda *a: good, "CP0000SEM086NEST", ""), None)

class R:
    def __init__(s, text, status=200): s.text, s.status = text, status
    def raise_for_status(s):
        if s.status >= 400: raise RuntimeError(s.status)
HDR = "REF_AREA,METHODOLOGY,ADJUSTMENT,TIME_PERIOD,OBS_VALUE\n"
def csv_rows(area, meth, pts, adj="N"):
    return "".join(f"{area},{meth},{adj},{p},{v}\n" for p, v in pts)
nat = months(140, val=1.0, step=0.01)   # to 2026-08
hic = months(140, val=2.0, step=0.01)
mixed = HDR + csv_rows("SWE", "HICP", hic) + csv_rows("SWE", "N", nat)
r = inf.fetch_national_cpi("SWE", get=lambda url, **k: R(mixed), today=T, pause=0)
check("only national methodology taken from a mixed response", r["points"][0][1], 1.0)
check("national label", r["label"], "CPI, national definition, all items, YoY (OECD live prices system)")
only_hicp = HDR + csv_rows("POL", "HICP", hic)
check("HICP-only response is refused for cpi_national", inf.fetch_national_cpi("POL", get=lambda url, **k: R(only_hicp), today=T, pause=0), None)
stale = HDR + csv_rows("DNK", "N", months(100))   # ends 2023-04
check("stale national series refused", inf.fetch_national_cpi("DNK", get=lambda url, **k: R(stale), today=T, pause=0), None)
short = HDR + csv_rows("IRL", "N", months(7, start=(2026, 1)))
check("short national series refused", inf.fetch_national_cpi("IRL", get=lambda url, **k: R(short), today=T, pause=0), None)
sa = HDR + csv_rows("SWE", "N", nat, adj="Y")
check("seasonally adjusted rows refused", inf.fetch_national_cpi("SWE", get=lambda url, **k: R(sa), today=T, pause=0), None)
calls = []
def flaky(url, **k):
    calls.append(url)
    return R("", 404) if "C2018" in url else R(HDR + csv_rows("SWE", "N", nat))
r2 = inf.fetch_national_cpi("SWE", get=flaky, today=T, pause=0)
check("falls through to the older dataflow", (len(calls), r2["points"][-1][0]), (2, "2026-08"))
check("request never uses the wildcard methodology", all(".M.N.CPI." in u for u in calls), True)
check("July is not stale in mid-September", inf._age_days("2026-07", T) <= inf.NATIONAL_MAX_AGE_DAYS, True)
check("April is stale in mid-September", inf._age_days("2026-04", T) > inf.NATIONAL_MAX_AGE_DAYS, True)

ok = sum(1 for c in cases if c[1])
for name, passed, got, want in cases:
    if not passed: print(f"FAIL {name}: got {got!r}, want {want!r}")
print(f"{ok}/{len(cases)} inflation source branches pass")
sys.exit(0 if ok == len(cases) else 1)
