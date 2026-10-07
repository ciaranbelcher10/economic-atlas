"""Lint (v1.7.25): derived rates are stored at 4 decimals, never 2.

Storing a rate at 2 decimals and showing it at 1 rounds twice. Portugal's
Aug 2026 HICP was 3.5552%: stored as 3.55 it showed 3.5% (3.55 is
3.5499... in binary) against the official 3.6%, and Q1 2026 GDP growth,
0.247%, showed 0.3% against Eurostat's 0.2%. Pages round once, from the
stored value, so the stored value must keep the precision.

    python3 tools/test_rate_precision.py
"""
import glob, os, re, sys
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
BAD = re.compile(r"round\(\([^()]*/[^()]*- 1\) \* 100, [0-3]\)")
hits = []
for f in sorted(glob.glob(os.path.join(ROOT, "*.py"))):
    for n, line in enumerate(open(f, encoding="utf-8"), 1):
        if BAD.search(line):
            hits.append(f"{os.path.basename(f)}:{n}: {line.strip()}")
for h in hits:
    print("FAIL", h)
# the pattern must still catch the old form (planted fault)
assert BAD.search("out.append([per, round((val / base - 1) * 100, 2)])")
assert not BAD.search("out.append([per, round((val / base - 1) * 100, 4)])")
print(f"rate precision: {len(hits)} rate(s) stored below 4 decimals")
sys.exit(1 if hits else 0)
