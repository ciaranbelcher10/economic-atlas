#!/usr/bin/env python3
"""v1.7.57: the real + Dollarise banner names the year of the rate actually used.

realFxYear() returns the last year of the real GDP series (2026 for a page
with quarterly GDP to Q2 2026). rateForPeriod() then falls back to the
nearest year the exchange-rate history has, which for a World Bank annual
history is 2025. The figures were right (Peru: S/614.6bn / 3.5671 =
$172.3bn) but the banner said "the 2026 average rate" (live review of
Iceland and Peru, 16 Oct 2026). realFxRateYear() reports the year whose
rate rateForPeriod() really used, so banner and arithmetic always agree.

Idempotent: re-running reports 0 changes.
"""
import pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parent.parent
MARK = "v1.7.57"

ANCHOR = "function convertRealSeriesToUSD(series, fx){"
FUNC = '''/* v1.7.57: the year whose rate rateForPeriod() actually uses for yr. An
   annual history that ends before yr falls back to its nearest year, and
   the banner must name that year, not yr. */
function realFxRateYear(yr, history){
  if(!yr || !history || !history.length) return yr;
  if(history.some(([p])=>String(p).slice(0,4)===yr)) return yr;
  const t = monthKey(yr);
  let best = history[0], bd = Infinity;
  for(const h of history){ const d = Math.abs(monthKey(String(h[0])) - t); if(d < bd){ bd = d; best = h; } }
  return String(best[0]).slice(0,4);
}
'''
OLD = "if(ry) notes.push(`real GDP converted at the ${ry} average rate throughout"
NEW = "if(ry) notes.push(`real GDP converted at the ${realFxRateYear(ry, fx.history)} average rate throughout"


def patch(text):
    if "function realFxRateYear" in text:
        return text, 0
    if ANCHOR not in text or OLD not in text:
        return text, -1
    text = text.replace(ANCHOR, FUNC + ANCHOR, 1).replace(OLD, NEW, 1)
    return text, 1


def main():
    changed, skipped = [], []
    for p in sorted(ROOT.glob("*.html")):
        t = p.read_text(encoding="utf-8")
        new, n = patch(t)
        if n == 1:
            p.write_text(new, encoding="utf-8"); changed.append(p.name)
        elif n == -1 and "function realFxYear" in t:
            skipped.append(p.name)
    print(f"{MARK}: patched {len(changed)} page(s)")
    if skipped:
        print("FAIL could not patch: " + ", ".join(skipped)); return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
