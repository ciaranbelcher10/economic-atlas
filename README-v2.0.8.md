# v2.0.8: Chartmaker and Compare polish (from the 23 Nov live check)

## Requested
1. **Country colours are now the default** for bar charts with more than 10 countries, in Chartmaker and in Compare's Customise & export. One colour is still one click away, and saved charts keep their own choice.
2. **Export buttons after signing in.** Chartmaker's Download PNG/CSV buttons now drop their padlock the moment sign-in lands, rather than after the account profile loads.
3. **Less text above the chart.** The conversion and "how Bar works" notes sit in one collapsed "About these figures" line, which opens on click and only shows when there is a note.
4. **All countries and Clear** in the country picker (shared by Chartmaker and My Dashboard), next to G7, G20, EU, Euro area, OECD and BRICS.
5. **Square bars everywhere.** borderRadius is 0 on all 66 pages' bar charts, and the SVG exports in Chartmaker and Compare draw square bars.
6. **Compare's country picker** now has the G7, G20, EU, Euro area, OECD and BRICS buttons alongside Select all and Clear all, and lists countries in one alphabetical list. Signed out, a group fills the 4 free slots and shows the sign-up card.

## Also fixed
- **Column chart (one series over time):** labels fall on round years (1980, 1990 …), not every 7th bar (1975, 1982, 1989).
- **Horizontal chart:** grows taller so every row keeps room for its label. The 51-year Bank Rate chart overlapped before.
- **Compare, the year in progress:** shows "2026 so far" in the ranking, and the card says the figures average the readings published this year. UK CPI read 3.06% for 2026 against 3.6% for Oct 2026 elsewhere, with nothing saying why.

## Tests
- New: test_v208_polish.js (20 checks). It fails on the old files.
- Updated for square bars and the new default: test_v203_bar_colours (12/0), test_v203_compare_bar_colours (9/0).
- Unchanged and passing: test_v207_chartmaker_axis (6/0), test_compare_rules (37/37), test_signup_terms, html_gate, generated_pages_gate, coverage_claims_gate.

## Deploy (Claude Code)
1. Verify the sha256, run `git pull`, then unzip at the repo root.
2. Run `python3 tools/migrate_v208.py` (expect about 64 files), then run it again (expect 0).
3. Run `python3 tools/html_gate.py` and `python3 tools/generated_pages_gate.py` (expect 0 failures each).
4. Run `NODE_PATH=/tmp/node_modules node tools/test_v208_polish.js`, `tools/test_v203_bar_colours.js` and `tools/test_v203_compare_bar_colours.js` (expect 0 failures each).
5. `git add -u && xargs git add < FILES.txt`, commit "v2.0.8: country colours default, square bars, picker groups, notes line, label fixes" and push.
