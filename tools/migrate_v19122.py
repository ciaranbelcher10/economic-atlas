#!/usr/bin/env python3
"""v1.9.122: Per capita toggle on the 62 country pages.

Adds a third display toggle after "Adjust for inflation | Convert to USD$". When on, every
eligible currency series (EA_PC.ELIGIBLE: gdp_level, gdp_real, exports, imports, trade_balance,
net_debt, debt_interest, deficit) is divided by THAT YEAR's population through percapita.js
(EA_PC.divide), after the inflation and USD transforms. Missing years are dropped and named in
the toggle note (EA_PC.note). Tiles and charts of eligible metrics get the per capita glow,
with combination colours; the tile period line names the population year used.

Idempotent: run twice, expect "62 changed" then "0 changed".
Usage: python3 tools/migrate_v19122.py [repo_root]
"""
import glob, os, re, sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
MARK = "v1.9.122 per capita"
SKIP = {"chartmaker.html", "compare.html", "dashboard.html"}

CSS_ANCHOR = 'button.mtoggle.fx-both{background:#2FA463; border-color:#2FA463; color:#fff;}'
CSS_ADD = '''
/* v1.9.122 per capita: coral on its own; orange with inflation, purple with USD$, brown with all three */
.stat.fx-pc, .panel.fx-pc{border-color:#E06A5A !important; box-shadow:0 0 0 2px rgba(224,106,90,.35);}
.stat.fx-real-pc, .panel.fx-real-pc{border-color:#E8853A !important; box-shadow:0 0 0 2px rgba(232,133,58,.35);}
.stat.fx-dollar-pc, .panel.fx-dollar-pc{border-color:#8E63C9 !important; box-shadow:0 0 0 2px rgba(142,99,201,.35);}
.stat.fx-all, .panel.fx-all{border-color:#8A5A3C !important; box-shadow:0 0 0 2px rgba(138,90,60,.35);}
button.mtoggle.fx-pc{background:#E06A5A; border-color:#E06A5A; color:#fff;}
button.mtoggle.fx-real-pc{background:#E8853A; border-color:#E8853A; color:#171B1E;}
button.mtoggle.fx-dollar-pc{background:#8E63C9; border-color:#8E63C9; color:#fff;}
button.mtoggle.fx-all{background:#8A5A3C; border-color:#8A5A3C; color:#fff;}'''

BTN_ANCHOR = ' <span class="mtoggle-note" id="mtoggleNote"></span>'
BTN_ADD = (' <button type="button" class="mtoggle" id="toggleCapita" onclick="toggleMetric(\'capita\',this)" aria-pressed="false">\n'
           ' <span class="mtoggle-switch" aria-hidden="true"></span>Per capita\n'
           ' </button>\n')

SCRIPT_ANCHOR = '<script src="mobile.js'
SCRIPT_ADD = '<script src="percapita.js?v=3"></script>\n'

STATE_OLD = 'const TOGGLE_STATE = { real:false, dollar:false };'
STATE_NEW = '''const TOGGLE_STATE = { real:false, dollar:false, capita:false };
/* v1.9.122 per capita: keys whose displayed series is currently divided by population */
const PC_APPLIED = new Set();
function pcEligibleKeys(){ return (window.EA_PC && window.EA_PC.ELIGIBLE) || []; }
function pcPopulation(){ const p = PAGE_DATA && PAGE_DATA.series && PAGE_DATA.series.population; return (p && p.points) || []; }
// [[period, value], ...] -> per person, each period divided by its own year's population only.
function pcSeries(series){
  const r = window.EA_PC.divide(series.points.map(([x, y]) => ({x, y})), series.unit, pcPopulation());
  return { series: {...series, points: r.pts.map(p => [p.x, p.y]), unit: r.unit}, dropped: r.droppedYears };
}
let PC_DROPPED = [], PC_GDP_SERIES = null;'''

CURFMT_OLD = 'function curFmt(rawValue, unitStr, decimals){\n'
CURFMT_NEW = '''function curFmt(rawValue, unitStr, decimals){
  // v1.9.122: per person values are whole currency units ("\\u00a343,815"), never "\\u00a30m"
  if(/ per person$/.test(String(unitStr || ""))){
    // the page's own symbol rules (A$, dollarised $) via its normal path: "A$1m" -> "A$"
    const sym = curFmt(1, String(unitStr).replace(/ per person$/, "m"), 0).replace(/1m$/, "");
    if(rawValue === 0) return sym + "0";
    return (rawValue < 0 ? "\\u2212" : "") + sym + Math.round(Math.abs(rawValue)).toLocaleString("en-GB");
  }
'''

