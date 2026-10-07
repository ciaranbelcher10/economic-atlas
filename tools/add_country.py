#!/usr/bin/env python3
"""Wire a new country into every shared surface of the site from one spec.

    python3 tools/add_country.py tools/country_specs/my.json            # apply
    python3 tools/add_country.py tools/country_specs/my.json --check    # report only

Written after the China launch (v1.7.0), where the shared-surface edits were
done by hand across ~45 files and three surfaces were found stale only by
accident (index.html map missing Thailand, Dashboard's ISO_OF frozen at 18
countries, 8 mini-maps highlighting the wrong country). Every edit here is
idempotent: a surface that already carries the country is left alone, so the
script can be re-run safely and doubles as a repair tool.

What it does NOT do (judgement calls, kept manual on purpose):
  * the fetch script and the audit (fetch_<code>.py, tools/audit_<code>.py)
  * the citation text: data-metric-sources.json["<Name>"] must be written,
    and agree with the fetch script's labels, BEFORE this runs (checked)
  * the country page itself: tools/build_country_page.py, after this
  * anything under .github/workflows/: the script prints the YAML to paste

Never deletes anything. Never writes generated output (indicators/ embed/
og/ rankings/ sitemap.xml). tools/country_surfaces_gate.py checks the result.
"""
from __future__ import annotations

import glob, json, math, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGIONS = ("Europe", "Scandinavia", "North America", "South America", "Asia", "Oceania", "Middle East", "Africa")
CHANGES: list[str] = []
CHECK_ONLY = "--check" in sys.argv


def die(msg):
    sys.exit(f"add_country: {msg}")


def load_spec(path):
    s = json.load(open(path, encoding="utf-8"))
    need = ("name", "slug", "code", "iso2", "isonum", "region", "currency")
    miss = [k for k in need if not s.get(k)]
    if miss:
        die(f"spec missing {miss}")
    if s["region"] not in REGIONS:
        die(f"region must be one of {REGIONS}")
    if not re.fullmatch(r"\d{3}", s["isonum"]):
        die("isonum must be the 3-digit ISO numeric code as a string, e.g. \"458\"")
    s.setdefault("glyph", "")
    s.setdefault("fx", {})
    s.setdefault("policy_rate_key", None)
    s["datafile"] = f"data-{s['code']}.json"
    s["setname"] = s["iso2"].upper() + "c"
    return s


