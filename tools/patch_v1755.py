#!/usr/bin/env python3
"""v1.7.55: Dollarise fixes on every country page (and the china.html template).

1. Real + Dollarise: real GDP (gdp_real, gdp_real_annual, and gdp_level when
   "Make it real" swaps it in) is converted at ONE rate, the average rate of
   the series' latest year, instead of each year's own rate. Converting
   constant-price local currency at a moving nominal rate turned devaluation
   into apparent contraction (Egypt: -$7.2bn in a year of +4.4% real growth).
   A single rate keeps real growth exactly as published.
2. Dollarise banner: the history span starts at fx.floor when one is set,
   and the floor note shows whenever a series has points before the floor
   (it never showed, because the check compared against history start).

Idempotent: re-running reports 0 changes.
"""
import pathlib, re, sys
ROOT = pathlib.Path(__file__).resolve().parent.parent
MARK = "v1.7.55"

FUNC_ANCHOR = "/* ------------------ historical FX period-matching lookup ------------------"
FUNC = r'''/* v1.7.55: real GDP is converted at ONE exchange rate, the average of the
   series' latest year, not each year's own rate. Constant-price local
   currency divided by a moving nominal rate turns devaluation into apparent
   contraction; a single rate keeps real growth exactly as published. */
function realFxYear(series){
  const pts = series.points || [];
  return pts.length ? String(pts[pts.length-1][0]).slice(0,4) : null;
}
function convertRealSeriesToUSD(series, fx){
  const yr = realFxYear(series);
  const rate = (fx.history && fx.history.length && yr) ? rateForPeriod(yr, fx.history) : fx.rate;
  const newUnit = "$"+series.unit.replace(/^(?:[A-Za-z]+(?=(?:m|bn|tn)$)|[^a-zA-Z0-9]+)/,"");
  return {...series, unit:newUnit, real_fx_year:yr,
          points: series.points.map(([p,v])=>[p, fx.direction==="multiply" ? v*rate : v/rate])};
}
/* v1.7.55: points before fx.floor are dropped from the dollar view. */
function hasPreFloorPoints(series, fx){
  if(!fx || !fx.floor) return false;
  const fk = monthKey(String(fx.floor));
  return series.points.some(([p])=> monthKey(p) !== null && monthKey(p) < fk);
}
'''

OLD_LOOP = """      if(out[k] && isCurrencyUnit(out[k].unit) && !isAlreadyUSD(out[k].unit, k)) out[k]=convertSeriesToUSD(out[k], fx);"""
NEW_LOOP = """      if(out[k] && isCurrencyUnit(out[k].unit) && !isAlreadyUSD(out[k].unit, k)){
        // v1.7.55: real series convert at one rate (see convertRealSeriesToUSD)
        const isReal = k==="gdp_real" || k==="gdp_real_annual" || (k==="gdp_level" && realView);
        out[k] = isReal ? convertRealSeriesToUSD(out[k], fx) : convertSeriesToUSD(out[k], fx);
      }"""

OLD_REALIF = "function buildDisplaySeries(rawSeries){\n  const out = {};\n  for(const k in rawSeries) out[k]=rawSeries[k];\n"
NEW_REALIF = OLD_REALIF + "  // v1.7.55: is gdp_level about to hold a real series?\n  const realView = !!(TOGGLE_STATE.real && (rawSeries.gdp_real || rawSeries.gdp_real_annual));\n"

OLD_NOTE = r"""      notes.push(`Currency figures converted at each period's own ${fx.pair} rate (history: ${fx.history[0][0]} to ${fx.history[fx.history.length-1][0]}; latest ${fxRateTxt(fx.rate)} as of ${fx.as_of})`);
      const anyPreHistory = CURRENCY_KEYS.some(k => s[k] && hasPreHistoryPoints(s[k], fx));
      if(anyPreHistory){"""
NEW_NOTE = r"""      // v1.7.55: the span starts at the floor when one is set
      const histStart = (fx.floor && monthKey(String(fx.floor)) > monthKey(fx.history[0][0])) ? String(fx.floor) : fx.history[0][0];
      notes.push(`Currency figures converted at each period's own ${fx.pair} rate (history: ${histStart} to ${fx.history[fx.history.length-1][0]}; latest ${fxRateTxt(fx.rate)} as of ${fx.as_of})`);
      const anyPreHistory = CURRENCY_KEYS.some(k => s[k] && (hasPreHistoryPoints(s[k], fx) || hasPreFloorPoints(s[k], fx)));
      if(TOGGLE_STATE.real && s.gdp_real){
        const ry = realFxYear(s.gdp_real_annual || s.gdp_real);
        if(ry) notes.push(`real GDP converted at the ${ry} average rate throughout, so its growth matches the published real growth`);
      }
      if(anyPreHistory){"""

def patch(path):
    s = path.read_text(encoding="utf-8")
    if "function convertRealSeriesToUSD" in s:
        return 0
    if "function buildDisplaySeries" not in s or path.name == "us.html":
        return 0
    old_note, new_note = OLD_NOTE, NEW_NOTE
    if s.count(old_note) == 0:  # pages that hard-code the pair (uk.html: GBP/USD)
        m = re.search(r"converted at each period's own ([A-Z]{3}/USD) rate \(history: \$\{fx\.history\[0\]", s)
        if m:
            old_note = OLD_NOTE.replace("${fx.pair}", m.group(1))
            new_note = NEW_NOTE.replace("${fx.pair}", m.group(1))
    checks = [(FUNC_ANCHOR,1),(OLD_LOOP,1),(old_note,1)]
    for a,n in checks:
        c = s.count(a)
        if c != n: sys.exit(f"{path.name}: anchor found {c}x: {a[:60]!r}")
    # real-if: plain form, or Switzerland's annual-swap form
    if s.count(OLD_REALIF) != 1: sys.exit(f"{path.name}: real-if found {s.count(OLD_REALIF)}x")
    s = s.replace(OLD_REALIF, NEW_REALIF)
    s = s.replace(FUNC_ANCHOR, FUNC + FUNC_ANCHOR)
    s = s.replace(OLD_LOOP, NEW_LOOP)
    s = s.replace(old_note, new_note)
    path.write_text(s, encoding="utf-8")
    return 1

n = 0
changed = []
for p in sorted(ROOT.glob("*.html")):
    if patch(p): changed.append(p.name)
print(f"patched {len(changed)} page(s)")
for c in changed: print(" ", c)
