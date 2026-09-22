#!/usr/bin/env python3
"""Writes every figure the indicator/ranking pages print, formatted by the
Python fmt_num(), to a JSON file that tools/test_indicator_fmt.js re-formats
with the browser's fmtNum() and diffs. Also asserts the display rules."""
import json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import generate_indicator_pages as g

cases, problems = [], []
src = g.load_json("data-metric-sources.json")
cat, _, _, pages = g.build_all(src)
for c, info in cat.items():
    for e in info["catalogue"]:
        pts = e["pts"]
        for mode in ("value", "tip", "axis", "delta", "cell"):
            for p in pts[-40:]:
                v = p[1] if mode != "delta" else p[1] - pts[0][1]
                out = g.fmt_num(v, e["unit"], e["key"], c, mode)
                cases.append([v, e["unit"], e["key"], c, mode, out])
                # display rules
                k = g.unit_kind(e["unit"])
                if k == "pct" and mode in ("value", "tip", "cell") and not out.endswith("%"): problems.append((c, e["key"], out))
                if k == "pct" and mode == "delta" and not out.endswith("pp"): problems.append((c, e["key"], out))
                if k == "cur" and mode != "delta" and not re.search(r"(tn|bn|m|k|\d)$", out): problems.append((c, e["key"], out))
                if k == "cur" and re.search(r"\d{4,}", out.replace(",", "")) and not re.search(r"\d{1,3}(,\d{3})+", out): problems.append((c, e["key"], "unscaled " + out))
                if "nan" in out.lower() or "undefined" in out: problems.append((c, e["key"], out))
                if k == "cur" and not re.match(r"^[\u2212+]?([^\d]+)\d", out) and abs(v) > 0: problems.append((c, e["key"], "no symbol " + out))
json.dump(cases, open("/tmp/fmt_cases.json", "w"), ensure_ascii=False)
print(f"{len(cases)} cases written; {len(problems)} rule violations")
for p in problems[:20]: print("  ", p)
sys.exit(1 if problems else 0)
