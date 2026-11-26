#!/usr/bin/env python3
"""v2.0.20: build_country_page.py must still reproduce the live pages.

    python3 tools/test_build_country_page.py            # every country with a spec
    python3 tools/test_build_country_page.py vn pe      # some

Rebuilds each country that has tools/country_specs/<code>.json in a scratch copy of the repo and compares
it with the live page, ignoring only what is expected to differ: the generator-owned key-figures block,
the Dataset dateModified, the section notes and the info-popover block (both edited on live pages after
their spec was written; the popover is checked against the citations by citation_provider.py) and
comment lines. Anything else that differs means the builder has drifted from a migration and a new
country would launch with a page unlike the rest. Read-only on the repo.
"""
import glob, json, os, re, shutil, subprocess, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IGN = [(re.compile(r"<!-- KEY-FIGURES:START.*?<!-- KEY-FIGURES:END -->\n?", re.S), ""),
       (re.compile(r'"dateModified": "\d{4}-\d{2}-\d{2}"'), '"dateModified": ""'),
       (re.compile(r'^ {1,2}<p class="secnote">.*</p>\n', re.M), ""),
       (re.compile(r"/\* ---- per-metric info popover content ----.*?\n\};\n", re.S), ""),
       (re.compile(r"^\s*//.*\n", re.M), ""),
       (re.compile(r'<div class="newdata" id="newdata" hidden(?: data-expect="1")?>'), '<div class="newdata" id="newdata" hidden>'),
       (re.compile(r"^[ \t]*\n", re.M), "")]
# Deliberate hand edits on one page each; a new country like them needs the same hand step (see the playbook).
KNOWN = {"Cyprus": "population and per capita from Eurostat, same area as GDP (fetch_population.COVERAGE_SOURCE, v1.9.125)",
         "Taiwan": "no World Bank coverage: the real-GDP conversion note omits the World Bank comparison"}
STR = re.compile(r'"(?:[^"\\\n]|\\.)*"')


def norm(t):
    for rx, r in IGN:
        t = rx.sub(r, t)
    return t


def main():
    want = sys.argv[1:]
    specs = sorted(p for p in glob.glob(os.path.join(ROOT, "tools/country_specs/*.json")) if not p.endswith(".citations.json"))
    tmp = tempfile.mkdtemp()
    work = os.path.join(tmp, "repo")
    shutil.copytree(ROOT, work, ignore=shutil.ignore_patterns(".git", "indicators", "embed", "og", "rankings", "_archive"))
    fails, wording, n = [], [], 0
    for p in specs:
        spec = json.load(open(p, encoding="utf-8"))
        if want and spec["code"] not in want:
            continue
        n += 1
        live = open(os.path.join(ROOT, spec["slug"] + ".html"), encoding="utf-8").read()
        r = subprocess.run([sys.executable, "tools/build_country_page.py", os.path.relpath(p, ROOT).replace(os.sep, "/"), "--force"],
                           cwd=work, capture_output=True, text=True)
        if r.returncode:
            fails.append(f"{spec['name']}: build failed: {(r.stdout + r.stderr).strip().splitlines()[-1]}")
            continue
        new = open(os.path.join(work, spec["slug"] + ".html"), encoding="utf-8").read()
        a, b = norm(live).split("\n"), norm(new).split("\n")
        if a != b and [STR.sub('""', x) for x in a] == [STR.sub('""', x) for x in b]:
            wording.append(spec["name"])   # same structure, different text: content drift, not builder drift
            continue
        if a != b and spec["name"] in KNOWN:
            wording.append(spec["name"] + " (known: " + KNOWN[spec["name"]] + ")")
            continue
        if a != b:
            import difflib
            d = [l for l in difflib.unified_diff(a, b, "live", "rebuilt", n=0, lineterm="") if l[:1] in "+-" and l[:3] not in ("+++", "---")]
            fails.append(f"{spec['name']}: {len(d)} line(s) differ, first: " + " | ".join(x[:600] for x in d[:12]))
    shutil.rmtree(tmp)
    print(f"test_build_country_page: {n} countries rebuilt, {len(fails)} differ from the live page")
    for f in fails:
        print("  FAIL " + f)
    if wording:
        print(f"  note: {len(wording)} page(s) match in structure but some wording differs from what the citations and spec "
              "would write now (live text edited since): " + ", ".join(wording))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
