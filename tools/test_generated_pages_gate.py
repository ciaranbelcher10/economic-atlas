#!/usr/bin/env python3
"""Tests for tools/generated_pages_gate.py (v1.9.13).

A gate that has never been seen to fail proves nothing, so this feeds it deliberately broken generators and
doctored data and requires, for each, a non-zero exit and a failure message naming the right problem. A crash
does not count as a catch: the gate must exit 1 with a FAIL line, not a traceback.

  - positive control: the repo's own generator passes;
  - 15 generator mutations, one per class of problem the gate exists to catch;
  - doctored data: a rolling UK range that crosses a year boundary, and a UK series whose previous month
    differs from three months ago (so the ranking's comparison basis shows). The repo's generator must pass
    both; the generator with the v1.9.13 ranking fix reverted must fail the second.

Each gate run takes about six seconds. Run from the repo root:  python3 tools/test_generated_pages_gate.py
"""
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GATE = ROOT / "tools" / "generated_pages_gate.py"
GEN = (ROOT / "generate_indicator_pages.py").read_text(encoding="utf-8")
fails = []
ran = 0


def check(cond, msg):
    if not cond:
        fails.append(msg)
        print("FAIL", msg)


def run_gate(gen_text=None, repo=None):
    tmp = Path(tempfile.mkdtemp(prefix="tgg_"))
    args = [sys.executable, str(GATE)]
    if gen_text is not None:
        g = tmp / "generate_indicator_pages.py"
        g.write_text(gen_text, encoding="utf-8")
        args += ["--generator", str(g)]
    if repo is not None:
        args += ["--repo", str(repo)]
    r = subprocess.run(args, capture_output=True, text=True, timeout=300, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    shutil.rmtree(tmp, ignore_errors=True)
    global ran
    ran += 1
    return r


def mutate(old, new):
    assert GEN.count(old) == 1, f"anchor not unique ({GEN.count(old)}): {old[:70]!r}"
    return GEN.replace(old, new)


def caught(name, r, expect):
    out = r.stdout + r.stderr
    fl = [ln for ln in out.splitlines() if ln.startswith("FAIL")]
    match = (lambda ln: expect.search(ln)) if hasattr(expect, "search") else (lambda ln: expect in ln)
    ok = r.returncode == 1 and "Traceback" not in r.stderr and any(match(ln) for ln in fl)
    check(ok, f"{name}: expected exit 1 with a FAIL line containing {expect!r}; got rc={r.returncode}, "
              f"{len(fl)} FAIL lines, first: {fl[0][:150] if fl else out[-200:]!r}")


def repo_copy(edit):
    d = Path(tempfile.mkdtemp(prefix="tgr_"))
    for pat in ("*.json", "*.html", "*.py"):
        for f in glob.glob(str(ROOT / pat)):
            shutil.copy(f, d / os.path.basename(f))
    # the methodology page links to the site's css, js and images: link them in so the gate's link check can resolve them
    for f in ROOT.iterdir():
        if f.is_file() and not (d / f.name).exists():
            os.symlink(f, d / f.name)
    edit(d)
    return d


# the v1.9.13 ranking fix, reverted (the generator as it was in v1.9.12)
FIX_COMPARE = re.compile(r'            if is_rolling3m\(country, key\) and freq == "months" and len\(pts\) >= 4:\n(?:                #.*\n)+'
                         r'                prev_p, prev = pts\[-4\]\n')
FIX_TIP_NEW = ('(fmt_rolling3m if is_rolling3m(r["country"], r.get("key")) and r.get("freq") == "months" '
               'else fmt_period_label)(r.get("prev_period", ""))')
FIX_TIP_OLD = 'fmt_period_label(r.get("prev_period", ""))'
assert FIX_COMPARE.search(GEN) and GEN.count(FIX_TIP_NEW) == 1, "the v1.9.13 ranking fix is not in generate_indicator_pages.py"
V1912 = FIX_COMPARE.sub("", GEN, count=1).replace(FIX_TIP_NEW, FIX_TIP_OLD)

# ---------------------------------------------------------------- positive control
r = run_gate()
check(r.returncode == 0 and "ok (0 failures)" in r.stdout, f"positive control: the repo's generator must pass: {r.stdout[-400:]} {r.stderr[-200:]}")
check("976 indicator pages" in r.stdout or re.search(r"\d+ indicator pages", r.stdout), "positive control: no page counts reported")

# ---------------------------------------------------------------- generator mutations
VS = 'vs {esc(plab(prev_p))}</span></p>'
MUTS = [
    ("UK rolling labels dropped", mutate('ROLLING_3M_MID = {("UK", "unemployment"), ("UK", "employment"), ("UK", "inactivity"), ("UK", "unemployment_1624")}',
                                         'ROLLING_3M_MID = set()'), "title says"),
    ("ranking tooltip back to a plain month (v1.9.12)", GEN.replace(FIX_TIP_NEW, FIX_TIP_OLD), "UK change tooltip"),
    ("hourly claim in visible copy", mutate(VS, 'vs {esc(plab(prev_p))} (checked hourly)</span></p>'), "hourly claim"),
    ("em dash in visible copy", mutate(VS, 'vs {esc(plab(prev_p))} \u2014 x</span></p>'), "em dash"),
    ("double hyphen in visible copy", mutate(VS, 'vs {esc(plab(prev_p))} -- x</span></p>'), "double hyphen"),
    ("'illustrative' in visible copy", mutate(VS, 'vs {esc(plab(prev_p))} (illustrative)</span></p>'), "illustrative"),
    ("NaN in visible copy", mutate(VS, 'vs {esc(plab(prev_p))} NaN</span></p>'), "NaN/undefined/Infinity"),
    ("embedded series loses its last point", mutate("points=pts, realPoints=real_pts", "points=pts[:-1], realPoints=real_pts"), "differs from"),
    ("canonical link wrong", mutate('href="{canonical}">', 'href="{canonical}/">'), "canonical is"),
    ("JSON-LD truncated", mutate("\n{jsonld}\n</script>", "\n{jsonld[:-5]}\n</script>"), "JSON-LD does not parse"),
    ("rankings missing from the sitemap", mutate("        if u not in seen:\n            seen.add(u)\n",
                                                 '        if u not in seen and "/rankings/" not in u:\n            seen.add(u)\n'), "sitemap lacks rankings/"),
    ("embed shows a plain month for the UK", mutate('latest_period=esc((fmt_rolling3m if is_rolling3m(country, entry["key"]) else fmt_period_label)(lp[0]))',
                                                    "latest_period=esc(fmt_period_label(lp[0]))"), "does not show"),
    ("summary line overstates the embeds", mutate('{generated} embeds and', '{generated + 1} embeds and'), "summary says"),
    ("generator crashes", mutate("def main():\n", "def main():\n    raise SystemExit(3)\n"), "generator exited 3"),
    ("generator prints no summary", mutate('print(f"Generated {generated} indicator pages', 'print(f"Built {generated} indicator pages'), "printed no"),
]
for name, text, expect in MUTS:
    caught(name, run_gate(text), expect)

# ---------------------------------------------------------------- doctored data
def cross_year(d):
    p = d / "data-uk.json"
    j = json.loads(p.read_text(encoding="utf-8"))
    pts = j["series"]["unemployment"]["points"]
    # the latest rolling value is now centred on December: November 2026 to January 2027
    pts.append(["2026-08", 4.8]), pts.append(["2026-09", 4.8]), pts.append(["2026-10", 4.7]), pts.append(["2026-11", 4.7]), pts.append(["2026-12", 4.6])
    p.write_text(json.dumps(j), encoding="utf-8")


def basis_shows(d):
    p = d / "data-uk.json"
    j = json.loads(p.read_text(encoding="utf-8"))
    pts = j["series"]["unemployment"]["points"]
    assert pts[-2][0] == "2026-06" and pts[-4][0] == "2026-04", f"data moved on: {pts[-4:]}"
    pts[-2][1] = round(pts[-4][1] + 0.7, 1)       # the previous month now differs from three months ago
    p.write_text(json.dumps(j), encoding="utf-8")


for name, edit in (("cross-year rolling range", cross_year), ("ranking comparison basis", basis_shows)):
    d = repo_copy(edit)
    try:
        r = run_gate(repo=d)
        check(r.returncode == 0, f"{name}: the repo's generator must pass doctored data: {r.stdout[-300:]} {r.stderr[-200:]}")
        if name == "ranking comparison basis":
            # the VALUE message ("UK change -0.6, expected -0.2"), not the tooltip one ("UK change tooltip is ...")
            caught(f"{name} with the ranking fix reverted", run_gate(V1912, repo=d), re.compile(r"UK change -?\d"))
        else:
            wrong_year = mutate("    ey, em = (y, m + 1) if m < 12 else (y + 1, 1)\n", "    ey, em = (y, m + 1) if m < 12 else (y, 1)\n")
            caught(f"{name} with a wrong year rollover", run_gate(wrong_year, repo=d), "title says")
    finally:
        shutil.rmtree(d, ignore_errors=True)

print(f"test_generated_pages_gate: {'FAILED' if fails else 'ok'} ({len(fails)} failures, {ran} gate runs)")
sys.exit(1 if fails else 0)
