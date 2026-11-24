# v2.0.16: Convert to PPP (Phase 4)

## What it does
A fourth switch, **Convert to PPP**, converts GDP, real GDP and GDP per person to international dollars at purchasing power parity. It sits beside Convert to USD$ as one joined pill. The two are never on together: switching one on switches the other off. Adjust for inflation and Per capita work with either.

- **Colours:** PPP uses Convert to USD$'s colours. That is blue on its own, green with Adjust for inflation and purple with Per capita, on both the switch and the highlighted figures.
- **Phones:** the four switches share one row with short labels (USD$, PPP, Real, Per cap.). Desktop keeps the full names.
- **Where:** Chartmaker, Compare (a PPP button on the GDP cards, beside Per capita), My Dashboard and the 62 country pages. Indicator pages follow in the next release.

## Rules (the same on every surface, in ppp.js)
- **Nominal figures:** each period is divided by that year's World Bank PPP conversion factor (PA.NUS.PPP, local currency per international $). A year without a published factor is left out and named in the note, never converted with another year's factor or a forecast.
- **Real GDP:** priced in one year, the latest complete year with nominal GDP, real GDP and a factor. It is converted at that year's factor (real x deflator / factor), so growth equals the published real growth.
- **Scope:** the GDP family only. Trade and government money stay as published, and the note says so.
- **Checked before shown:** for each economy, our latest complete-year GDP divided by the factor must match the World Bank's own GDP at PPP (NY.GDP.MKTP.PP.CD) within 6%. An economy that fails gets no PPP figures, and its switch is greyed out with the reason given.
- **Earlier years checked too:** going back year by year, each year must stay within 10%, and PPP is not shown before the first year that fails. This catches currency changes (Bulgaria's 1999 redenomination put 1995 out by a factor of 21) and old GDP vintages. With live data, PPP starts in 1997 for Bulgaria, 2002 for Slovenia, 2008 for Slovakia, 2010 for Vietnam and 2019 for Nigeria. Most economies start in 1990. No unchecked figure is shown.
- **Latest period:** when the newest quarter has no factor yet, a Dashboard tile shows the latest year that has one, never a blank or zero.

## Data
- fetch_population.py also fetches the PPP factors and the World Bank's GDP at PPP, once a day. It uses the same guards as population: at least 50 economies, factors no more than 4 years old, and the previous figures kept on any failure.
- The figures are stored under a "ppp" key in data-population.json, which the workflow already commits, so no workflow change is needed. A PPP failure never stops the population refresh.
- merge_population.py reruns the check every hour against current GDP. It writes a "ppp" series, with factors, check and real GDP price year, into each data file that passes, and removes it from any that does not.

## Tests
tools/test_v216_ppp.js, test_v216_ppp_data.py, test_v216_chartmaker_ppp.js, test_v216_compare_ppp.js, test_v216_dashboard_ppp.js and test_v216_country_ppp.js use fixture factors, because the sandbox cannot reach the World Bank. Two older test harnesses learnt the new helper. Rehearsed on a fresh main with live World Bank data. The migration changed 1,182 pages, then 0 on a second run. PPP was written to 60 data files; the euro area (no World Bank factor) and Taiwan (not covered) are not offered. Every latest-year check is within 6% (largest: Ireland −5.7% and Cyprus +5.0%; UK +0.2%). A second merge run changes nothing. With live data: UK GDP per person Int$64,707 in 2025, Japan Int$55,646 and Bulgaria Int$44,458, in line with the World Bank's own figures. All new tests pass; html_gate, generated_pages_gate and coverage_claims_gate report 0 failures; older tests give the same results as on main.

## Deploy (Claude Code)
1. Verify the sha256, run `git pull`, then unzip at the repo root.
2. Run `python3 tools/migrate_v216.py` (expect about 1,182 pages), then run it again (expect 0).
3. Run `python3 generate_indicator_pages.py` (new cache-busters in the generator).
4. Run `FORCE_POPULATION=1 python3 fetch_population.py`, then `python3 merge_population.py`. This loads the PPP figures now rather than at the next daily run. Report the line "PPP written to N data file(s); not offered: ...", and for any economy not offered, the reason in data-population.json under ppp.countries.<name>.reason.
5. Run `python3 tools/html_gate.py`, `python3 tools/generated_pages_gate.py` and `python3 tools/coverage_claims_gate.py` (0 failures each). Run `python3 tools/test_v216_ppp_data.py` and, with NODE_PATH set to its node_modules, the five tools/test_v216_*.js files.
6. `git add -u && xargs git add < FILES.txt`, commit "v2.0.16: Convert to PPP on Chartmaker, Compare, Dashboard and country pages" and push.
