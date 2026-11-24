#!/usr/bin/env python3
"""v2.0.16: Convert to PPP on the 62 country pages, and the style/mobile cache-busters on every page.

Idempotent: a page already carrying the v2.0.16 PPP block is left as it is; a second run changes nothing.
Run from the repo root:  python3 tools/migrate_v216.py
"""
import glob
import os
import re
import sys

MARK = "/* v2.0.16 Convert to PPP"

BLOCK = r'''/* v2.0.16 Convert to PPP (ppp.js): GDP, real GDP and GDP per person in international dollars, the same rule
   as Chartmaker, Compare and the Dashboard. Each period at its own year's World Bank PPP conversion factor;
   real GDP at its price base year's factor (real x deflator), so growth is unchanged. Never on together with
   Convert to USD$. Applied first, so Adjust for inflation and Per capita then work on the converted figures. */
TOGGLE_STATE.ppp = false;
const PPP_KEYS = ["gdp_level","gdp_level_annual","gdp_real","gdp_real_annual","gdp_per_capita"];
let PPP_APPLIED = new Set(), PPP_DROPPED = [], PPP_ANCHOR = null;
function pppPoints(){ const s = typeof PAGE_DATA !== "undefined" && PAGE_DATA && PAGE_DATA.series && PAGE_DATA.series.ppp; return (s && s.points) || []; }
function pppAvailable(){ return !!(window.EA_PPP && pppPoints().length); }
function buildDisplaySeries(rawSeries){
  PPP_APPLIED = new Set(); PPP_DROPPED = []; PPP_ANCHOR = null;
  if(!TOGGLE_STATE.ppp || !pppAvailable()) return buildDisplaySeriesBase(rawSeries);
  const pre = {...rawSeries}, dropped = new Set();
  PPP_KEYS.forEach(k=>{
    const s = pre[k];
    if(!s || !Array.isArray(s.points) || !(k === "gdp_per_capita" || isCurrencyUnit(s.unit)) || / per /.test(String(s.unit))) return;
    const isReal = k === "gdp_real" || k === "gdp_real_annual";
    const pts = s.points.map(([x, y]) => ({x, y}));
    const ra = ((PAGE_DATA.series.ppp || {}).real_anchor) || {};
    const r = isReal ? EA_PPP.convertReal(pts, s.unit, pppPoints(), ra[k] || ra.gdp_real || s.usd_anchor)
                     : EA_PPP.convert(pts, s.unit, pppPoints());
    if(!r.ok || !r.pts.length){ if(isReal) PPP_ANCHOR = PPP_ANCHOR || "none"; return; }   // left as published; the note says so
    PPP_APPLIED.add(k);
    pre[k] = {...s, unit: k === "gdp_per_capita" ? "Int$" : r.unit, points: r.pts.map(p => [p.x, p.y])};
    if(r.anchorYear) PPP_ANCHOR = r.anchorYear;
    r.droppedYears.forEach(y => dropped.add(y));
  });
  PPP_DROPPED = [...dropped].sort();
  return buildDisplaySeriesBase(pre);
}
function rerender(){
  rerenderBase();
  const b = document.getElementById("togglePpp");
  if(!b) return;
  const ok = pppAvailable();
  b.disabled = !ok; b.classList.toggle("disabled", !ok);
  if(!ok){
    b.setAttribute("aria-disabled", "true"); b.title = "PPP not available for this economy";
    if(TOGGLE_STATE.ppp){ TOGGLE_STATE.ppp = false; b.classList.remove("on"); b.setAttribute("aria-pressed", "false"); }
    return;
  }
  b.removeAttribute("aria-disabled"); b.title = "Convert GDP to international dollars at purchasing power parity";
  if(!TOGGLE_STATE.ppp) return;
  const parts = [], note = document.getElementById("mtoggleNote");
  const realShown = TOGGLE_STATE.real && PPP_ANCHOR;
  if(!realShown || PPP_APPLIED.has("gdp_per_capita"))
    parts.push(EA_PPP.note({droppedYears: PPP_DROPPED}, EA_PPP.latestYear(pppPoints())).replace(/\.$/, ""));
  if(PPP_ANCHOR === "none") parts.push("PPP not available for real GDP here (no PPP conversion factor for its price base year)");
  else if(PPP_ANCHOR) parts.push(EA_PPP.note({anchorYear: PPP_ANCHOR}).replace(/\.$/, ""));
  parts.push("other money figures are shown as published");
  if(note) note.textContent = (note.textContent ? note.textContent + " · " : "") + parts.join(" · ");
}
'''

