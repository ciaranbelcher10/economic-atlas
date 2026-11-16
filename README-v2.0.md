# Economic Atlas v2.0

Built on `d546c398`. Launch release: the last data-quality items found after v1.9.139 went live.

## Data

- **Euro area exports, imports and trade balance now run from January 2002.** They came from Eurostat's teiet010 and teiet110 tables, which keep only the latest twelve months, so the euro area charts showed one year where member states show decades. They now come from Eurostat ext_st_easitc (euro area EA21, trade with countries outside the euro area, seasonally and calendar adjusted, EUR million): 297 months, January 2002 to September 2026. The twelve months the two tables share are identical (October 2025 to September 2026, every value). If ext_st_easitc fails on a data run, `fetch_ez.py` falls back to teiet, and keeps the stored history when it is longer and as current.
- `tools/migrate_v20_data.py` puts the full series into `data-ez.json` now. It stops without writing if any stored month differs from Eurostat.
- Source text on the euro area page, Compare and in `data-metric-sources.json` names the new table and drops the note that the chart covers about twelve months. The methodology page now lists the three series as seasonally adjusted (was "Not stated").

## Display

- **Poland's methodology note is back.** It said the trade balance was in euros, which stopped being true in v1.9.139, so the generator withheld it. It now says that exports, imports and the trade balance are Eurostat figures converted to zloty at each month's ECB reference rate, and that Convert to USD$ uses each year's average PLN/USD rate. Its check covers all three series.

## Checked and left as is

- Trade for Brazil, Canada, Denmark, South Korea and Mexico is converted to local currency at each month's own rate, not one current rate. Brazil checked against the IMF for June 2010, March 2018 and June 2026: stored value equals IMF US$ figure times that month's rate in all three. The data-run log line "converted using 5.4746" names only the latest rate.
- Indicator pages say "the exports rose" and similar on every country. Wording is unchanged in this release.

## Testing

- `fetch_ez.py` run in full in a scratch copy: 297 months for exports, imports and the balance. Run again with ext_st_easitc forced to fail: the stored 297-month series is kept.
- `migrate_v20_data.py` run twice: same result, only the three euro area trade series change.
- `generate_indicator_pages.py`: 1,108 indicator pages, 1,108 embeds, 14 rankings, no warnings (the Poland warning is gone).
- `html_gate.py`: 0 failures on all four checks. `generated_pages_gate.py`: ok (0 failures). `citation_provider.py`: 0 mismatches.
