# v2.0.4: production list, Phase 1 (fix existing site issues)

## What changes
1. **Country-page notes corrected against the data.** 18 footer or section-note sentences said a series was missing when the page shows it:
   - UK and US: 10-year yield (the UK footer flagged after launch).
   - Canada, Japan and the Eurozone: 10-year yield.
   - Brazil, Canada, Denmark, Mexico and South Korea: exports and imports.
   - Poland: policy rate and participation.
   - Morocco: exchange rate.
   - Singapore: 10-year yield.

   All 24 older footers are rewritten in plain, declarative wording, and "not an oversight" and "known gap, not a decision" are gone.
2. **New gate, `tools/coverage_claims_gate.py`.** It reads every "not available" sentence on every country page and fails if the data file carries that series. It reports 18 failures on the old main and 0 after this release.
3. **Terms of Service.** Four colloquial asides are rewritten, and one line is added: "Please check any figure against its original publisher before relying on it." The page already had the as-is, no-advice, liability and England & Wales clauses.
4. **Sign-up form.** It now shows "Creating an account means you accept the Terms of Service and Privacy policy", with two buttons (no links in running text). This appears in Sign up mode only, on all 1,199 pages with the login window and in the indicator page generator.

## How it ships
As a migration script, not as whole files, so it does not overwrite v2.0.3's chartmaker.html and compare.html, or data-bot commits. It is idempotent. Rehearsed on a fresh clone of main (feda26c): the result was byte-identical to the verified tree, and a second run changed 0 files.

## Deploy (Claude Code), after v2.0.3
1. Verify the sha256 of economic-atlas-v2.0.4.zip, run `git pull`, then unzip at the repo root.
2. Run `python3 tools/migrate_v204.py` (expect about 1,201 files changed). Run it again (expect 0).
3. Run `python3 tools/coverage_claims_gate.py` (expect 0 failures).
4. Run `python3 tools/html_gate.py` and `python3 tools/generated_pages_gate.py` (expect 0 failures).
5. Run `NODE_PATH=/tmp/node_modules node tools/test_signup_terms.js` (expect 0 failures) and `tools/test_signup_existing.js` (expect 0 failures).
6. `git add -u && xargs git add < FILES.txt`, then commit "v2.0.4: correct coverage notes, Terms wording, sign-up terms notice" and push.

## Not changed (decided earlier)
- No "not financial advice" line in footers or exports (decision of 29 Oct). The Terms cover it.
