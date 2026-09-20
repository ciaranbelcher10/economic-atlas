#!/usr/bin/env python3
"""Branch tests for oecd_prices.

Runs entirely offline against stubbed HTTP responses. Bash in the build
sandbox cannot reach sdmx.oecd.org, and more importantly a test that depends
on a live provider tells you about the provider, not the code.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import oecd_prices as op

op.REQUEST_PAUSE_S = 0  # no need to pace a stub

PASS = FAIL = 0


def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  FAIL  {name}")


class Resp:
    def __init__(self, status=200, text=""):
        self.status_code = status
        self.text = text


def csv_for(area, n, start_year=2015, monthly=True, methodology="N", value=lambda i: 100 + i):
    head = "REF_AREA,METHODOLOGY,ADJUSTMENT,TIME_PERIOD,OBS_VALUE\n"
    rows = []
    for i in range(n):
        if monthly:
            y, m = start_year + i // 12, i % 12 + 1
            period = f"{y}-{m:02d}"
        else:
            y, q = start_year + i // 4, i % 4 + 1
            period = f"{y}-Q{q}"
        rows.append(f"{area},{methodology},N,{period},{value(i)}")
    return head + "\n".join(rows)


def current_csv(area, n, monthly=True):
    """A series whose last point is the current period, so it passes freshness.

    Built by counting back from now rather than guessing a start year: the
    freshness bar is measured against the last point, so the fixture has to
    actually end at the present or it tests the wrong branch.
    """
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    head = "REF_AREA,METHODOLOGY,ADJUSTMENT,TIME_PERIOD,OBS_VALUE\n"
    rows = []
    if monthly:
        end = now.year * 12 + (now.month - 1)
        for i in range(n):
            idx = end - (n - 1 - i)
            rows.append(f"{area},N,N,{idx // 12:04d}-{idx % 12 + 1:02d},{100 + i}")
    else:
        end = now.year * 4 + ((now.month - 1) // 3)
        for i in range(n):
            idx = end - (n - 1 - i)
            rows.append(f"{area},N,N,{idx // 4:04d}-Q{idx % 4 + 1},{100 + i}")
    return head + "\n".join(rows)


# --- period arithmetic -------------------------------------------------
check("month back within year", op.period_back_1("2026-08") == "2026-07")
check("month back across year", op.period_back_1("2026-01") == "2025-12")
check("quarter back within year", op.period_back_1("2026-Q3") == "2026-Q2")
check("quarter back across year", op.period_back_1("2026-Q1") == "2025-Q4")
check("garbage period is None", op.period_back_1("not-a-period") is None)

# --- rate derivation ---------------------------------------------------
pts = [["2026-01", 100.0], ["2026-02", 101.0], ["2026-03", 102.01]]
rates = op.rate_from_index(pts)
check("first period dropped (no predecessor)", len(rates) == 2)
check("rate value correct", rates[0] == ["2026-02", 1.0])
check("rate compounds correctly", rates[1] == ["2026-03", 1.0])

# a hole must not be bridged: Feb missing means March has no predecessor
holed = [["2026-01", 100.0], ["2026-03", 102.0], ["2026-04", 103.0]]
holed_rates = op.rate_from_index(holed)
check("hole is not bridged", [r[0] for r in holed_rates] == ["2026-04"])

# quarterly
q = [["2025-Q4", 100.0], ["2026-Q1", 102.0]]
check("quarterly rate derived", op.rate_from_index(q) == [["2026-Q1", 2.0]])

# --- fetch: happy path -------------------------------------------------
calls = []


def ok_get(url, **kw):
    calls.append(url)
    return Resp(200, current_csv("BRA", 200))


got = op.fetch_cpi_index(["BRA"], "M", http_get=ok_get)
check("index returned", got is not None and len(got) == 200)
check("index sorted by period", got == sorted(got, key=lambda p: p[0]))
check("IX requested, not PA", all(".IX." in u for u in calls))
check("all four combos tried", len(calls) == 4)

# --- fetch: 429 is not absence ----------------------------------------
def throttled_get(url, **kw):
    return Resp(429, "")


check("429 yields None, not a short series",
      op.fetch_cpi_index(["BRA"], "M", http_get=throttled_get) is None)

n_calls = []


def throttled_counting(url, **kw):
    n_calls.append(url)
    return Resp(429, "")


op.fetch_cpi_index(["BRA"], "M", http_get=throttled_counting)
check("bails out after repeated 429s rather than burning every combo",
      len(n_calls) <= op.MAX_CONSECUTIVE_429)

# --- fetch: absent -----------------------------------------------------
check("404 yields None",
      op.fetch_cpi_index(["BRA"], "M", http_get=lambda u, **k: Resp(404, "")) is None)
check("request exception yields None",
      op.fetch_cpi_index(["BRA"], "M",
                         http_get=lambda u, **k: (_ for _ in ()).throw(RuntimeError("boom"))) is None)

# --- fetch: too short --------------------------------------------------
check("a series under the length bar is refused",
      op.fetch_cpi_index(["BRA"], "M",
                         http_get=lambda u, **k: Resp(200, current_csv("BRA", 10))) is None)

# --- fetch: stale ------------------------------------------------------
check("a discontinued base-year series is refused on age",
      op.fetch_cpi_index(["BRA"], "M",
                         http_get=lambda u, **k: Resp(200, csv_for("BRA", 200, start_year=1995))) is None)

# --- fetch: longest wins, not first ------------------------------------
seq = []


def mixed_get(url, **kw):
    # C2018 answers first but with little history; C1999 holds far more
    seq.append(url)
    if "COICOP2018" in url:
        return Resp(200, current_csv("BRA", 30))
    return Resp(200, current_csv("BRA", 250))


best = op.fetch_cpi_index(["BRA"], "M", http_get=mixed_get)
check("longest candidate wins over the one that answered first",
      best is not None and len(best) == 250)

# --- series construction ----------------------------------------------
idx = [[f"2020-{m:02d}", 100.0 + m] for m in range(1, 13)]
idx += [[f"2021-{m:02d}", 112.0 + m] for m in range(1, 13)]
idx += [[f"2022-{m:02d}", 124.0 + m] for m in range(1, 13)]
built = op.build_mom_series(idx, "M", "OECD live prices system")
check("monthly series built", built is not None)
check("monthly freq recorded", built and built["freq"] == "months")
check("unit is percent", built and built["unit"] == "%")
check("label names the basis", built and "month on month" in built["label"])

qidx = [[f"{y}-Q{q}", 100.0 + i] for i, (y, q) in
        enumerate([(y, q) for y in range(2000, 2010) for q in range(1, 5)])]
qbuilt = op.build_mom_series(qidx, "Q", "OECD live prices system")
check("quarterly series built", qbuilt is not None)
check("quarterly freq recorded", qbuilt and qbuilt["freq"] == "quarters")
check("quarterly label names quarter on quarter",
      qbuilt and "quarter on quarter" in qbuilt["label"])

check("too few derived points leaves the key out",
      op.build_mom_series([["2026-01", 100.0], ["2026-02", 101.0]], "M", "x") is None)
check("empty input leaves the key out", op.build_mom_series([], "M", "x") is None)

# --- mom_points: the one-call path the fetch scripts use ---------------
check("mom_points returns derived rates",
      len(op.mom_points(["BRA"], "M", http_get=lambda u, **k: Resp(200, current_csv("BRA", 200))) or []) == 199)
check("mom_points returns None when there is no index",
      op.mom_points(["BRA"], "M", http_get=lambda u, **k: Resp(404, "")) is None)
check("mom_points returns None when throttled",
      op.mom_points(["BRA"], "M", http_get=lambda u, **k: Resp(429, "")) is None)
check("mom_points refuses a series under the bar",
      op.mom_points(["BRA"], "M", http_get=lambda u, **k: Resp(200, current_csv("BRA", 20))) is None)
check("mom_points handles quarterly",
      len(op.mom_points(["AUS"], "Q", http_get=lambda u, **k: Resp(200, current_csv("AUS", 100, monthly=False))) or []) == 99)

total = PASS + FAIL
print(f"{PASS}/{total} oecd price index branches pass")
sys.exit(1 if FAIL else 0)
