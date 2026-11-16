# Economic Atlas v2.0.2

Built on `7b2f270b`. Fixes the Chartmaker bar chart of one measure across many countries, in the preview and in PNG, SVG and CSV exports. Found on the 10-year bond yield chart.

## Chartmaker bar chart

- **Rotated labels.** The first diagonal label ran off the left edge ("olombia"). The bars are now inset far enough for it to fit. Diagonal and vertical labels reserve the height of the longest label, so the period line under them no longer overlaps them. The canvas grows to make room and the plot keeps its size.
- **Period wording.** When some bars show an earlier period than the one chosen, as in "Colombia (Sep 2026)", the period line reads "Latest month, to October 2026" instead of "October 2026". A chart title that contains the period is updated the same way. When every bar is from the chosen period, the wording is unchanged.
- **One colour.** More than 10 countries on one measure now use one colour (#1E4566) instead of each country's own colour. A bar recoloured by hand keeps its colour. Charts with 2 to 10 countries still use ranked Mako shades.
- **Source footer.** FRED and ECB IRS cite one series code per country. When two or more countries share one of these providers, they are now grouped under it, as Eurostat and OECD already were: "FRED (UK, US, ...)". The CSV still gives each country's full series code.
- **Comparability note.** A chart of 10-year bond yields that compares Japan or the euro area with other countries now adds one line: "Note: Japan and euro area figures are month-end yields; the others are monthly averages."

## Chartmaker CSV

- The notes have one row per data column. Countries with no data are named once on their own line. Before, the file listed 62 series against 44 columns.
- Values are rounded to 4 decimal places (3.40238095238095 becomes 3.4024), and the file says so.
- The bond comparability note is included.
- **Mexico blanks (2026-03 and 2026-06):** checked against the OECD source of FRED IRLTLT01MXM156N. The OECD has no values for those months, and none for 2024-02, 2024-06 or 2025-03 either. The blanks are correct. The OECD now has 2026-10 (9.25), which the next data run will add.

## Tests

- New: `tools/test_v202_chartmaker.js` (16 checks). It draws the all-country bond chart and checks the first label, the period line clearance and wording, the single colour, the grouped sources, the note, and the CSV.
- Updated for the new behaviour: `tools/test_chartmaker_saved.js` (period wording, one colour above 10 countries) and `tools/test_chartmaker_stress.js` (the layout of the CSV notes).
- `test_chartmaker_saved` 97/0, `test_chartmaker_stress` 45/0, `test_chartmaker_mobile` 41/0, `test_chartmaker_inflation` 18/0, `test_chartmaker_title_reset` 11/0, `test_v19108` 28/0.
- Known failures that were already on main and are unchanged by this release: `test_chartmaker_followups` (1, the default for points), `test_chartmaker_toggles` (2, toggle order and the Switzerland axis), `test_methodology_gate.py` (Poland anchor, stale since the v2.0 note was rewritten).
- Full audit: `invariants_gate.js` 3,531 checks, 0 failures; `coverage_gate.js` 0 gaps; `sampledata_gate.js` 0 failures; `html_gate.py` 0; `generated_pages_gate.py` ok; `country_surfaces_gate.py` 0 gaps; `fx_floor_gate.py` 0; `history_depth_gate.py` 0; `og_gate.py` and `sitemap_gate.py` clean; `tile_pages_gate.py` 971 tiles; `citation_provider.py` 0 mismatches.