LABEL_OLD = '  const label = which === "real" ? "Adjust for inflation" : "Convert to USD$";'
LABEL_NEW = '  const label = which === "real" ? "Adjust for inflation" : which === "capita" ? "Per capita" : "Convert to USD$";'

NOTES_OLD = '  if(TOGGLE_STATE.real) notes.push("GDP shown in real terms (chained volume / constant prices)");'
NOTES_NEW = NOTES_OLD + '''
  // v1.9.122 per capita: the button is off where there is no population (Taiwan); the note names dropped years
  const capitaBtn = document.getElementById("toggleCapita");
  if(capitaBtn){
    const noPop = !pcPopulation().length || !window.EA_PC;
    capitaBtn.disabled = noPop; capitaBtn.classList.toggle("disabled", noPop);
    if(noPop){ capitaBtn.setAttribute("aria-disabled", "true"); capitaBtn.title = "Population not available for this economy"; TOGGLE_STATE.capita = false; capitaBtn.classList.remove("on"); capitaBtn.setAttribute("aria-pressed", "false"); }
    else { capitaBtn.removeAttribute("aria-disabled"); capitaBtn.title = ""; }
  }'''

RENDER_OLD = '  const displaySeries = buildDisplaySeries(s);'
RENDER_NEW = '''  const displaySeries = buildDisplaySeries(s);
  if(TOGGLE_STATE.capita && window.EA_PC){
    const pcNote = window.EA_PC.note(PC_DROPPED, window.EA_PC.latestYear(pcPopulation()), !pcPopulation().length);
    note.textContent = note.textContent ? note.textContent + " \\u00b7 " + pcNote : pcNote;
  }'''

HL_CALL_OLD = '  applyToggleHighlighting();\n'
HL_CALL_NEW = '  applyToggleHighlighting();\n  applyPerCapitaHighlighting();\n'

HL_FN = '''/* v1.9.122 per capita glow, layered on applyToggleHighlighting's classes:
   none -> coral, inflation -> orange, USD$ -> purple, inflation + USD$ -> brown. */
function applyPerCapitaHighlighting(){
  const on = TOGGLE_STATE.capita;
  const combo = {"": "fx-pc", "fx-real": "fx-real-pc", "fx-dollar": "fx-dollar-pc", "fx-both": "fx-all"};
  const prev = el => ["fx-real","fx-dollar","fx-both"].find(c => el.classList.contains(c)) || "";
  document.querySelectorAll(".stat[data-key], .panel[data-key]").forEach(el=>{
    el.classList.remove("fx-pc","fx-real-pc","fx-dollar-pc","fx-all");
    if(!on || !PC_APPLIED.has(el.dataset.key)) return;
    const p = prev(el); if(p) el.classList.remove(p);
    el.classList.add(combo[p]);
  });
  const btns = ["toggleReal","toggleDollar","toggleCapita"].map(id => document.getElementById(id)).filter(Boolean);
  btns.forEach(b => b.classList.remove("fx-pc","fx-real-pc","fx-dollar-pc","fx-all"));
  if(!on) return;
  const r = TOGGLE_STATE.real, d = TOGGLE_STATE.dollar;
  const cls = r && d ? "fx-all" : r ? "fx-real-pc" : d ? "fx-dollar-pc" : "fx-pc";
  btns.forEach(b => { if(b.id === "toggleCapita" || (b.id === "toggleReal" && r) || (b.id === "toggleDollar" && d)){ b.classList.remove("fx-real","fx-dollar","fx-both"); b.classList.add(cls); } });
}
'''
HL_FN_ANCHOR = 'function applyToggleHighlighting(){'

PERIOD_RE = re.compile(r'(<p class="period">\$\{(?:_fmtP|fmtPeriod)\(last\[0\]\)\})(</p>)')
PERIOD_ADD = r'\1${(typeof PC_APPLIED !== "undefined" && PC_APPLIED.has(key)) ? " \\u00b7 per person, " + String(last[0]).slice(0, 4) + " population" : ""}\2'

BDS_BLOCK = r'''  // v1.9.122 per capita: last, after inflation and USD$, so it divides what is shown
  PC_APPLIED.clear(); PC_DROPPED = []; PC_GDP_SERIES = null;
  // Poland, Turkey: gdp_level may already be a trailing four-quarter sum (gdp_level_annual / gdp_real_annual)
  const pcRolling = !!out.gdp_level && /trailing 4-quarter sum/i.test(String(out.gdp_level.label || ""));
  if(TOGGLE_STATE.capita && window.EA_PC && pcPopulation().length){
    const dropped = new Set();
    pcEligibleKeys().forEach(k=>{
      if(!out[k] || !Array.isArray(out[k].points) || !/(m|bn|tn)$/.test(String(out[k].unit || "").replace(/\s*\(.*\)\s*$/, ""))) return;
      const r = pcSeries(out[k]);
      if(!r.series.points.length) return;
      out[k] = r.series; PC_APPLIED.add(k); r.dropped.forEach(y => dropped.add(y));
    });
    PC_DROPPED = [...dropped].sort();
    if(PC_APPLIED.has("gdp_level")) PC_GDP_SERIES = {...out.gdp_level, pcRolling};   // the per person series the page shows
  }
'''

