# v2.0.13: no double enlargement of the country-page map on phones

**Cause.** style.css grows the country-page map on `:hover` and `.expanded` (190px to 340px, its own 0.3s height transition). iOS keeps `:hover` on after a tap, and the page's own tap handler adds `.expanded`. So a tap gave mobile.js's opening (130 to 190) and then a second growth (190 to 340).

**Fix.** On phones the card is always 340px tall, cropped by max-height (130px closed), so mobile.js's open and close is the only motion. The open map is larger than before (340px against 190px), which makes countries easier to pick.

Measured in Chromium at 390px, with a hover and a tap, then the page's own handler fired, sampled every 50ms. UK: 130, 226, 291, 319, 334, 338, 340, and it holds at 340 through the hover and the page handler. Closing goes 244, 179, 151, 136, 132, 130. Japan is the same.

The cache-busters are bumped together (mobile.css?v=52, mobile.js?v=50) by tools/migrate_v213.py. The rehearsal on a fresh main changed 1,200 files and 0 on a second run; html_gate and generated_pages_gate report 0 failures.

## Deploy (Claude Code)
1. Verify the sha256, run `git pull`, then unzip at the repo root.
2. Run `python3 tools/migrate_v213.py` (expect about 1,200 files), then run it again (expect 0).
3. Run `python3 tools/html_gate.py` and `python3 tools/generated_pages_gate.py` (expect 0 failures each).
4. `git add -u && xargs git add < FILES.txt`, commit "v2.0.13: single smooth map enlargement on phones" and push.
