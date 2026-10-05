#!/usr/bin/env python3
"""v1.6.44: the OECD group is fixed for a whole Actions run.

    python3 tools/test_oecd_turn_run.py   # "N ok", exit 1 on failure
"""
import os, sys
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import oecd_turn as ot  # noqa: E402

ok, fails = 0, []
def check(cond, msg):
    global ok
    ok += bool(cond)
    if not cond: fails.append(msg)

os.environ.pop("OECD_TURN_GROUP", None)
os.environ["GITHUB_RUN_NUMBER"] = "1027"          # 1027 % 3 == 1 -> B
check(ot.current_group() == "B", "run number decides the group")

# The 4 Oct 14:57 run crossed 15:00; both checks must now agree.
import unittest.mock as m
for t in (datetime(2026, 10, 4, 14, 59, tzinfo=timezone.utc), datetime(2026, 10, 4, 15, 1, tzinfo=timezone.utc)):
    with m.patch.object(ot, "datetime") as dt:
        dt.now.return_value = t
        check(ot.current_group() == "B", f"same group at {t:%H:%M} within one run")

check([ot.ORDER[n % 3] for n in (1026, 1027, 1028, 1029)] == ["A", "B", "C", "A"], "consecutive runs rotate A, B, C")
check(ot.current_group(datetime(2026, 1, 1, 2, tzinfo=timezone.utc)) == "C", "explicit now still uses the clock")

os.environ["OECD_TURN_GROUP"] = "A"
check(ot.current_group() == "A", "OECD_TURN_GROUP still overrides the run number")
os.environ["OECD_TURN_GROUP"] = "ALL"
check(ot.current_group() == "ALL", "ALL still disables rotation")
os.environ.pop("OECD_TURN_GROUP")

for bad in ("", "abc"):
    os.environ["GITHUB_RUN_NUMBER"] = bad
    with m.patch.object(ot, "datetime") as dt:
        dt.now.return_value = datetime(2026, 1, 1, 1, tzinfo=timezone.utc)
        check(ot.current_group() == "B", f"run number {bad!r} falls back to the clock")
os.environ.pop("GITHUB_RUN_NUMBER")

for f in fails: print("FAIL", f)
print(f"{ok} ok")
sys.exit(1 if fails else 0)
