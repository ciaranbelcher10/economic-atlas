# v2.0.12: phone map opens on touch, closes on a touch elsewhere

The map card on the homepage and on country pages (phones) now:
- **Opens the moment a finger touches it**, whether a tap or the start of a scroll (pointerdown or touchstart). It no longer waits for a completed tap.
- **Never opens a country with the opening touch.** A click within 0.7s of opening is held back. Once the map is open, tapping a country opens its page (checked: Brazil opens /brazil).
- **Closes smoothly when you touch anywhere else on the page**, from the first touch rather than a completed click. It still closes instantly, unseen, once scrolled fully off screen. Reduced-motion still turns the animation off.

Measured in Chromium at 390px with real touch input, sampled every 60ms. The UK map opens 130, 157, 179, 187, 189, 190 and closes 163, 141, 133, 131, 130. The homepage opens 190 to 323 and closes the same way. A scroll gesture starting on the map opens it.

The cache-busters are bumped together on every page and in the generator (mobile.css?v=51, mobile.js?v=49) by tools/migrate_v212.py. The rehearsal on a fresh main changed 1,200 files and 0 on a second run; html_gate and generated_pages_gate report 0 failures.

## Deploy (Claude Code)
1. Verify the sha256, run `git pull`, then unzip at the repo root.
2. Run `python3 tools/migrate_v212.py` (expect about 1,200 files), then run it again (expect 0).
3. Run `python3 tools/html_gate.py` and `python3 tools/generated_pages_gate.py` (expect 0 failures each).
4. `git add -u && xargs git add < FILES.txt`, commit "v2.0.12: phone map opens on touch, closes on touch elsewhere" and push.
