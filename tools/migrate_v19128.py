#!/usr/bin/env python3
"""v1.9.128: three country page fixes.

1. (i) popovers: the notes still used the toggles' old names ("Make it real", "Dollarise") and said
   nothing about Per capita. Each popover now relabels the notes (EA_PC.relabel) and always adds a
   "Per capita:" paragraph (EA_PC.infoNote), which says when the switch is on and what is on screen.
2. Y-axis ticks: a narrow range (China's population, 1.40bn to 1.41bn) printed "1.4bn" on every
   tick. The tick callback now goes through EA_axisTick (mobile.js), which adds decimals until the
   labels differ.
3. Map hint: "All 62 economies. Tap or click a coloured country to open its data." sits directly
   above the map on every country page, the same words as the homepage.

Idempotent: run twice, expect "62 changed" then "0 changed".
"""
import glob, os, sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
MARK = "v1.9.128 info+axis+hint"
HINT = "All 62 economies. Tap or click a coloured country to open its data."

EDITS = [
    # (i): relabel the inflation and USD$ notes
    ("    p.innerHTML = `<strong>Adjust for inflation:</strong> ${content.real}`;",
     "    p.innerHTML = `<strong>Adjust for inflation:</strong> ${window.EA_PC ? EA_PC.relabel(content.real) : content.real}`;"),
    ("    p.innerHTML = `<strong>Convert to USD$:</strong> ${content.dollar}`;",
     "    p.innerHTML = `<strong>Convert to USD$:</strong> ${window.EA_PC ? EA_PC.relabel(content.dollar) : content.dollar}`;"),
    # (i): the Per capita paragraph, after the other two
    ("    togglesEl.appendChild(p);\n  }\n  el.hidden = false;",
     "    togglesEl.appendChild(p);\n  }\n"
     "  /* " + MARK + ": every (i) explains Per capita too */\n"
     "  if(window.EA_PC && EA_PC.infoNote){\n"
     "    const p = document.createElement(\"p\");\n"
     "    p.className = \"infoPopoverToggleNote capita\";\n"
     "    const st = document.createElement(\"strong\"); st.textContent = \"Per capita:\";\n"
     "    p.appendChild(st);\n"
     "    p.appendChild(document.createTextNode(\" \" + EA_PC.infoNote(infoKey, {\n"
     "      unit: ((typeof PAGE_DATA !== \"undefined\" && PAGE_DATA.series || {})[infoKey] || {}).unit,\n"
     "      noPopulation: typeof pcPopulation === \"function\" && !pcPopulation().length,\n"
     "      on: !!TOGGLE_STATE.capita })));\n"
     "    togglesEl.appendChild(p);\n"
     "  }\n"
     "  el.hidden = false;"),
    # axis ticks
    ("            maxTicksLimit:6, callback:v=>fmtY(v)}}",
     "            maxTicksLimit:6, callback:(v,i,t)=>window.EA_axisTick ? EA_axisTick(fmtY,v,i,t) : fmtY(v)}}"),
    ("      opts.scales.y.ticks.callback = v => Number.isInteger(v) ? String(v) : fmtY(v); }",
     "      opts.scales.y.ticks.callback = (v,i,t) => { const f = x => Number.isInteger(x) ? String(x) : fmtY(x); return window.EA_axisTick ? EA_axisTick(f,v,i,t) : f(v); }; }"),
]


def add_hint(s):
    """The hint goes immediately before the map's container, whichever form the page uses."""
    for anchor in ('<div class="mini-mapwrap" id="miniMapWrap"',):
        if s.count(anchor) == 1:
            return s.replace(anchor, '<p class="home-mapcap ea-maphint">' + HINT + '</p>\n' + anchor), True
    return s, False


def main():
    pages = sorted(f for f in glob.glob(os.path.join(ROOT, "*.html"))
                   if "const INFO_CONTENT = {" in open(f, encoding="utf-8").read())
    changed = 0
    for f in pages:
        s = open(f, encoding="utf-8").read()
        if MARK in s:
            continue
        for old, new in EDITS:
            n = s.count(old)
            if n != 1:
                raise SystemExit(f"{os.path.basename(f)}: anchor found {n} times: {old[:60]!r}")
            s = s.replace(old, new)
        s, ok = add_hint(s)
        if not ok:
            raise SystemExit(f"{os.path.basename(f)}: no single map container to put the hint above")
        open(f, "w", encoding="utf-8").write(s)
        changed += 1
    print(f"{len(pages)} page(s) checked, {changed} changed")


if __name__ == "__main__":
    main()