PPP_BUTTON = (''' <button type="button" class="mtoggle" id="togglePpp" onclick="toggleMetric('ppp',this)" aria-pressed="false">\n'''
              ''' <span class="mtoggle-switch" aria-hidden="true"></span><span class="mt-l" data-short="PPP">Convert to PPP</span>\n'''
              ''' </button>\n </span>\n''')

INFO = '''  /* v2.0.16: GDP figures' (i) explains PPP */
  if(window.EA_PPP && EA_PPP.eligible(infoKey === "gdp_real_annual" ? "gdp_real" : infoKey)){
    const p = document.createElement("p");
    p.className = "infoPopoverToggleNote dollar";
    const st = document.createElement("strong"); st.textContent = "Convert to PPP:";
    p.appendChild(st);
    p.appendChild(document.createTextNode(" " + (typeof pppAvailable === "function" && !pppAvailable()
      ? EA_PPP.infoNote(infoKey, {country: typeof COUNTRY_LABEL !== "undefined" ? COUNTRY_LABEL : "", notOffered: true})
      : EA_PPP.infoNote(infoKey === "gdp_real_annual" ? "gdp_real" : infoKey, {country: typeof COUNTRY_LABEL !== "undefined" ? COUNTRY_LABEL : "", on: !!TOGGLE_STATE.ppp}))));
    togglesEl.appendChild(p);
  }
'''


def sub1(s, old, new, name, f):
    if s.count(old) != 1:
        raise SystemExit(f"{f}: expected one '{name}', found {s.count(old)}")
    return s.replace(old, new)


