# v2.0.5: production list, Phase 2 (bug hunt) fixes

## Fixed
1. **Israel debt to GDP showed a part-year 2026 figure as annual.** The BIS series is quarterly. The fetch kept each year's last quarter, so "2026" (74.5%) was the Q2 2026 reading presented as an annual figure, on the Israel page and in Compare. fetch_il.py now keeps a year only once its Q4 is published. Earlier years are unchanged, since Q4 is the year-end reading they already used. This takes effect on the next hourly data run.
2. **My Dashboard info note.** It showed literal backslashes on the live page ("period\'s", "year\'s"). It also said every figure is converted at its own period's rate, when real GDP uses its latest year's rate (Compare's footnote already said this). Both are fixed.

## Checked and clean (no change needed)
- **Data freshness:** across all 63 data files, no series is past its normal release lag. The only older series are annual 2024 figures and Egypt's IMF trade data, which is already shown as awaiting the publisher's next release.
- **Links:** across 2,312 site pages, 0 internal links or assets point at missing files.
- **Browser:** all 78 main pages were loaded in Chromium at 1366px and 390px. There were 0 JavaScript errors and 0 cases of sideways overflow on phones. The only console noise is expected 404s for trade-partner files on the 15 economies without them, plus Indonesia's bond file.
- **Chartmaker, bar chart of 10-year yields for all countries on "Latest":** 44 bars from October 2026 plus China (September), titled "Latest month, to October 2026"; 18 economies with no 10-year series show as No data. The 16 Nov export (April 2026, 37 countries) does not reproduce. It was most likely a saved draft with the period picker set to April.
- **Supabase:** 27 accounts, all confirmed. 0 unconfirmed sign-ups in the last 7 days.

## Deploy (Claude Code)
1. Verify the sha256, run `git pull`, then unzip at the repo root.
2. Run `python3 tools/html_gate.py` and `python3 tools/generated_pages_gate.py` (expect 0 failures).
3. Run `python3 tools/coverage_claims_gate.py` (expect 0 failures).
4. `git add -u && xargs git add < FILES.txt`, then commit "v2.0.5: Israel debt year-end only; Dashboard toggle note" and push.
