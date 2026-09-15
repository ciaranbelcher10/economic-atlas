#!/usr/bin/env python3
"""Behavioural tests for series_guard, plus a replay over real git history."""
import json, sys, collections
import os as _os


def _find_repo(start):
    d = start
    while True:
        if (_os.path.exists(_os.path.join(d, "compare.html"))
                and _os.path.exists(_os.path.join(d, "data-metric-sources.json"))):
            return d
        parent = _os.path.dirname(d)
        if parent == d:
            raise SystemExit(
                "could not locate the economic-atlas clone from "
                + start + "; set ATLAS_REPO to the clone root")
        d = parent


REPO = _os.environ.get("ATLAS_REPO") or _find_repo(
    _os.path.dirname(_os.path.abspath(__file__)))

sys.path.insert(0, REPO)
from series_guard import merge_series, apply_guard


def mk(n, first, last, freq, label="X"):
    """Synthesise a series with n points spanning first..last."""
    pts = [[first, 1.0]] + [[f"pad{i}", 1.0] for i in range(max(0, n - 2))]
    if n >= 2:
        pts.append([last, 2.0])
    return {"freq": freq, "label": label, "unit": "%", "points": pts[:n] if n < 2 else pts}


def case(name, new, prev, expect, allow=None):
    chosen, verdict, detail = merge_series("cpi", new, prev, allow or {})
    ok = verdict == expect
    print(f"  {'PASS' if ok else 'FAIL'}  {name:52} -> {verdict:12} {detail[:60]}")
    return ok


print("== unit branches ==")
results = []
# must block
results.append(case("Poland: 139 monthly -> 7 monthly, both current",
     mk(7, "2026-01", "2026-07", "months"), mk(139, "2015-01", "2026-07", "months"), "kept"))
results.append(case("Chile: 140 monthly -> 55 annual",
     mk(55, "1971", "2025", "years"), mk(140, "2015-01", "2026-08", "months"), "kept"))
results.append(case("Brazil: 139 -> 127, start moved forward",
     mk(127, "2016-01", "2026-07", "months"), mk(139, "2015-01", "2026-07", "months"), "kept"))
results.append(case("Thailand: 66 annual -> 36 annual",
     mk(36, "1990", "2025", "years"), mk(66, "1960", "2025", "years"), "kept"))
# must allow
results.append(case("Mexico: 66 annual -> 140 monthly (freq upgrade)",
     mk(140, "2015-01", "2026-08", "months"), mk(66, "1960", "2025", "years"), "new"))
results.append(case("normal: 139 -> 140, one new month",
     mk(140, "2015-01", "2026-08", "months"), mk(139, "2015-01", "2026-07", "months"), "new"))
results.append(case("Thailand recovery: 36 -> 66 annual",
     mk(66, "1960", "2025", "years"), mk(36, "1990", "2025", "years"), "new"))
# stale exemption
results.append(case("EZ trade: 400 ending 2023-04 -> 12 ending 2026-05",
     mk(12, "2025-06", "2026-05", "months"), mk(400, "1990-01", "2023-04", "months"), "new-stale"))
results.append(case("BR unemp: 419 monthly ending 2015-11 -> 35 annual",
     mk(35, "1991", "2025", "years"), mk(419, "1981-01", "2015-11", "months"), "new-stale"))
# override
results.append(case("US PPI swap without override",
     mk(190, "2010-11", "2026-08", "months"), mk(668, "1971-01", "2026-08", "months"), "kept"))
results.append(case("US PPI swap with override",
     mk(190, "2010-11", "2026-08", "months"), mk(668, "1971-01", "2026-08", "months"),
     "new-allowed", {"cpi": "PPIACO -> PPIFID"}))
# graft
results.append(case("short but newer, same label/freq -> graft",
     mk(7, "2026-01", "2026-08", "months"), mk(139, "2015-01", "2026-07", "months"), "grafted"))
results.append(case("short and newer but DIFFERENT label -> keep, no seam",
     mk(7, "2026-01", "2026-08", "months", "other measure"),
     mk(139, "2015-01", "2026-07", "months", "X"), "kept"))
# failure paths
results.append(case("incoming empty, previous good",
     {"freq": "months", "label": "X", "points": []}, mk(139, "2015-01", "2026-07", "months"), "kept"))
results.append(case("no previous at all", mk(10, "2026-01", "2026-08", "months"), None, "new"))

print(f"\n  {sum(results)}/{len(results)} unit branches pass")

# ---- absence carry-over still works ----
print("\n== carry-over (absence) ==")
out = {"cpi": mk(140, "2015-01", "2026-08", "months")}
prev = {"cpi": mk(139, "2015-01", "2026-07", "months"),
        "business_confidence": mk(440, "1990-01", "2026-08", "months")}
v = apply_guard(out, prev, log=None)
ok = "business_confidence" in out and v["business_confidence"][0] == "carried-over"
print(f"  {'PASS' if ok else 'FAIL'}  absent series carried over, present series updated")
results.append(ok)

# ---- historical replay ----
print("\n== replay over recorded history ==")
_hist_path = _os.path.join(
    _os.path.dirname(_os.path.abspath(__file__)), "history_shapes.json")
if not _os.path.exists(_hist_path):
    print("  SKIPPED: history_shapes.json not present. Generate it with")
    print("           python3 tools/history_walk.py walk")
    print(f"\n  {sum(results)}/{len(results)} unit branches pass, "
          "replay skipped")
    raise SystemExit(0 if all(results) else 1)
hist = json.load(open(_hist_path))
counts = collections.Counter()
blocked = []
for f, entries in hist.items():
    prev_s = None
    for e in entries:
        cur = e["series"]
        if prev_s:
            for k in set(prev_s) & set(cur):
                a, b = prev_s[k], cur[k]
                if a["n"] == b["n"] and a["first"] == b["first"] and a["freq"] == b["freq"]:
                    continue
                pa = mk(a["n"], a["first"], a["last"], a["freq"], a["label"])
                pb = mk(b["n"], b["first"], b["last"], b["freq"], b["label"])
                _, verdict, detail = merge_series(k, pb, pa, {})
                counts[verdict] += 1
                if verdict in ("kept", "grafted"):
                    blocked.append((f, k, e["date"][:10], a["n"], b["n"], verdict))
        prev_s = cur

print("  verdicts across every recorded shape transition:")
for v, c in counts.most_common():
    print(f"    {v:14} {c}")
print(f"\n  transitions the guard would have blocked or grafted: {len(blocked)}")
agg = collections.Counter((b[0], b[1]) for b in blocked)
print("  top affected series:")
for (f, k), c in agg.most_common(12):
    print(f"    {f:16}{k:22} {c} blocked transitions")
