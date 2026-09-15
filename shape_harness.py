#!/usr/bin/env python3
"""
Workstream 1 harness: reconstruct every series' shape at any commit and diff.

Shape = (n_points, first_period, last_period, freq, unit, label, source-ish)

Usage:
  python3 shape_harness.py snapshot <commit>        -> writes JSON snapshot to scratch
  python3 shape_harness.py diff <commitA> <commitB> -> prints changed series
  python3 shape_harness.py inventory <commit>       -> full (country,metric) table TSV
"""
import json, subprocess, sys, os

import os as _os
REPO = _os.environ.get("ATLAS_REPO") or _os.path.dirname(
    _os.path.dirname(_os.path.abspath(__file__)))
SCRATCH = _os.path.dirname(_os.path.abspath(__file__))

SKIP_SUFFIX = ("-trade-partners.json",)
SKIP_PREFIX = ("data-calendar-",)


def git(*args):
    r = subprocess.run(["git"] + list(args), capture_output=True, text=True, cwd=REPO)
    return r.stdout if r.returncode == 0 else None


def data_files(commit):
    out = git("ls-tree", "--name-only", commit)
    if out is None:
        return []
    files = []
    for ln in out.splitlines():
        if not (ln.startswith("data-") and ln.endswith(".json")):
            continue
        if any(ln.startswith(p) for p in SKIP_PREFIX):
            continue
        if any(ln.endswith(s) for s in SKIP_SUFFIX):
            continue
        if ln in ("data-metric-sources.json",):
            continue
        files.append(ln)
    return sorted(files)


def snapshot(commit):
    """{ 'data-tr.json': { 'cpi': {n, first, last, freq, unit, label} } }"""
    snap = {}
    for f in data_files(commit):
        raw = git("show", f"{commit}:{f}")
        if raw is None:
            continue
        try:
            d = json.loads(raw)
        except Exception:
            snap[f] = {"__parse_error__": True}
            continue
        series = d.get("series")
        if not isinstance(series, dict):
            continue
        entry = {}
        for k, v in series.items():
            if not isinstance(v, dict):
                continue
            pts = v.get("points")
            if not isinstance(pts, list) or not pts:
                entry[k] = {"n": 0, "first": None, "last": None,
                            "freq": v.get("freq"), "unit": v.get("unit"),
                            "label": v.get("label")}
                continue
            def per(p):
                return p[0] if isinstance(p, list) and p else None
            def val(p):
                return p[1] if isinstance(p, list) and len(p) > 1 else None
            entry[k] = {
                "n": len(pts),
                "first": per(pts[0]),
                "last": per(pts[-1]),
                "lastval": val(pts[-1]),
                "freq": v.get("freq"),
                "unit": v.get("unit"),
                "label": v.get("label"),
            }
        snap[f] = entry
        snap.setdefault("__updated__", {})[f] = d.get("updated")
    return snap


def diff(a, b, only_shape=True):
    sa, sb = snapshot(a), snapshot(b)
    rows = []
    files = sorted(set(sa) | set(sb))
    for f in files:
        if f.startswith("__"):
            continue
        ea, eb = sa.get(f, {}), sb.get(f, {})
        for k in sorted(set(ea) | set(eb)):
            ra, rb = ea.get(k), eb.get(k)
            if ra is None:
                rows.append((f, k, "ADDED", "", fmt(rb)))
                continue
            if rb is None:
                rows.append((f, k, "REMOVED", fmt(ra), ""))
                continue
            keys = ["n", "first", "freq", "unit", "label"] if only_shape else list(ra)
            changed = [x for x in keys if ra.get(x) != rb.get(x)]
            if changed:
                rows.append((f, k, ",".join(changed), fmt(ra), fmt(rb)))
    return rows


def fmt(r):
    if r is None:
        return ""
    return f"n={r['n']} {r['first']}..{r['last']} freq={r['freq']} unit={r['unit']} lbl={(r['label'] or '')[:48]}"


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "snapshot":
        c = sys.argv[2]
        s = snapshot(c)
        p = os.path.join(SCRATCH, f"snap_{c[:8]}.json")
        json.dump(s, open(p, "w"), indent=1)
        n = sum(len(v) for k, v in s.items() if not k.startswith("__"))
        print(f"{p}: {len([k for k in s if not k.startswith('__')])} files, {n} series")
    elif cmd == "diff":
        rows = diff(sys.argv[2], sys.argv[3])
        if not rows:
            print("no shape changes")
        for r in rows:
            print(f"{r[0]:22} {r[1]:22} [{r[2]}]\n    OLD {r[3]}\n    NEW {r[4]}")
        print(f"\n{len(rows)} changed series")
    elif cmd == "inventory":
        s = snapshot(sys.argv[2])
        print("file\tmetric\tn\tfirst\tlast\tlastval\tfreq\tunit\tlabel")
        for f in sorted(s):
            if f.startswith("__"):
                continue
            for k, r in sorted(s[f].items()):
                print(f"{f}\t{k}\t{r['n']}\t{r['first']}\t{r['last']}\t{r.get('lastval')}\t{r['freq']}\t{r['unit']}\t{r['label']}")
