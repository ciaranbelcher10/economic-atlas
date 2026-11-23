# v2.0.6: follow-up to the v2.0.5 live check

1. **Israel debt still showed 2026 (74.5%).** The v2.0.5 fetch ran (the 21:16 data run), but series_guard kept the old series, because the new one ends earlier (2026 -> 2025). That is the guard's job, and an intended change needs an ALLOW_SHRINK entry. fetch_il.py now has one for debt_gdp. Remove it in the next release, once data-il.json ends at 2025.
2. **Israel debt tile and chart said "World Bank".** The series is BIS. They now credit "BIS credit statistics · % of GDP, end of year". The info popover, indicator page and Compare were already correct.
3. **Convert to USD$ popover wording.** On 14 country pages and in the metric sources, "converts each historical point using that point's OWN contemporaneous X rate" now reads "converts each point at that period's own X rate".

Rehearsed on a fresh clone of main (ed0733c): the result is byte-identical to the verified tree, and a second run changes 0 files. html_gate, generated_pages_gate and coverage_claims_gate all report 0 failures.

## Deploy (Claude Code)
1. Verify the sha256, run `git pull`, then unzip at the repo root.
2. Run `python3 tools/migrate_v206.py` (expect 17 files), then run it again (expect 0).
3. Run `python3 tools/html_gate.py`, `python3 tools/generated_pages_gate.py` and `python3 tools/coverage_claims_gate.py` (expect 0 failures each).
4. `git add -u && xargs git add < FILES.txt`, commit "v2.0.6: Israel debt guard exception and BIS source; USD popover wording" and push.
5. Optional: trigger the data workflow by hand rather than waiting for the hourly run.
