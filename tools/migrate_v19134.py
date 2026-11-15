#!/usr/bin/env python3
"""v1.9.134: tile and popover polish on the country pages, Compare and Dashboard.

1. A clear space between a tile title and its (i) button (.infoBtn margin 6px -> .5em).
2. The (i) popover's opening sentence (what the metric is) is bold; method notes after it stay normal.
3. The headline CPI tile says it is the annual rate: "CPI inflation (YoY)", shown as "(y/y)" to match
   "CPI (m/m)". labelHtml now also lowercases "(YoY, CSO)" style labels.
4. Miscellaneous tiles and charts were never cleared before a re-render (tiles-misc and charts-misc
   missing from CONTAINER_IDS), so every toggle or tab press added another copy.
5. The Per capita note in the (i) is written for the page: percapita.js v6 takes the country name.

Idempotent: run twice, expect "N changed" then "0 changed".
"""
import glob, os, re, sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
GENERATED_ROOT = {"methodology-by-economy.html", "data-status.html"}

LEAD_FN = '''/* v1.9.134: the (i) popover's first sentence (what the metric is) in bold */
function eaLeadBold(el, text){
  text = String(text == null ? "" : text);
  var m = /^([\\s\\S]+?[.!?])(\\s+(?=[A-Z0-9(\\u201c"])[\\s\\S]*)?$/.exec(text);
  el.textContent = "";
  var b = document.createElement("strong"); b.textContent = m ? m[1] : text; el.appendChild(b);
  if(m && m[2]) el.appendChild(document.createTextNode(m[2]));
}
'''

CPI_TITLES = [
    (',"cpi","CPI inflation",', ',"cpi","CPI inflation (YoY)",'),
    (',"cpi","CPI (YoY)",', ',"cpi","CPI inflation (YoY)",'),
    (',"cpi","CPI inflation (annual)",', ',"cpi","CPI inflation (YoY)",'),
    (',"cpi","HICP inflation",', ',"cpi","HICP inflation (YoY)",'),
    (',"cpi","HICP (YoY)",', ',"cpi","HICP inflation (YoY)",'),
]

OLD_TAG = """const tag = s => s.replace(/\\((QoQ|YoY|MoM)\\)/gi, (m,x)=>'(<span class="lc">'+x.charAt(0).toLowerCase()+'/'+x.charAt(2).toLowerCase()+'</span>)');"""
NEW_TAG = """const tag = s => s.replace(/\\((QoQ|YoY|MoM)([,)])/gi, (m,x,e)=>'(<span class="lc">'+x.charAt(0).toLowerCase()+'/'+x.charAt(2).toLowerCase()+'</span>'+e);"""


def fix(s, name):
    # 1. space before (i)
    s = s.replace("width:16px; height:16px; margin-left:6px; padding:0; border:none;",
                  "width:16px; height:16px; margin-left:.5em; padding:0; border:none;")
    # 2. bold lead sentence
    if "function eaLeadBold(" not in s and "function ensureInfoPopover(" in s:
        s = s.replace("function ensureInfoPopover(", LEAD_FN + "function ensureInfoPopover(", 1)
    s = s.replace('el.querySelector(".infoPopoverDesc").textContent = content.description;',
                  'eaLeadBold(el.querySelector(".infoPopoverDesc"), content.description);')
    s = s.replace('el.querySelector(".infoPopoverDesc").textContent = expl;',
                  'eaLeadBold(el.querySelector(".infoPopoverDesc"), expl);')
    s = re.sub(r'el\.querySelector\("\.infoPopoverDesc"\)\.textContent = (info \? info\.description : [^;]*);',
               r'eaLeadBold(el.querySelector(".infoPopoverDesc"), \1);', s)
    # 3. CPI titles and the label tagger
    for o, n in CPI_TITLES:
        s = s.replace(o, n)
    s = re.sub(r',"cpi_national","CPI inflation \(([A-Z]+)\)",', r',"cpi_national","CPI inflation (YoY, \1)",', s)
    s = s.replace(OLD_TAG, NEW_TAG)
    # 4. Miscellaneous containers cleared on re-render
    s = s.replace('"tiles-public","tiles-markets",\n', '"tiles-public","tiles-markets","tiles-misc",\n', 1) \
        if '"tiles-misc",\n' not in s else s
    s = s.replace('"charts-public","charts-markets"];', '"charts-public","charts-markets","charts-misc"];')
    # 5. Per capita note names the country; percapita.js v6
    s = s.replace("EA_PC.infoNote(infoKey, {\n      unit:",
                  "EA_PC.infoNote(infoKey, {\n      country: typeof COUNTRY_LABEL !== \"undefined\" ? COUNTRY_LABEL : \"\",\n      unit:")
    s = s.replace("percapita.js?v=5", "percapita.js?v=6")
    return s


def main():
    changed = checked = 0
    for f in sorted(glob.glob(os.path.join(ROOT, "*.html"))):
        name = os.path.basename(f)
        if name in GENERATED_ROOT:
            continue
        s0 = open(f, encoding="utf-8").read()
        s = fix(s0, name)
        checked += 1
        if s != s0:
            open(f, "w", encoding="utf-8").write(s)
            changed += 1
    print(f"{checked} page(s) checked, {changed} changed")


if __name__ == "__main__":
    main()
