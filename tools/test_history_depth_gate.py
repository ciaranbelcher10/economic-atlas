#!/usr/bin/env python3
"""Tests for tools/history_depth_gate.py, including the planted negative."""
import copy
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import history_depth_gate as g  # noqa: E402

REPO = g.REPO
NEW30 = ("cn my nz vn ph tw hk be pt fi gr cz hu ro sk hr bg lt ee lv si lu cy mt sa ng eg pe is pk").split()
FILES = sorted(os.path.basename(p) for p in glob.glob(os.path.join(REPO, "data-??.json")))
BASE = {f: json.load(open(os.path.join(REPO, f), encoding="utf-8")) for f in FILES}
fails = []


def expect(name, cond):
    print(("ok    " if cond else "FAIL  ") + name)
    if not cond:
        fails.append(name)


def run(mutate=None, allow=None):
    """Baseline = repo as it is; 'new' = same data after mutate(copy)."""
    new = copy.deepcopy(BASE)
    if mutate:
        mutate(new)
    return g.check(FILES, "TEST", allow or {}, loader=lambda f: new[f],
                   base_loader=lambda f: BASE[f])


def shorten_mt(new):
    pts = new["data-mt.json"]["series"]["gdp_real"]["points"]
    new["data-mt.json"]["series"]["gdp_real"]["points"] = pts[40:]   # drop 10 years of quarters


findings, warns, compared = run()
expect("unchanged data: 0 findings", not findings)
expect(f"compared {compared} series (must be > 800)", compared > 800)
covered = {os.path.basename(f)[5:7] for f in FILES}
expect("all 30 new economies are iterated", set(NEW30) <= covered)

findings, _, _ = run(shorten_mt)
expect("PLANTED shortened Malta gdp_real fails", any("data-mt.json:gdp_real" in x for x in findings))

new_start = None
tmp = copy.deepcopy(BASE); shorten_mt(tmp)
new_start = str(tmp["data-mt.json"]["series"]["gdp_real"]["points"][0][0])
good = {"data-mt.json:gdp_real": {"start": new_start, "reason": "Source genuinely starts here; caption added."}}
findings, _, _ = run(shorten_mt, good)
expect("allow entry with start + reason passes", not findings)

short = {"data-mt.json:gdp_real": {"start": new_start, "reason": "ok"}}
findings, _, _ = run(shorten_mt, short)
expect("allow entry with too-short reason still fails", bool(findings))

wrong = {"data-mt.json:gdp_real": {"start": "1999-Q1", "reason": "A perfectly good long reason here."}}
findings, _, _ = run(shorten_mt, wrong)
expect("allow entry naming a different start still fails", bool(findings))

def shorten_more(new):
    shorten_mt(new)
    new["data-mt.json"]["series"]["gdp_real"]["points"] = new["data-mt.json"]["series"]["gdp_real"]["points"][8:]
findings, _, _ = run(shorten_more, good)
expect("a further regression beyond the allowed start fails", bool(findings))

def lengthen(new):
    s = new["data-mt.json"]["series"]["gdp_real"]["points"]
    s.insert(0, ["1990-Q1", s[0][1]])
findings, _, _ = run(lengthen)
expect("a series that starts EARLIER passes", not findings)

def freq_swap(new):   # quarterly -> annual starting later in the same year must still count as later/earlier correctly
    new["data-mt.json"]["series"]["gdp_real"]["points"][0][0] = "2000"
findings, _, _ = run(freq_swap)
expect("2000 (annual) vs 2000-Q1 is not a regression", not findings)

def drop_series(new):
    del new["data-ee.json"]["series"]["bond_yield_10y"]
findings, warns, _ = run(drop_series)
expect("a vanished series warns but does not fail", not findings and any("series gone" in w for w in warns))

print()
print("ALL PASS" if not fails else f"{len(fails)} FAILED")
sys.exit(1 if fails else 0)
