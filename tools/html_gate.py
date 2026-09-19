#!/usr/bin/env python3
"""
Structural gate over EVERY published HTML page: root, indicators/ and embed/.

Why this exists as a tool. The gate was previously run ad hoc against the root
pages only, and reported "43 pages, 307 JS blocks, 66 ld+json, 0 failures".
Every one of those numbers was true and every one covered a seventh of the
site: the real totals are 299 pages, 1,235 inline blocks and 194 ld+json
blocks. Generated directories are where the worst defect of the audit lived
(128 OG cards nothing regenerated, publishing projections as outturns) and
where 33 pages were found emitting invalid schema.org temporalCoverage, so
running a gate that silently skips them is worse than not running one.

Every count printed is "examined", not just "failed", so a run that covers
less than it should is visible in the numbers rather than hidden behind a
clean pass.

    python3 tools/html_gate.py
"""
import json
import os
import re
import subprocess
import sys
import tempfile

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
        "meta", "param", "source", "track", "wbr"}
# Elements the HTML parser is allowed to close implicitly. Treating an unclosed
# <p> or <li> as an imbalance would make the gate cry wolf on valid pages.
OPTIONAL_END = {"p", "li", "td", "th", "tr", "thead", "tbody", "tfoot",
                "option", "dt", "dd", "colgroup", "caption", "rt", "rp"}

TAG_RE = re.compile(r"<(/?)([a-zA-Z][a-zA-Z0-9]*)\b[^>]*?(/?)>")
SCRIPT_RE = re.compile(r"<script\b([^>]*)>([\s\S]*?)</script>", re.I)
COMMENT_RE = re.compile(r"<!--[\s\S]*?-->")


def find_repo(start):
    d = start
    while True:
        if (os.path.exists(os.path.join(d, "compare.html"))
                and os.path.exists(os.path.join(d, "data-metric-sources.json"))):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            raise SystemExit("could not locate the clone from " + start
                             + "; set ATLAS_REPO to the clone root")
        d = parent


REPO = os.environ.get("ATLAS_REPO") or find_repo(
    os.path.dirname(os.path.abspath(__file__)))


def pages():
    out = [f for f in sorted(os.listdir(REPO)) if f.endswith(".html")]
    for sub in ("indicators", "embed"):
        d = os.path.join(REPO, sub)
        if os.path.isdir(d):
            out += [os.path.join(sub, f) for f in sorted(os.listdir(d))
                    if f.endswith(".html")]
    return out


def strip_non_markup(html):
    """Remove comments, script and style bodies before counting tags."""
    html = COMMENT_RE.sub("", html)
    html = re.sub(r"<script\b[^>]*>[\s\S]*?</script>", "<script></script>",
                  html, flags=re.I)
    html = re.sub(r"<style\b[^>]*>[\s\S]*?</style>", "<style></style>",
                  html, flags=re.I)
    return html


def tag_balance(html):
    stack = []
    for m in TAG_RE.finditer(strip_non_markup(html)):
        closing, name, selfclose = m.group(1), m.group(2).lower(), m.group(3)
        if name in VOID or selfclose:
            continue
        if not closing:
            stack.append(name)
        else:
            while stack and stack[-1] in OPTIONAL_END and stack[-1] != name:
                stack.pop()
            if not stack:
                return f"</{name}> with nothing open"
            if stack[-1] != name:
                return f"</{name}> closes <{stack[-1]}>"
            stack.pop()
    leftover = [t for t in stack if t not in OPTIONAL_END]
    return f"unclosed <{leftover[0]}>" if leftover else None


def classify(attrs):
    if re.search(r"\bsrc\s*=", attrs, re.I):
        return "external"
    m = re.search(r'\btype\s*=\s*["\']?([^"\'\s>]+)', attrs, re.I)
    if m and m.group(1).lower() == "application/ld+json":
        return "ldjson"
    if m and m.group(1).lower() not in ("text/javascript", "module",
                                        "application/javascript"):
        return "other"
    return "inline"


