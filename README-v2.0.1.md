# Economic Atlas v2.0.1

Built on `48a93c4f`. Makes the trade sections consistent across country pages, and fixes a release check.

## Pages

- **Exports and imports tiles** on Brazil, Canada, Denmark, Mexico, Poland and South Korea. These six had exports and imports charts from v1.9.139 but tiles only for the trade balance. Each tile uses the same format and source line as the page's trade balance tile, as on China and Japan.
- **UK quarterly current account** now has a tile in the trade section and its own indicator page, `indicators/uk-current-account-quarterly` (ONS AA6H, % of GDP, latest Q2 2026: -2.5%), with an embed, a preview image, a sitemap entry and a methodology row under External. UK pages now say 30 live indicators.
- `tools/coverage_gate.js`: 0 chart-only gaps (was 13 on 7 pages).

## Repository

- `README.md` rewritten for v2.0: it described the site at v1.0 (18 countries, admin-only features, pipeline fixes from 2025). It now covers the 62 economies, the pages, how the data pipeline and release checks work, and how to run the site locally.

## Release checks

- `tools/invariants_gate.js`: removed the entry that allowed Poland's trade balance to be in euros. Poland's trade has been in zloty since v1.9.139, so the entry made the check fail. 3,531 checks, 0 failures.

## Testing

- `generate_indicator_pages.py`: 1,109 indicator pages, 1,109 embeds, 14 rankings, no warnings.
- `html_gate.py` 0 failures; `generated_pages_gate.py` ok; `tile_pages_gate.py` 971 tiles, all with a page; `og_gate.py` 1,109 pages, all with a preview image; `sitemap_gate.py` 1,199 entries, no gaps; `country_surfaces_gate.py` 0 gaps; `history_depth_gate.py` 0 findings; `fx_floor_gate.py` 0 mismatches; `citation_provider.py` 0 mismatches.
- Rendered in jsdom on all 62 country pages: `invariants_gate.js` 0 failures, `coverage_gate.js` 0 gaps, `sampledata_gate.js` 0 failures.
