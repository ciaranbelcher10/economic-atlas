# v2.0.11: smoother phone map, compact switch row

1. **Map card opens and closes smoothly (homepage and country pages, phones).**
   - Closing snapped shut on country pages: a `max-height:130px !important` rule outranked the animation's inline height, and the target height was measured with every cap removed, so closing measured as no change.
   - mobile.js now sets the animated height as an !important inline style and measures the target with the page's own cap.
   - Measured in Chromium at 390px, every 60ms. Country page opening: 130, 157, 179, 187, 189, 190. Closing: 163, 141, 135, 131, 130. Homepage: 190 to 323 and back, the same way.
   - The fade at the foot of the closed card and the Expand pill now fade (0.25s) rather than vanish. The motion is slightly slower (0.35s), and reduced-motion still turns it off.
2. **Convert to USD$, Adjust for inflation and Per capita share one compact 42px row on phones** (they took two full-width rows). The switch is smaller and labels run to two lines at most. On My Dashboard the (i) fits on the same row. Checked at 390px and 360px.
3. **Cache-busters bumped together** on every page and in the indicator generator: mobile.css?v=50, mobile.js?v=48 (tools/migrate_v211.py, idempotent).

Tests: html_gate 0, generated_pages_gate 0. The mobile suites are unchanged from main: chartmaker 41/0, compare 127/0, markets 110/0, foundations 27/0, rankings 202/0. dashboard_mobile has 3 failures on main as well: they are stale checks for the picker's chooser.js version and the intro wording.

## Deploy (Claude Code)
1. Verify the sha256, run `git pull`, then unzip at the repo root.
2. Run `python3 tools/migrate_v211.py` (expect about 1,200 files changed), then run it again (expect 0).
3. Run `python3 tools/html_gate.py` and `python3 tools/generated_pages_gate.py` (expect 0 failures each).
4. `git add -u && xargs git add < FILES.txt`, commit "v2.0.11: smooth phone map, compact switch row" and push.
