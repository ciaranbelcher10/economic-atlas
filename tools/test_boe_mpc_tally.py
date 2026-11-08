"""v1.9.102: fetch_boe_mpc.py writes rate_votes (counts per voted rate, no names) from a mock BoE sheet.
Run: python3 tools/test_boe_mpc_tally.py"""
import io, os, sys, datetime as dt
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
try:
    import openpyxl
except ImportError:
    print("test_boe_mpc_tally: FAIL openpyxl missing"); sys.exit(1)
import fetch_boe_mpc as F
wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Bank Rate Decisions"
ws.cell(3, 3, "Current members")
for i in range(9): ws.cell(3, 4 + i, "M%d" % i)
ws.cell(3, 13, "Past members")
ws.cell(11, 3, "Bank Rate"); ws.cell(12, 3, 0.0375)
rows = [(dt.datetime(2026, 11, 5), 0.04, [0.0425] + [0.04] * 8),
        (dt.datetime(2026, 9, 17), 0.0375, [0.04] * 3 + [0.0375] * 6),
        (dt.datetime(2026, 8, 6), 0.0375, [0.0375] * 9)]
for r, (d, rate, v) in enumerate(rows):
    ws.cell(13 + r, 2, d); ws.cell(13 + r, 3, rate)
    for i, x in enumerate(v): ws.cell(13 + r, 4 + i, x)
buf = io.BytesIO(); wb.save(buf)
class R:
    status_code = 200; content = buf.getvalue()
    def raise_for_status(self): pass
F.requests.get = lambda *a, **k: R()
m = {x["date"]: x for x in F.fetch_and_parse()}
fails = 0
def ok(c, msg):
    global fails
    if not c: fails += 1; print("  FAIL  " + msg)
nov, sep = m["2026-11-05"], m["2026-09-17"]
ok(nov["rate_votes"] == {"4.25": 1, "4": 8}, "Nov tally 8 at 4, 1 at 4.25: %s" % nov["rate_votes"])
ok(list(nov["rate_votes"]) == ["4.25", "4"], "highest rate first")
ok((nov["hold"], nov["hike"], nov["cut"]) == (0, 9, 0), "hold/hike/cut counts unchanged")
ok(sep["rate_votes"] == {"4": 3, "3.75": 6}, "Sep tally %s" % sep["rate_votes"])
ok(sum(nov["rate_votes"].values()) == nov["total_votes"], "tally adds up to the votes")
ok(F._rate_key(0.1) == "0.1" and F._rate_key(5.25) == "5.25" and F._rate_key(4.0) == "4", "rate keys")
ok(not any(k.startswith("M") for x in m.values() for k in x["rate_votes"]), "no member names in the output")
print("test_boe_mpc_tally: 7 checks, %d failures" % fails)
sys.exit(1 if fails else 0)