TILE_OLD = 'function statTile(el, key, title, series, opts){\n'
TILE_NEW = TILE_OLD + """  // v1.9.122: with Per capita on, the GDP tile is the latest complete calendar year, the same
  // figure as the GDP per capita tile and Compare (never a part year, never one quarter's rate)
  if(key === "gdp_level" && typeof PC_APPLIED !== "undefined" && PC_APPLIED.has("gdp_level") && series)
    series = pcCalendarYears(PC_GDP_SERIES || series);
"""
PCY_FN = r"""/* v1.9.122: {year: GDP per person} for complete years only, as merge_population.py's
   calendar_year_gdp: an annual figure, or all four quarters summed (averaged where quarters are
   published at an annual rate: US, Japan). Each quarter was already divided by its own year's
   population, so the sum or mean equals the year's GDP over that year's population. */
const PC_ANNUAL_RATE = ["US", "Japan"];
function pcCalendarYears(series){
  const pts = (series.points || []).filter(p => p && p[1] != null && isFinite(p[1]));
  if(series.freq === "years" || pts.every(p => /^\d{4}$/.test(String(p[0])))) return series;
  if(series.pcRolling){   // a trailing four-quarter sum at Q4 is that calendar year
    const q4 = pts.filter(p => /^\d{4}-Q4$/.test(String(p[0]))).map(p => [String(p[0]).slice(0, 4), p[1]]);
    return q4.length ? {...series, points: q4, freq: "years"} : series;
  }
  const by = {};
  pts.forEach(([per, v]) => { const m = /^(\d{4})-Q([1-4])$/.exec(String(per)); if(m) (by[m[1]] = by[m[1]] || {})[m[2]] = v; });
  const out = Object.keys(by).sort().filter(y => Object.keys(by[y]).length === 4).map(y => {
    const tot = Object.values(by[y]).reduce((a, b) => a + b, 0);
    return [y, PC_ANNUAL_RATE.includes(COUNTRY_LABEL) ? tot / 4 : tot];
  });
  return out.length ? {...series, points: out, freq: "years"} : series;
}
"""


def migrate(s):
    if MARK in s:
        return s, False
    def once(old, new, label):
        nonlocal s
        n = s.count(old)
        if n != 1:
            raise SystemExit(f"anchor {label!r} found {n} times")
        s = s.replace(old, new)
    once(CSS_ANCHOR, CSS_ANCHOR + CSS_ADD, "css")
    once(BTN_ANCHOR, BTN_ADD + BTN_ANCHOR, "button")
    once(SCRIPT_ANCHOR, SCRIPT_ADD + SCRIPT_ANCHOR, "script")
    once(STATE_OLD, STATE_NEW.replace("/* v1.9.122 per capita:", "/* " + MARK + ":"), "state")
    once(CURFMT_OLD, CURFMT_NEW, "curFmt")
    once(LABEL_OLD, LABEL_NEW, "announce")
    once(NOTES_OLD, NOTES_NEW, "notes")
    once(RENDER_OLD, RENDER_NEW, "render")
    once(HL_CALL_OLD, HL_CALL_NEW, "hl call")
    once(HL_FN_ANCHOR, HL_FN + PCY_FN + HL_FN_ANCHOR, "hl fn")
    once(TILE_OLD, TILE_NEW, "statTile")
    s, n = PERIOD_RE.subn(PERIOD_ADD, s)
    if n != 1:
        raise SystemExit(f"period line found {n} times")
    # last "  return out;\n}" inside buildDisplaySeries
    i = s.index("function buildDisplaySeries(rawSeries){")
    j = s.index("\n  return out;\n}\n", i)
    if s.find("\nfunction ", i + 10) < j:
        raise SystemExit("buildDisplaySeries return not found")
    s = s[:j + 1] + BDS_BLOCK + s[j + 1:]
    return s, True


def main():
    pages = sorted(f for f in glob.glob(os.path.join(ROOT, "*.html"))
                   if os.path.basename(f) not in SKIP and 'id="toggleDollar"' in open(f, encoding="utf-8").read())
    changed = 0
    for f in pages:
        s = open(f, encoding="utf-8").read()
        new, did = migrate(s)
        if did:
            open(f, "w", encoding="utf-8").write(new)
            changed += 1
    print(f"{len(pages)} page(s) checked, {changed} changed")


if __name__ == "__main__":
    main()
