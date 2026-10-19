#!/usr/bin/env python3
"""History-start regression gate.

Compares the start date of every series in every data-XX.json with the same
file at a baseline git ref (default: origin/main, falling back to HEAD). It
fails when a series now starts LATER than it did, unless tools/history_depth_allow.json
holds an entry for that exact series that
  - names the new start it is allowing, and
  - gives a reason of at least 15 characters.

An allow entry only covers the start it names, so a further regression on the
same series fails again. Series that disappear are reported as warnings (they
come and go with rotation) but do not fail the run.

Usage:
  python3 tools/history_depth_gate.py                 # worktree vs origin/main
  python3 tools/history_depth_gate.py --ref HEAD      # worktree vs another ref
  python3 tools/history_depth_gate.py --files data-mt.json data-ee.json

Exit 0 = clean, 1 = at least one unallowed later start.

Allow-list format (tools/history_depth_allow.json):
  { "data-ee.json:bond_yield_10y": {"start": "2020-06", "reason": "..."} }
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
ALLOW_PATH = os.path.join(HERE, "history_depth_allow.json")
MIN_REASON = 15


def start_key(label):
    """Sortable key for 'YYYY', 'YYYY-Qn' or 'YYYY-MM'. Later start = larger key."""
    s = str(label)
    m = re.fullmatch(r"(\d{4})(?:-Q([1-4])|-(\d{2}))?", s)
    if not m:
        raise ValueError(f"unrecognised date label {s!r}")
    year = int(m.group(1))
    if m.group(2):
        return (year, (int(m.group(2)) - 1) * 3 + 1)
    if m.group(3):
        return (year, int(m.group(3)))
    return (year, 1)


def starts(doc):
    out = {}
    for name, s in (doc.get("series") or {}).items():
        if isinstance(s, dict) and s.get("points"):
            out[name] = str(s["points"][0][0])
    return out


def git_show(ref, path):
    r = subprocess.run(["git", "show", f"{ref}:{path}"], capture_output=True,
                       text=True, cwd=REPO)
    return json.loads(r.stdout) if r.returncode == 0 else None


def resolve_ref(ref):
    if ref:
        return ref
    ok = subprocess.run(["git", "rev-parse", "--verify", "-q", "origin/main"],
                        capture_output=True, cwd=REPO).returncode == 0
    return "origin/main" if ok else "HEAD"


def load_allow(path):
    if not os.path.exists(path):
        return {}
    return json.load(open(path, encoding="utf-8"))


def check(files, ref, allow, loader=None, base_loader=None):
    """Returns (findings, warnings, compared). Loaders are injectable for tests."""
    loader = loader or (lambda f: json.load(open(os.path.join(REPO, f), encoding="utf-8")))
    base_loader = base_loader or (lambda f: git_show(ref, f))
    findings, warnings, compared = [], [], 0
    for f in files:
        new_doc, old_doc = loader(f), base_loader(f)
        if old_doc is None:
            warnings.append(f"{f}: not present at {ref} (new file, nothing to compare)")
            continue
        new, old = starts(new_doc), starts(old_doc)
        for name, old_start in old.items():
            if name not in new:
                warnings.append(f"{f}:{name}: series gone (was {old_start})")
                continue
            compared += 1
            if start_key(new[name]) > start_key(old_start):
                key = f"{f}:{name}"
                entry = allow.get(key)
                reason = (entry or {}).get("reason", "") if isinstance(entry, dict) else ""
                if (entry and entry.get("start") == new[name]
                        and len(reason.strip()) >= MIN_REASON):
                    continue
                why = ""
                if entry:
                    why = (" (allow entry ignored: start mismatch)"
                           if entry.get("start") != new[name]
                           else " (allow entry ignored: reason too short)")
                findings.append(f"{key}: start moved later {old_start} -> {new[name]}{why}")
    return findings, warnings, compared


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref")
    ap.add_argument("--files", nargs="*")
    ap.add_argument("--allow", default=ALLOW_PATH)
    a = ap.parse_args(argv)
    ref = resolve_ref(a.ref)
    files = a.files or sorted(os.path.basename(p) for p in glob.glob(os.path.join(REPO, "data-??.json")))
    allow = load_allow(a.allow)
    findings, warnings, compared = check(files, ref, allow)
    for w in warnings:
        print("WARN  ", w)
    for x in findings:
        print("FAIL  ", x)
    print(f"history_depth_gate: baseline {ref}; {len(files)} files, {compared} series compared, "
          f"{len(findings)} later-start findings, {len(warnings)} warnings, {len(allow)} allow entries")
    if compared == 0:
        print("FAIL   nothing was compared; a gate that compares nothing is not evidence")
        return 1
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
