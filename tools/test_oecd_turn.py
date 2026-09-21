#!/usr/bin/env python3
"""Branch tests for oecd_turn: which group each hour serves, and what skips."""
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import oecd_turn as ot

os.environ.pop("OECD_TURN_GROUP", None)
PASS = FAIL = 0


def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  FAIL  {name}")


def at(hour):
    return datetime(2026, 9, 21, hour, 0, tzinfo=timezone.utc)


def raises(script, hour):
    try:
        ot.check(script, at(hour))
        return False
    except ot.NotThisHour:
        return True


# --- the clock ----------------------------------------------------------
check("hour 0 serves A", ot.current_group(at(0)) == "A")
check("hour 1 serves B", ot.current_group(at(1)) == "B")
check("hour 2 serves C", ot.current_group(at(2)) == "C")
check("hour 3 wraps back to A", ot.current_group(at(3)) == "A")
check("hour 23 serves C", ot.current_group(at(23)) == "C")
# every group gets exactly eight hours a day
counts = {g: sum(1 for h in range(24) if ot.current_group(at(h)) == g) for g in "ABC"}
check("each group gets eight hours a day", counts == {"A": 8, "B": 8, "C": 8})
# and no country ever waits more than three hours between turns
for script, grp in ot.GROUPS.items():
    hours = [h for h in range(24) if ot.current_group(at(h)) == grp]
    gaps = [(hours[(i + 1) % len(hours)] - hours[i]) % 24 for i in range(len(hours))]
    if max(gaps) != 3:
        check(f"{script} never waits more than three hours", False)
        break
else:
    check("no country waits more than three hours between OECD turns", True)

# --- who skips ----------------------------------------------------------
check("a group-A script fetches in hour 0", not raises("fetch_au.py", 0))
check("a group-A script skips in hour 1", raises("fetch_au.py", 1))
check("a group-B script fetches in hour 1", not raises("fetch_de.py", 1))
check("a group-C script fetches in hour 2", not raises("fetch_no.py", 2))
check("a group-C script skips in hour 0", raises("fetch_no.py", 0))
check("a full path is resolved to its file name",
      not raises("/home/runner/work/x/fetch_au.py", 0))

# --- fail open ------------------------------------------------------------
check("an unmapped script always fetches (a new country keeps working)",
      not raises("fetch_newcountry.py", 1))
check("a test runner is never skipped", not raises("tools/test_oecd_prices.py", 2))

# --- the pairing that must hold --------------------------------------------
check("fetch_data.py and fetch_us.py share a group (both write data-us.json)",
      ot.GROUPS["fetch_data.py"] == ot.GROUPS["fetch_us.py"])

# --- every group is populated, and balanced by OECD weight -----------------
heavy = {"fetch_au.py", "fetch_br.py", "fetch_ca.py", "fetch_cl.py", "fetch_co.py",
         "fetch_ch.py", "fetch_id.py", "fetch_in.py", "fetch_il.py", "fetch_mx.py",
         "fetch_no.py", "fetch_za.py", "fetch_kr.py", "fetch_tr.py"}
per = {g: sum(1 for s in heavy if ot.GROUPS[s] == g) for g in "ABC"}
check("heavy OECD countries spread five, five, four", sorted(per.values()) == [4, 5, 5])
check("all 32 country scripts are mapped", len(ot.GROUPS) == 32)

# --- overrides --------------------------------------------------------------
os.environ["OECD_TURN_GROUP"] = "C"
check("OECD_TURN_GROUP forces a group", ot.current_group(at(0)) == "C")
os.environ["OECD_TURN_GROUP"] = "ALL"
check("OECD_TURN_GROUP=ALL disables the rotation", not raises("fetch_au.py", 1))
os.environ["OECD_TURN_GROUP"] = "nonsense"
check("an unrecognised override is ignored, not obeyed",
      ot.current_group(at(1)) == "B")
os.environ.pop("OECD_TURN_GROUP", None)

# --- a skip is not an ordinary failure --------------------------------------
check("NotThisHour is catchable as an Exception, so existing handlers keep "
      "the script running", issubclass(ot.NotThisHour, Exception))

total = PASS + FAIL
print(f"{PASS}/{total} oecd rotation branches pass")
sys.exit(1 if FAIL else 0)
