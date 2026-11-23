# v2.0.9: follow-ups to the v2.0.8 live check

1. **Chartmaker padlocks after sign-in, the real fix.** Chartmaker's script runs in its own scope, so the sign-in code (in an earlier script) could never call applyExportGateState: `typeof applyExportGateState === "function"` was always false. The export buttons only got their state at page load, and kept the padlock until a reload. The v2.0.8 change used the same unreachable call. The gate is now exposed as `window.EATLAS_APPLY_EXPORT_GATE`, and both callers use it. New test tools/test_v209_chartmaker_signin.js signs in through the page's real sign-in code; it fails 2 of 3 checks on the v2.0.8 file.
2. **Country pickers grouped by region again**, with countries alphabetical within each region. Compare's window is back to the Country Breakdowns regions; the Chartmaker and My Dashboard picker (chooser.js) now uses the same regions and shows one flat list only while searching. The group buttons, All countries, Select all and Clear stay. chooser.js?v=4.
3. **Compare's year slider** reads "2026 so far" for the year in progress, matching the ranking.

Tests: test_v208_polish 30/0 (region and slider checks added), test_v209_chartmaker_signin 3/0, test_v203_bar_colours 12/0, test_v203_compare_bar_colours 9/0, test_v207_chartmaker_axis 6/0, test_signup_terms 0 failures, html_gate 0, generated_pages_gate 0.

## Deploy (Claude Code)
1. Verify the sha256, run `git pull`, then unzip at the repo root.
2. Run `python3 tools/html_gate.py` and `python3 tools/generated_pages_gate.py` (expect 0 failures each).
3. Run `NODE_PATH=/tmp/node_modules node tools/test_v209_chartmaker_signin.js` and `tools/test_v208_polish.js` (expect 0 failures each).
4. `git add -u && xargs git add < FILES.txt`, commit "v2.0.9: Chartmaker sign-in unlocks exports; pickers by region; slider so far" and push.
