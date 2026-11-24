# v2.0.14: homepage map card on phones matches the country pages

On phones the homepage map is now the country-page map card:
- **Caption above the card.** "All 62 economies. Tap or click a coloured country to open its data." moves out of the card, as on the country pages (mobile.js moves the element on phones only).
- **130px closed, 340px open.** The whole world map scales with the card (the SVG has a viewBox), so the closed card shows the full map rather than its top half.
- **Legend at the foot when open.** The legend and zoom hint show only when the card is open.
- **One motion each way.** The card's height is fixed and max-height crops it, so mobile.js's open and close is the only motion. Measured in Chromium at 390px, every 50ms: 130, 195, 291, 319, 331, 338, 340 open; 275, 196, 158, 139, 133, 131, 130 closed.

Desktop is unchanged: the caption stays inside the card, which is 642px tall at 1366px wide.

The cache-busters are bumped together (mobile.css?v=53, mobile.js?v=51) by tools/migrate_v214.py. The rehearsal on a fresh main changed 1,200 files and 0 on a second run; html_gate and generated_pages_gate report 0 failures.

## Deploy (Claude Code)
1. Verify the sha256, run `git pull`, then unzip at the repo root.
2. Run `python3 tools/migrate_v214.py` (expect about 1,200 files), then run it again (expect 0).
3. Run `python3 tools/html_gate.py` and `python3 tools/generated_pages_gate.py` (expect 0 failures each).
4. `git add -u && xargs git add < FILES.txt`, commit "v2.0.14: homepage map card matches country pages on phones" and push.
