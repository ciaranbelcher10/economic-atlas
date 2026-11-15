# v1.9.134: quarterly trade converted at the right rate; tile, popover, Markets and Calendar polish

No data files or workflow YAML change.

**Quarterly trade used the wrong exchange rate (36 fetch scripts).** `_fx_rate_for_period` decided a period was a month by "7 characters with '-' at position 4", which "2026-Q1" also satisfies. So every quarter was looked up as a month, found nothing, and fell back to the latest month at or before the string "2026-Q1"; as "2026-11" sorts before "2026-Q1", that is the latest rate there is. Every quarterly trade point was therefore converted to local currency at today's rate, and Convert to USD$ converted it back at the quarter's average, so the round trip missed the published US$ figure. This is why the v1.9.133 data run did not move Brazil: the stored reais changed only by the move in the latest rate (5.4895 to 5.4746). Brazil after the run: site US$22.1bn / 21.5bn / 21.4bn for 2026 Q1-Q3; FRED US$21.2bn / 19.8bn / 20.1bn. A month is now "YYYY-MM" with digits after the dash. Replaying the stored figures through the fixed function returns FRED's figures to the cent. `tools/test_trade_fx.py` gains the quarter cases that would have caught it (and its annual case now expects the v1.9.133 annual mean); 0 failures. The trade series are reconverted from fresh US$ data on the next data run.

**Exchange-rate check after the v1.9.132 run passes.** Germany's 2024-01 rate is 1.08989, FRED's monthly average (EXUSEU) for January 2024 is 1.0899. The 1.0905 in the handover was the ECB reference average, a different fixing.

## Front end

1. **Space before (i).** Every tile and chart title on the 62 country pages, Compare and Dashboard now has a clear gap before its (i) button (`.infoBtn` margin 6px to .5em).
2. **Per capita note in (i), shorter and page-specific.** `percapita.js` v6: for example "Shows the trade balance per person in Lithuania, using each year's population (World Bank)." Cyprus names Eurostat. GDP adds "Uses the latest full calendar year." The note under the chart still names any year left out, so the (i) no longer repeats that rule.
3. **Bold definition in (i).** The first sentence of every (i) description (what the metric is) is bold; method notes after it stay normal weight. Country pages, Compare and Dashboard.
4. **CPI tiles say they are annual.** Headline and Inflation tiles read "CPI inflation (y/y)" (or "HICP inflation (y/y)", "CPI inflation (y/y, CSO)" for the national series), matching "CPI (m/m)". Previously 32 pages said "CPI (y/y)" and the rest just "CPI inflation".
5. **Miscellaneous tiles multiplied.** `tiles-misc` and `charts-misc` were missing from `CONTAINER_IDS` on all 62 country pages, so each toggle press or re-render added another copy of every Miscellaneous tile and chart (Lithuania went from 2 tiles to 38 in the harness). Both are now cleared before each render.
6. **Markets bond chart in dark mode.** Each bar row is a link; once visited, the browser's dark visited-link colour replaced the label colour, so those rows' names, values and dates nearly vanished. Chart links now inherit the page colour.
7. **Calendar email explainer behind a button.** "How email alerts work" now opens from an "Email alerts (i)" button next to Countries, with tighter wording. The Countries panel note no longer points "below the calendar".

Also: `tools/build_country_page.py` uses the new CPI tile title for future countries; `generate_indicator_pages.py` requests `percapita.js?v=6` (the bot regenerates indicator pages); `tools/test_v19122.js`, `test_v19125.py`, `test_v19128.js` follow the new version and wording.

Migration: `tools/migrate_v19134.py` (idempotent; already applied to the pages in this package).
