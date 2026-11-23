# v2.0.7: Chartmaker axis fixes, and the Israel guard exception removed

1. **A cleared y-axis title came back as "%" after save and reopen.** An empty saved title was read as "never set", so the automatic title was applied again. Saves now record whether the title was edited (`yAxisTitleTouched`). Older saves behave as before, so to keep a cleared title on one of them, clear it and save once more.
2. **Date labels drifted on long charts** (Jan 1971, Jan 1978, Dec 1984 … Sep 2026). Monthly or quarterly charts spanning 3 years or more now put their labels on year starts (Jan 1980, Jan 1990 …). Short ranges and "Year only" labels are unchanged.
3. **fetch_il.py:** the v2.0.6 ALLOW_SHRINK entry is removed, because data-il.json now ends at 2025 and the change has landed.

New test: tools/test_v207_chartmaker_axis.js (6 checks). It fails 3 checks on the old chartmaker.html.
No regressions: test_v203_bar_colours (11/0), test_v203_compare_bar_colours (8/0), test_signup_terms (0 failures), html_gate (0), generated_pages_gate (0). test_chartmaker_followups (1 failure) and test_chartmaker_toggles (a ReferenceError) fail in the same way on unchanged main.

## Deploy (Claude Code)
1. Verify the sha256, run `git pull`, then unzip at the repo root.
2. Run `python3 tools/html_gate.py` and `python3 tools/generated_pages_gate.py` (expect 0 failures each).
3. Run `NODE_PATH=/tmp/node_modules node tools/test_v207_chartmaker_axis.js` (expect 0 failures).
4. `git add -u && xargs git add < FILES.txt`, commit "v2.0.7: Chartmaker axis title and year-start date labels; drop Israel guard exception" and push.