def rd(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def wr(rel, old, new, what):
    if old == new:
        return
    CHANGES.append(f"{rel}: {what}")
    if not CHECK_ONLY:
        (ROOT / rel).write_text(new, encoding="utf-8")


def js_key(name):
    return name if re.fullmatch(r"[A-Za-z_]\w*", name) else json.dumps(name)


def obj_span(text, varname):
    """(start, end) of the {...} or [...] literal assigned to varname."""
    m = re.search(r"(?:var|const|let)\s+" + re.escape(varname) + r"\s*=\s*([\{\[])", text)
    if not m:
        die(f"cannot find object {varname}")
    o, c = ("{", "}") if m.group(1) == "{" else ("[", "]")
    i = m.end(1) - 1
    d = 0
    for j in range(i, len(text)):
        if text[j] == o:
            d += 1
        elif text[j] == c:
            d -= 1
            if d == 0:
                return i, j + 1
    die(f"unbalanced {varname}")


def add_entry(text, varname, key, value_js):
    """Append `key: value` to a JS object literal, unless key is present."""
    a, b = obj_span(text, varname)
    body = text[a:b]
    if re.search(r"(?<![\w\"])" + re.escape(js_key(key)) + r"\s*:", body):
        return text
    inner = body[1:-1].rstrip()
    sep = "" if inner.endswith(",") else ","
    tail = body[1:-1][len(inner):]
    new = "{" + inner + sep + " " + js_key(key) + ":" + value_js + tail + "}"
    return text[:a] + new + text[b:]


# ------------------------------------------------------------------ steps
def step_generator(s):
    rel = "generate_indicator_pages.py"
    t = rd(rel)
    new = t
    if f'"{s["name"]}":' not in t.split("COUNTRIES", 1)[1][:4000]:
        m = re.search(r"COUNTRIES\s*=\s*\{\n", new)
        line = f'    "{s["name"]}":{" " * max(1, 14 - len(s["name"]))}("{s["code"]}", "{s["slug"]}", "{s["iso2"]}", "{s["region"]}"),\n'
        new = new[:m.end()] + line + new[m.end():]
    new = nav_insert(new, s, prefix="../")
    wr(rel, t, new, "COUNTRIES + nav template")


def nav_insert(text, s, prefix=""):
    """Insert the country into its region column of the nav, alphabetically."""
    head = f'<p class="dhead">{s["region"]}</p>\n'
    if f'href="{prefix}{s["slug"]}"' in text or head not in text:
        return text
    i = text.index(head) + len(head)
    j = i
    names = []
    while True:
        m = re.match(r' <a href="' + re.escape(prefix) + r'([a-z]+)"[^>]*>([^<]+)</a>\n', text[j:])
        if not m:
            break
        names.append((m.group(2), j))
        j += m.end()
    pos = j
    for nm, at in names:
        if nm.lower() > s["name"].lower():
            pos = at
            break
    link = f' <a href="{prefix}{s["slug"]}">{s["name"]}</a>\n'
    return text[:pos] + link + text[pos:]


def step_nav(s):
    for rel in sorted(glob.glob(str(ROOT / "*.html"))):
        rel = Path(rel).name
        if rel == "404.html":
            continue
        t = rd(rel)
        wr(rel, t, nav_insert(t, s), "nav")


def step_minimaps(s):
    sn, num, slug = s["setname"], s["isonum"], s["slug"]
    for rel in sorted(glob.glob(str(ROOT / "*.html"))):
        rel = Path(rel).name
        t = rd(rel)
        new = t
        if rel == "index.html":
            if f'"{num}"]);' not in new.split("function", 1)[0] and f"const {sn} " not in new:
                decl = list(re.finditer(r"const \w+ = new Set\(\[\"\d{3}\"(?:, ?\"\d{3}\")*\]\);\n", new))
                if decl:
                    k = decl[-1].end()
                    new = new[:k] + f'const {sn} = new Set(["{num}"]);\n' + new[k:]
            if f'"{slug}" :' not in new and f'? "{slug}"' not in new:
                new = re.sub(r'(\? "[a-z]+") : null;', lambda m: f'{m.group(1)} : {sn}.has(id) ? "{slug}" : null;', new, count=1)
        else:
            if "CURRENT=new Set(" not in new:
                continue
            if f"{sn}=new Set(" not in new:
                hits = [m for m in re.finditer(r"(?<![A-Za-z])([A-Z]{2}c?)=new Set\(\[\"\d{3}\"(?:,\"\d{3}\")*\]\);", new)]
                if not hits:
                    continue
                h = hits[-1]
                new = new[:h.end() - 1] + f', {sn}=new Set(["{num}"])' + new[h.end() - 1:]
            if f'?"{slug}"' not in new:
                new = re.sub(r'(\.has\(id\)\?"[a-z]+"):null', lambda m: f'{m.group(1)}:{sn}.has(id)?"{slug}":null', new, count=1)
        wr(rel, t, new, "mini-map")


def palette_pick(compare_text):
    pal = re.findall(r"#[0-9A-F]{6}", compare_text[slice(*obj_span(compare_text, "COMPARE_PALETTE"))])
    used = set(re.findall(r"#[0-9A-F]{6}", compare_text[slice(*obj_span(compare_text, "COUNTRY_COLOR"))]))

    def lab(h):
        r, g, b = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        f = lambda c: ((c + 0.055) / 1.055) ** 2.4 if c > 0.04045 else c / 12.92
        r, g, b = f(r), f(g), f(b)
        X = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
        Y = 0.2126 * r + 0.7152 * g + 0.0722 * b
        Z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883
        t = lambda u: u ** (1 / 3) if u > 0.008856 else 7.787 * u + 16 / 116
        return (116 * t(Y) - 16, 500 * (t(X) - t(Y)), 200 * (t(Y) - t(Z)))
    free = [c for c in pal if c not in used]
    if not free:
        die("COMPARE_PALETTE has no unused colour left; add one")
    return max(free, key=lambda c: min(math.dist(lab(c), lab(u)) for u in used))


def step_apps(s):
    n, q = s["name"], json.dumps
    rel = "compare.html"
    t = rd(rel)
    a, b = obj_span(t, "COUNTRY_COLOR")
    have = re.search(r"(?<![\w\"])" + re.escape(js_key(n)) + r"\s*:\s*\"(#[0-9A-F]{6})\"", t[a:b])
    color = have.group(1) if have else (s.get("color") or palette_pick(t))
    s["color"] = color
    new = t
    new = add_entry(new, "FILES", n, " " + q(s["datafile"]))
    new = add_entry(new, "COUNTRY_LABEL", n, q(n))
    new = add_entry(new, "COUNTRY_COLOR", n, q(color))
    new = add_entry(new, "ISO_OF", n, q(s["isonum"]))
    new = add_entry(new, "REGION_OF", n, q(s["region"]))
    new = group_insert(new, s)
    new = source_map(new, s)
    wr(rel, t, new, "FILES/LABEL/COLOR/ISO_OF/REGION_OF/REGION_GROUPS/SOURCE_MAP")

    rel = "dashboard.html"
    t = rd(rel)
    new = add_entry(t, "FILES", n, " " + q(s["datafile"]))
    new = add_entry(new, "ISO_OF", n, q(s["isonum"]))
    new = add_entry(new, "REGISTRY_KEY_TO_CODE", n, " " + q(s["code"]))
    wr(rel, t, new, "FILES/ISO_OF/REGISTRY_KEY_TO_CODE")

    rel = "chartmaker.html"
    t = rd(rel)
    new = add_entry(t, "FILES", n, " " + q(s["datafile"]))
    new = add_entry(new, "COUNTRY_CURRENCY", n, q(s["currency"]))
    new = add_entry(new, "COUNTRY_COLOR", n, q(color))
    new = add_entry(new, "REGISTRY_KEY_TO_CODE", n, " " + q(s["code"]))
    new = add_entry(new, "REGION_OF", n, q(s["region"]))
    new = group_insert(new, s)
    wr(rel, t, new, "FILES/CURRENCY/COLOR/REGISTRY_KEY_TO_CODE/REGION_OF/REGION_GROUPS")


def group_insert(text, s):
    a, b = obj_span(text, "REGION_GROUPS")
    body = text[a:b]
    m = re.search(r'\{name: "' + re.escape(s["region"]) + r'", countries: \[([^\]]*)\]\}', body)
    if not m:
        die(f"REGION_GROUPS has no {s['region']} group")
    if json.dumps(s["name"]) in m.group(1):
        return text
    newlist = m.group(1) + ", " + json.dumps(s["name"])
    body = body[:m.start(1)] + newlist + body[m.end(1):]
    return text[:a] + body + text[b:]


def sources_for(s):
    src = json.load(open(ROOT / "data-metric-sources.json", encoding="utf-8"))
    if s["name"] not in src:
        die(f'data-metric-sources.json has no "{s["name"]}" entry: write the citations first')
    return src[s["name"]]


def source_map(text, s):
    a, b = obj_span(text, "SOURCE_MAP")
    if re.search(r'\n  ' + re.escape(json.dumps(s["name"])) + r": \{", text[a:b]):
        return text
    src = sources_for(s)
    lines = [f'  {json.dumps(s["name"])}: {{']
    for k in sorted(src):
        if k != "fx_usd" and "source" in src[k]:
            lines.append(f"    {k}: {json.dumps(src[k]['source'], ensure_ascii=False)},")
    lines.append("  },")
    ins = text[a:b].rindex("}")
    body = text[a:b]
    body = body[:ins].rstrip() + "\n" + "\n".join(lines) + "\n" + body[ins:]
    return text[:a] + body + text[b:]


def step_markets(s):
    data = json.load(open(ROOT / s["datafile"], encoding="utf-8"))["series"]
    has_bond = "bond_yield_10y" in data
    pk = s.get("policy_rate_key")
    if pk and pk not in data:
        die(f"policy_rate_key {pk} not in {s['datafile']}")
    if pk:
        # The rate key must be one the apps and the generator already read.
        for rel, var in (("compare.html", "POLICY_RATE_KEYS"), ("chartmaker.html", "POLICY_RATE_KEYS")):
            if json.dumps(pk) not in rd(rel)[slice(*obj_span(rd(rel), var))]:
                die(f'{rel} {var} does not read "{pk}": store the rate as "policy_rate" in the fetch script')
        if json.dumps(pk) not in re.search(r'slug="interest-rate", keys=\[[^\]]*\]', rd("generate_indicator_pages.py")).group(0):
            die(f'generate_indicator_pages.py interest-rate keys do not include "{pk}"')
    if not has_bond and not pk:
        return
    rel = "markets.html"
    t = rd(rel)
    new = t
    a, b = obj_span(new, "C")
    if not re.search(r"[{,]\s*" + s["code"] + r"\s*:", new[a:b]):
        new = new[:b - 1] + f',{s["code"]}:["{s["name"]}","{s["slug"]}"]' + new[b - 1:]
    # A euro member shows the ECB's rate, which Markets already lists once
    # under the Eurozone: no per-member POLICY_KEY row (as Austria, v1.7.18).
    if pk and not s.get("euro_member"):
        new = add_entry(new, "POLICY_KEY", s["code"], json.dumps(pk))
    wr(rel, t, new, "C/POLICY_KEY (markets.html: review by eye, it is edited by hand by convention)")
    if pk and not s.get("euro_member"):
        rel = "tools/test_markets.js"
        t = rd(rel)
        new = t
        if f'"{s["datafile"]}":"{pk}"' not in new:
            new = re.sub(r'("data-jp\.json":"boj_rate")', lambda m: m.group(1) + f',"{s["datafile"]}":"{pk}"', new, count=1)
        if f'"{s["datafile"]}":"{s["name"]}"' not in new:
            new = new.replace('const NAMES = {', f'const NAMES = {{"{s["datafile"]}":"{s["name"]}",', 1)
        wr(rel, t, new, "POLICY / NAMES")


def py_dict_add(text, name, entry, present):
    """Insert `entry` before the closing brace of the top-level `name = {`
    literal (dict or set) unless `present` already occurs inside it."""
    m = re.search(r"^" + name + r" = \{", text, re.M)
    if not m:
        die(f"fx_config.py has no {name}")
    d, j = 0, m.end() - 1
    for k in range(j, len(text)):
        if text[k] == "{":
            d += 1
        elif text[k] == "}":
            d -= 1
            if d == 0:
                break
    body = text[j:k]
    if present in body:
        return text
    head = body.rstrip()
    sep = "" if head.endswith(",") or head.endswith("{") else ","
    return text[:j] + head + sep + entry + text[k:]


def step_fx(s):
    rel = "fx_config.py"
    t = rd(rel)
    new = t
    cur, fx, q = s["currency"], s["fx"], json.dumps
    if fx.get("fred"):
        new = py_dict_add(new, "H10", f'\n    {q(cur)}: ({q(fx["fred"])}, {bool(fx.get("usd_per_unit", False))}),\n', q(cur) + ":")
    elif fx.get("annual"):
        new = py_dict_add(new, "ANNUAL", f" {q(cur)}", q(cur))
    else:
        die('spec fx needs "fred": "<H.10 series>" or "annual": true (World Bank PA.NUS.FCRF)')
    if s.get("currency_name"):
        new = py_dict_add(new, "NAME", f"\n        {q(cur)}: {q(s['currency_name'])}", q(cur) + ":")
    if s["glyph"]:
        new = py_dict_add(new, "SYMBOL", f" {q(cur)}: {q(s['glyph'])}", q(cur) + ":")
    if fx.get("scale", 1) != 1:
        new = py_dict_add(new, "SCALE", f" {q(cur)}: {int(fx['scale'])}", q(cur) + ":")
    if s.get("euro_member"):
        if s["currency"] != "EUR":
            die("euro_member needs currency EUR")
        new = re.sub(r'(EURO_MEMBERS = \{[^}]*)\}', lambda m: m.group(0) if q(s["name"]) in m.group(1) else m.group(1) + ", " + q(s["name"]) + "}", new, count=1)
        if not new.count(q(s["name"])):
            die("could not add to fx_config.EURO_MEMBERS")
        g = rd("generate_indicator_pages.py")
        g2 = re.sub(r'(FX_EURO_MEMBERS = \{[^}]*)\}', lambda m: m.group(1) + "}" if q(s["name"]) in m.group(1) else m.group(1) + ", " + q(s["name"]) + "}", g, count=1)
        wr("generate_indicator_pages.py", g, g2, "FX_EURO_MEMBERS")
    pairs = q(fx.get("pairs", ["USD"]))
    new = py_dict_add(new, "COUNTRY_FX", f'\n    {q(s["name"])}: ({q(cur)}, {q(s["code"])}, {pairs}),\n', q(s["name"]) + ":")
    wr(rel, t, new, "H10 or ANNUAL / NAME / SYMBOL / SCALE / COUNTRY_FX")


def step_glyph(s):
    g, cur = s["glyph"], s["currency"]
    if not g:
        return
    esc = g.encode("unicode_escape").decode().replace("\\u", "\\u")
    for rel in [Path(p).name for p in sorted(glob.glob(str(ROOT / "*.html")))] + ["indicator-kit.js"]:
        t = rd(rel)
        if "ISO_GLYPH = {" not in t:
            continue
        a, b = obj_span(t, "ISO_GLYPH")
        if re.search(r"\b" + cur + r"\s*:", t[a:b]):
            continue
        new = t[:b - 1].rstrip() + f', {cur}:{json.dumps(g)}' + t[b - 1:]
        wr(rel, t, new, "ISO_GLYPH")
    rel = "generate_indicator_pages.py"
    t = rd(rel)
    new = t
    for dname in ("ISO_GLYPH", "FX_SYMBOL"):
        m = re.search(dname + r" = \{[^}]*\}", new)
        if not m:
            die(f"generate_indicator_pages.py has no {dname}: this tree predates v1.7.1")
        if f'"{cur}": ' not in m.group(0):
            new = re.sub(r'(' + dname + r' = \{[^}]*)\}', lambda mm: mm.group(1).rstrip() + f', "{cur}": {json.dumps(g)}}}', new, count=1)
    wr(rel, t, new, "ISO_GLYPH / FX_SYMBOL")


def step_freshness(s):
    rel = "check_data_freshness.py"
    t = rd(rel)
    if f'"{s["datafile"]}"' in t:
        return
    new = re.sub(r'(DATA_FILES = \{[^}]*)\}', lambda m: m.group(1).rstrip().rstrip(",") + f', "{s["name"]}": "{s["datafile"]}",\n}}', t, count=1)
    wr(rel, t, new, "DATA_FILES")


def step_counts(s):
    sys.path.insert(0, str(ROOT))
    src = rd("generate_indicator_pages.py")
    n = len(re.findall(r'^    "[^"]+":\s*\("[a-z]{2}", "', src.split("COUNTRIES", 1)[1].split("\n}", 1)[0], re.M))
    for rel, pats in (("index.html", [r"\b\d\d economies\b"]),
                      ("compare.html", [r"across \d\d countries", r"for all \d\d countries", r"full \d\d-country roster"])):
        t = rd(rel)
        new = t
        for p in pats:
            new = re.sub(p, lambda m: re.sub(r"\d\d", str(n), m.group(0)), new)
        wr(rel, t, new, f"country count -> {n}")
    t = rd("check_data_freshness.py")
    wr("check_data_freshness.py", t, re.sub(r"# All \d\d country data files", f"# All {n} country data files", t), "count comment")


def workflow_yaml(s):
    c = s["code"]
    return f"""
---- update-data.yml (paste by hand; workflows are never edited by tools) ----
  1. A step before fetch_fx_daily.py, matching the other fetch steps:
      - name: Run fetch_{c}.py
        continue-on-error: true
        run: |
          echo ">>> RUNNING fetch_{c}.py" >> pipeline_log.txt
          python fetch_{c}.py 2>&1 | tee -a pipeline_log.txt
        env:
          FRED_API_KEY: ${{{{ secrets.FRED_API_KEY }}}}
  2. In the commit step's explicit list:  git add {s['datafile']}
---- update-trade-data.yml ----
  1. A step running fetch_{c}_trade_partners.py (copy the fetch_cn_trade_partners step).
  2. In its commit step:  git add data-{c}-trade-partners.json 2>/dev/null || true
"""


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        die("usage: add_country.py tools/country_specs/<code>.json [--check]")
    s = load_spec(args[0])
    if not (ROOT / s["datafile"]).exists():
        die(f"{s['datafile']} does not exist yet: run the fetch script first")
    sources_for(s)
    step_generator(s)
    step_nav(s)
    step_minimaps(s)
    step_apps(s)
    step_markets(s)
    step_fx(s)
    step_glyph(s)
    step_freshness(s)
    step_counts(s)
    print(("WOULD CHANGE" if CHECK_ONLY else "CHANGED") + f" {len(CHANGES)} surface(s) for {s['name']}"
          + (f" (Compare colour {s['color']})" if s.get("color") else ""))
    for c in CHANGES:
        print("  " + c)
    print(workflow_yaml(s))
    print("Next: python3 tools/build_country_page.py", args[0], "  then  python3 tools/country_surfaces_gate.py")


if __name__ == "__main__":
    main()
