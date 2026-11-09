#!/usr/bin/env python3
"""v1.9.113: toggle labels renamed ("Dollarise" -> "Convert to USD$", "Make it real" ->
"Adjust for inflation") in visible text; code identifiers and saved-setting keys unchanged.
Notes read from data-metric-sources.json are relabelled when shown (that file is not edited).
Markets yields/FX tables: status dots get role="img"; each expandable row carries a real
button with aria-expanded (a plain table row may not). Page edits at deploy, idempotent.
Run from the repo root:  python3 tools/migrate_v19113.py   (exits 1 if anything is left)"""
import glob, os, re, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GENERATED = {"methodology-by-economy.html", "gdp-by-country.html", "inflation-by-country.html",
             "unemployment-by-country.html", "data-status.html"}
OLD_D = re.compile(r"(?<![A-Za-z_\-#.])Dollarise(?![A-Za-z_\-])")
OLD_R = re.compile(r"(?<![A-Za-z_\-#.])Make it real(?![A-Za-z_\-])")
NEW_D, NEW_R = "Convert to USD$", "Adjust for inflation"

def rename(s):
    return OLD_R.sub(NEW_R, OLD_D.sub(lambda m: NEW_D, s))

RELABEL_FN = ('function eaRelabel(t){ /* v1.9.113: notes in data-metric-sources.json use the old toggle names */\n'
              '  return String(t).replace(/Dollari[s]e/g, function(){ return "Convert to USD$"; })'
              '.replace(/Make it rea[l]/g, function(){ return "Adjust for inflation"; }); }\n')
DASH_SUBS = [("escapeHtmlDash(info.dollar)", "escapeHtmlDash(eaRelabel(info.dollar))"),
             ("escapeHtmlDash(info.real)", "escapeHtmlDash(eaRelabel(info.real))")]

MK_LED_OLD = "return '<span class=\"mk-led ' + c + '\" title=\"' + t + '\" aria-label=\"' + t + '\"></span>';"
MK_LED_NEW = "return '<span class=\"mk-led ' + c + '\" role=\"img\" title=\"' + t + '\" aria-label=\"' + t + '\"></span>';"
MK_ROWS_OLD = '    tr.tabIndex = 0; tr.setAttribute("aria-expanded", "false");\n'
MK_ROWS_NEW = ('    /* v1.9.113: the expanded state lives on a real button (a table row may not carry it) */\n'
               '    if(!tr.querySelector(".mk-rowbtn")){ var b = document.createElement("button"); b.type = "button"; b.className = "mk-rowbtn";\n'
               '      b.setAttribute("aria-expanded", "false"); b.textContent = "Details for " + (tr.cells[0] ? tr.cells[0].textContent.trim() : "this row");\n'
               '      if(tr.cells[0]) tr.cells[0].appendChild(b); }\n')
MK_SET = [('tr.classList.remove("mk-open"); tr.setAttribute("aria-expanded", "false"); return; }',
           'tr.classList.remove("mk-open"); mkRowState(tr, false); return; }'),
          ('tr.classList.add("mk-open"); tr.setAttribute("aria-expanded", "true");',
           'tr.classList.add("mk-open"); mkRowState(tr, true);'),
          ('if(t){ t.classList.remove("mk-open"); t.setAttribute("aria-expanded", "false"); }',
           'if(t){ t.classList.remove("mk-open"); mkRowState(t, false); }')]
MK_FN_ANCHOR = "function toggleRow(table, tr){\n"
MK_FN = ('function mkRowState(tr, open){ var b = tr.querySelector(".mk-rowbtn"); if(b) b.setAttribute("aria-expanded", open ? "true" : "false"); }\n')
MK_CSS_ANCHOR = '.mk-i[aria-expanded="true"]{color:var(--ink);}'
MK_CSS = ('\n.mk-rowbtn{position:absolute; width:1px; height:1px; padding:0; margin:-1px; overflow:hidden; clip:rect(0 0 0 0); border:0; white-space:nowrap;}\n'
          '.mk-rowbtn:focus-visible{position:static; width:auto; height:auto; margin:0 0 0 6px; clip:auto; overflow:visible; padding:2px 6px; border-radius:6px;'
          ' font:inherit; font-size:12px; background:var(--panel); color:var(--ink); outline:2px solid var(--blue);}')

def markets(s):
    if MK_LED_OLD in s: s = s.replace(MK_LED_OLD, MK_LED_NEW, 1)
    if MK_ROWS_OLD in s: s = s.replace(MK_ROWS_OLD, MK_ROWS_NEW, 1)
    for a, b in MK_SET: s = s.replace(a, b)
    if "function mkRowState(" not in s and MK_FN_ANCHOR in s: s = s.replace(MK_FN_ANCHOR, MK_FN + MK_FN_ANCHOR, 1)
    if ".mk-rowbtn{" not in s and MK_CSS_ANCHOR in s: s = s.replace(MK_CSS_ANCHOR, MK_CSS_ANCHOR + MK_CSS, 1)
    return s

def problems(name, s):
    out = []
    if OLD_D.search(s) or OLD_R.search(s): out.append("old label left")
    if "USD${" in s: out.append("label next to a template expression")
    if name == "dashboard.html" and ("eaRelabel(info.dollar)" not in s or "function eaRelabel(" not in s): out.append("popover relabel")
    if name == "markets.html":
        if MK_LED_NEW not in s: out.append("led role")
        if 'tr.setAttribute("aria-expanded"' in s or 't.setAttribute("aria-expanded"' in s: out.append("row aria-expanded left")
        if "function mkRowState(" not in s or ".mk-rowbtn{" not in s or 'b.className = "mk-rowbtn"' not in s: out.append("row button")
    return out

def main():
    changed = 0; bad = []
    targets = [f for f in sorted(glob.glob(os.path.join(ROOT, "*.html"))) if os.path.basename(f) not in GENERATED]
    targets += [os.path.join(ROOT, p) for p in ("mobile.js", "generate_indicator_pages.py", "methodology_by_economy.py")]
    for f in targets:
        name = os.path.basename(f); s = open(f, encoding="utf-8").read(); new = rename(s)
        if name == "dashboard.html":
            for a, b in DASH_SUBS: new = new.replace(a, b)
            anchor = "function openInfoPopover(btn, country, key){\n"
            if "function eaRelabel(" not in new and anchor in new: new = new.replace(anchor, RELABEL_FN + anchor, 1)
        if name == "markets.html": new = markets(new)
        if new != s: open(f, "w", encoding="utf-8").write(new); changed += 1
        bad += [name + ": " + p for p in problems(name, new)]
    print(f"migrate_v19113: {changed} file(s) changed")
    if bad: print("migrate_v19113: FAIL\n  " + "\n  ".join(bad)); return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
