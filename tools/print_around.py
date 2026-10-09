"""Print a series' values around given periods, for checking audit FAILs.

    python3 tools/print_around.py data-hu.json policy_rate 2022-06 2022-07
    python3 tools/print_around.py data-ro.json unemployment --outside 3 9

Read-only. Shows 3 periods either side of each period named; with
--outside LO HI, lists every value outside LO..HI instead.
"""
import json
import sys

d = json.load(open(sys.argv[1]))
key = sys.argv[2]
pts = d["series"][key]["points"]
print(f"{sys.argv[1]} {key}: {len(pts)} points, {pts[0][0]}..{pts[-1][0]}; label: {d['series'][key]['label']}")
if "--outside" in sys.argv:
    i = sys.argv.index("--outside")
    lo, hi = float(sys.argv[i + 1]), float(sys.argv[i + 2])
    out = [(p, v) for p, v in pts if not lo <= v <= hi]
    print(f"  outside {lo}..{hi}: {len(out)}")
    for p, v in out:
        print(f"    {p}  {v}")
else:
    idx = {p: n for n, (p, _) in enumerate(pts)}
    for want in sys.argv[3:]:
        n = idx.get(want)
        if n is None:
            print(f"  {want}: not in series")
            continue
        print(f"  around {want}:")
        for p, v in pts[max(0, n - 3): n + 4]:
            print(f"    {p}  {v}" + ("   <--" if p == want else ""))