def migrate_country(f, s):
    if MARK in s:
        return s
    # buttons: USD$ and PPP as one joined pair; short phone labels on all four
    s = re.sub(r'( <button type="button" class="mtoggle" id="toggleDollar" onclick="toggleMetric\(\'dollar\',this\)" aria-pressed="false">\n'
               r' <span class="mtoggle-switch" aria-hidden="true"></span>)Convert to USD\$\n </button>\n',
               lambda m: ' <span class="mtoggle-pair">\n' + m.group(1) + '<span class="mt-l" data-short="USD$">Convert to USD$</span>\n </button>\n' + PPP_BUTTON,
               s, count=1)
    if 'id="togglePpp"' not in s:
        raise SystemExit(f"{f}: Convert to USD$ button not found")
    s = sub1(s, '<span class="mtoggle-switch" aria-hidden="true"></span>Adjust for inflation\n',
             '<span class="mtoggle-switch" aria-hidden="true"></span><span class="mt-l" data-short="Real">Adjust for inflation</span>\n', "real label", f)
    s = sub1(s, '<span class="mtoggle-switch" aria-hidden="true"></span>Per capita\n',
             '<span class="mtoggle-switch" aria-hidden="true"></span><span class="mt-l" data-short="Per cap.">Per capita</span>\n', "capita label", f)
    # conversion: the original builder and rerender become the base the PPP wrappers call
    s = sub1(s, "function buildDisplaySeries(rawSeries){", BLOCK + "function buildDisplaySeriesBase(rawSeries){", "buildDisplaySeries", f)
    s = sub1(s, "function rerender(){\n  if(!PAGE_DATA", "function rerenderBase(){\n  if(!PAGE_DATA", "rerender", f)
    # one way to dollars at a time
    s = sub1(s, "function toggleMetric(which, el){\n  if(el.disabled) return;\n",
             "function toggleMetric(which, el){\n  if(el.disabled) return;\n"
             "  // v2.0.16: Convert to USD$ and Convert to PPP are never on together\n"
             "  const other = which === \"dollar\" ? [\"ppp\", \"togglePpp\"] : which === \"ppp\" ? [\"dollar\", \"toggleDollar\"] : null;\n"
             "  if(other && !TOGGLE_STATE[which] && TOGGLE_STATE[other[0]]){\n"
             "    TOGGLE_STATE[other[0]] = false;\n"
             "    const ob = document.getElementById(other[1]);\n"
             "    if(ob){ ob.classList.remove(\"on\"); ob.setAttribute(\"aria-pressed\", \"false\"); }\n"
             "  }\n", "toggleMetric", f)
    s = sub1(s, 'const label = which === "real" ? "Adjust for inflation" : which === "capita" ? "Per capita" : "Convert to USD$";',
             'const label = which === "real" ? "Adjust for inflation" : which === "capita" ? "Per capita" : which === "ppp" ? "Convert to PPP" : "Convert to USD$";', "announce", f)
    # colours: PPP takes Convert to USD$'s colours, on the figures it converts
    s = sub1(s, "  const realOn = TOGGLE_STATE.real, dollarOn = TOGGLE_STATE.dollar;",
             "  const realOn = TOGGLE_STATE.real, dollarOn = TOGGLE_STATE.dollar || !!TOGGLE_STATE.ppp;   // v2.0.16", "realOn", f)
    s, n = re.subn(r"const dollarHit = dollarOn && CURRENCY_KEYS\.includes\(key\)",
                   "const dollarHit = dollarOn && (TOGGLE_STATE.ppp ? PPP_APPLIED.has(key) : CURRENCY_KEYS.includes(key))", s)
    if n != 1:
        raise SystemExit(f"{f}: dollarHit not found")
    i = s.index("function applyToggleHighlighting(){")
    j = s.index("\n}\n", i)
    body = s[i:j]
    body = sub1(body, '  const dollarBtn = document.getElementById("toggleDollar");',
                '  const dollarBtn = document.getElementById(TOGGLE_STATE.ppp ? "togglePpp" : "toggleDollar");', "highlight dollarBtn", f)
    body = sub1(body, '  [realBtn, dollarBtn].forEach(b=>b && b.classList.remove("fx-real","fx-dollar","fx-both"));',
                '  [realBtn, document.getElementById("toggleDollar"), document.getElementById("togglePpp")].forEach(b=>b && b.classList.remove("fx-real","fx-dollar","fx-both"));', "highlight clear", f)
    s = s[:i] + body + s[j:]
    s = sub1(s, "  const r = TOGGLE_STATE.real, d = TOGGLE_STATE.dollar;",
             "  const r = TOGGLE_STATE.real, d = TOGGLE_STATE.dollar || !!TOGGLE_STATE.ppp;", "pc d", f)
    s = sub1(s, 'const btns = ["toggleReal","toggleDollar","toggleCapita"]', 'const btns = ["toggleReal","toggleDollar","togglePpp","toggleCapita"]', "pc btns", f)
    s = sub1(s, '(b.id === "toggleDollar" && d)){', '(b.id === "toggleDollar" && TOGGLE_STATE.dollar) || (b.id === "togglePpp" && TOGGLE_STATE.ppp)){', "pc combo", f)
    # saved charts keep the switch
    s = sub1(s, "o.toggles = { dollar: !!TOGGLE_STATE.dollar, real: !!TOGGLE_STATE.real, capita: !!TOGGLE_STATE.capita };",
             "o.toggles = { dollar: !!TOGGLE_STATE.dollar, real: !!TOGGLE_STATE.real, capita: !!TOGGLE_STATE.capita, ppp: !!TOGGLE_STATE.ppp };", "save", f)
    s = sub1(s, '[["dollar", "toggleDollar"], ["real", "toggleReal"], ["capita", "toggleCapita"]]',
             '[["dollar", "toggleDollar"], ["ppp", "togglePpp"], ["real", "toggleReal"], ["capita", "toggleCapita"]]', "restore", f)
    # values print as Int$
    s = sub1(s, "function currencySymbol(unitStr){\n",
             "function currencySymbol(unitStr){\n  if(/^Int\\$/.test(unitStr)) return \"Int$\";   // v2.0.16: international dollars (PPP)\n", "currencySymbol", f)
    s = sub1(s, "      on: !!TOGGLE_STATE.capita })));\n    togglesEl.appendChild(p);\n  }\n",
             "      on: !!TOGGLE_STATE.capita })));\n    togglesEl.appendChild(p);\n  }\n" + INFO, "info", f)
    s = re.sub(r'(<script src="percapita\.js\?v=\d+"></script>)', r'\1\n<script src="ppp.js?v=1"></script>', s, count=1)
    if "ppp.js?v=1" not in s:
        raise SystemExit(f"{f}: percapita.js tag not found")
    return s


def bump(s):
    s = s.replace("style.css?v=63", "style.css?v=64")
    s = s.replace("mobile.css?v=53", "mobile.css?v=54")
    s = s.replace("mobile.js?v=51", "mobile.js?v=52")
    return s


def main(root="."):
    changed = 0
    for f in sorted(glob.glob(os.path.join(root, "*.html")) + glob.glob(os.path.join(root, "indicators", "*.html"))):
        s0 = open(f, encoding="utf-8").read()
        s = s0
        if 'id="toggleCapita"' in s and "onclick=\"toggleMetric('capita',this)\"" in s:
            s = migrate_country(f, s)
        s = bump(s)
        if s != s0:
            open(f, "w", encoding="utf-8").write(s)
            changed += 1
    print(f"migrate_v216: {changed} page(s) changed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