# A function defined twice in one page is not a syntax error and runs fine --
# JavaScript simply keeps the later definition -- so neither tag balance nor
# the syntax check can see it. That is how a shared helper shipped twice on 31
# country pages: correct behaviour, ~50 lines of dead duplicate, every gate
# green. A page has no legitimate reason to declare the same top-level
# function name twice.
FUNC_RE = re.compile(r"^function\s+([A-Za-z_$][\w$]*)\s*\(", re.M)


def duplicate_functions(html):
    """[(name, count)] for top-level functions declared more than once in a page."""
    seen = {}
    for m in SCRIPT_RE.finditer(html):
        if classify(m.group(1)) != "inline":
            continue
        for f in FUNC_RE.finditer(m.group(2)):
            seen[f.group(1)] = seen.get(f.group(1), 0) + 1
    return sorted((n, c) for n, c in seen.items() if c > 1)


def main():
    files = pages()
    counts = dict(pages=0, inline=0, external=0, ldjson=0, other=0)
    failures = []
    blocks = []  # (label, source) for one batched node run

    for rel in files:
        html = open(os.path.join(REPO, rel), encoding="utf-8").read()
        counts["pages"] += 1
        bad = tag_balance(html)
        if bad:
            failures.append((rel, "tag balance: " + bad))
        for name, n in duplicate_functions(html):
            failures.append((rel, f"duplicate function: {name} declared {n} times"))
        for i, m in enumerate(SCRIPT_RE.finditer(html)):
            kind = classify(m.group(1))
            counts[kind] += 1
            if kind == "inline":
                blocks.append((f"{rel}#{i}", m.group(2)))
            elif kind == "ldjson":
                try:
                    json.loads(m.group(2))
                except Exception as exc:
                    failures.append((rel, f"ld+json block {i}: {exc}"))

    # One node process for every inline block. Per-block subprocesses would be
    # ~1,200 spawns; vm.Script gives the same syntax check as node --check.
    js_failures = []
    if blocks:
        with tempfile.TemporaryDirectory() as td:
            payload = os.path.join(td, "blocks.json")
            with open(payload, "w", encoding="utf-8") as fh:
                json.dump([{"label": a, "src": b} for a, b in blocks], fh)
            runner = os.path.join(td, "run.js")
            with open(runner, "w", encoding="utf-8") as fh:
                fh.write(
                    "const vm=require('vm'),fs=require('fs');\n"
                    "const bs=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));\n"
                    "const out=[];\n"
                    "for(const b of bs){try{new vm.Script(b.src,{filename:b.label});}\n"
                    "catch(e){out.push([b.label,e.message]);}}\n"
                    "console.log(JSON.stringify(out));\n")
            res = subprocess.run(["node", runner, payload],
                                 capture_output=True, text=True)
            if res.returncode != 0:
                raise SystemExit("node runner failed: " + res.stderr.strip())
            js_failures = json.loads(res.stdout)

    print(f"  pages examined          {counts['pages']}")
    print(f"  inline JS blocks        {counts['inline']}")
    print(f"  ld+json blocks          {counts['ldjson']}")
    print(f"  external scripts        {counts['external']} (not syntax checked)")
    if counts["other"]:
        print(f"  other script types      {counts['other']} (not syntax checked)")
    print(f"  tag balance failures    "
          f"{len([f for f in failures if 'tag balance' in f[1]])}")
    print(f"  ld+json parse failures  "
          f"{len([f for f in failures if 'ld+json' in f[1]])}")
    print(f"  inline JS syntax errors {len(js_failures)}")
    print(f"  duplicate functions     "
          f"{len([f for f in failures if 'duplicate function' in f[1]])}")
    for rel, msg in failures:
        print(f"    FAIL {rel}: {msg}")
    for label, msg in js_failures:
        print(f"    FAIL {label}: {msg}")
    return 1 if (failures or js_failures) else 0


if __name__ == "__main__":
    sys.exit(main())
