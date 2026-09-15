#!/usr/bin/env python3
"""
Walk the full git history of every data-XX.json and record each series' shape
at every commit that touched the file. Output: scratch/history_shapes.json

  { "data-tr.json": [ {commit, date, series:{metric:{n,first,last,freq,label}}} ... ] }

Then `report` flags:
  - point count drops
  - frequency changes
  - start dates moving forward
  - label/provider moves
  - oscillation (a shape state that is left and later returned to)
"""
import json, subprocess, sys, os, collections

import os as _os
REPO = _os.environ.get("ATLAS_REPO") or _os.path.dirname(
    _os.path.dirname(_os.path.abspath(__file__)))
SCRATCH = _os.path.dirname(_os.path.abspath(__file__))
OUT = os.path.join(SCRATCH, "history_shapes.json")


def git(*args):
    r = subprocess.run(["git"] + list(args), capture_output=True, text=True, cwd=REPO)
    return r.stdout if r.returncode == 0 else None


def data_files():
    out = git("ls-tree", "--name-only", "HEAD") or ""
    files = []
    for ln in out.splitlines():
        if ln == "data.json":
            files.append(ln); continue
        if ln.startswith("data-") and ln.endswith(".json") \
           and not ln.startswith("data-calendar-") \
           and not ln.endswith("-trade-partners.json") \
           and ln != "data-metric-sources.json":
            files.append(ln)
    return sorted(files)


def shape_of(raw):
    try:
        d = json.loads(raw)
    except Exception:
        return None
    s = d.get("series")
    if not isinstance(s, dict):
        return None
    out = {}
    for k, v in s.items():
        if not isinstance(v, dict):
            continue
        pts = v.get("points")
        if not isinstance(pts, list):
            pts = []
        first = pts[0][0] if pts and isinstance(pts[0], list) else None
        last = pts[-1][0] if pts and isinstance(pts[-1], list) else None
        out[k] = {"n": len(pts), "first": first, "last": last,
                  "freq": v.get("freq"), "label": v.get("label")}
    return {"series": out, "updated": d.get("updated")}


def walk():
    res = {}
    files = data_files()
    for i, f in enumerate(files, 1):
        log = git("log", "--format=%H %cI", "--", f) or ""
        entries = []
        lines = log.splitlines()
        for ln in lines:
            sha, date = ln.split(" ", 1)
            raw = git("show", f"{sha}:{f}")
            if raw is None:
                continue
            sh = shape_of(raw)
            if sh is None:
                continue
            entries.append({"commit": sha[:8], "date": date,
                            "series": sh["series"], "updated": sh["updated"]})
        entries.reverse()  # oldest first
        res[f] = entries
        print(f"[{i}/{len(files)}] {f}: {len(entries)} revisions", flush=True)
    json.dump(res, open(OUT, "w"))
    print("wrote", OUT)


def report():
    res = json.load(open(OUT))
    changes = []
    for f, entries in res.items():
        prev = None
        states = collections.defaultdict(list)  # metric -> list of state tuples
        for e in entries:
            cur = e["series"]
            for k, r in cur.items():
                st = (r["n"], r["first"], r["freq"], r["label"])
                if not states[k] or states[k][-1][0] != st:
                    states[k].append((st, e["commit"], e["date"]))
            if prev is not None:
                for k in sorted(set(prev) | set(cur)):
                    a, b = prev.get(k), cur.get(k)
                    if a is None:
                        changes.append((f, k, e["commit"], e["date"], "ADDED", "", desc(b)))
                        continue
                    if b is None:
                        changes.append((f, k, e["commit"], e["date"], "REMOVED", desc(a), ""))
                        continue
                    kinds = []
                    if b["n"] < a["n"]:
                        kinds.append(f"POINTS_DROPPED({a['n']}->{b['n']})")
                    if b["freq"] != a["freq"]:
                        kinds.append(f"FREQ({a['freq']}->{b['freq']})")
                    if a["first"] and b["first"] and str(b["first"]) > str(a["first"]):
                        kinds.append(f"START_FORWARD({a['first']}->{b['first']})")
                    if b["label"] != a["label"]:
                        kinds.append("LABEL")
                    if kinds:
                        changes.append((f, k, e["commit"], e["date"],
                                        ";".join(kinds), desc(a), desc(b)))
            prev = cur
        # oscillation: same state visited more than once non-consecutively
        for k, seq in states.items():
            seen = collections.Counter(s[0] for s in seq)
            for st, c in seen.items():
                if c > 1:
                    changes.append((f, k, seq[-1][1], seq[-1][2],
                                    f"OSCILLATION(state seen {c}x across {len(seq)} states)",
                                    str(st), ""))
    for c in changes:
        print("\t".join(str(x) for x in c))
    print(f"\n{len(changes)} shape events", file=sys.stderr)


def desc(r):
    if r is None:
        return ""
    return f"n={r['n']} {r['first']}..{r['last']} {r['freq']} {(r['label'] or '')[:40]}"


if __name__ == "__main__":
    (walk if sys.argv[1] == "walk" else report)()
