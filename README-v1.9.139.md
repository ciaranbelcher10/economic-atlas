# Economic Atlas v1.9.139

Built on `4d8be88`. Final pre-launch package: data fixes, the save, open and export faults found in testing, and one number format on every surface.

## Save, open and export (from Ciaran's testing, 16 Nov 2026)

- **Compare, Customise & export would not download in Bar view.** The filename step read a variable that is private to the page script, threw, and left both buttons on "Exporting…". PNG and SVG now download in Bar and Line views, with and without Per capita.
- **Compare CSV had an empty Date column.** Bar rows now carry their year (or "2016 to 2025" for a change). US$ figures now name their unit, and a per-person line download is in whole currency units, as the bar download already was.
- **Every CSV now names its value column** after the chart and its unit (for example "GDP level (US$ millions)") instead of "Value". This applies on all 73 pages that offer Download data.
- **Compare saves now keep every editor setting** (titles, legend, theme, log scale, reference line, ticks, label angle, annotations), plus Per capita, the country colours and the series each country used. Reopening on Compare puts all of them back.
- **A Compare save opened in Chartmaker drew nothing.** Chartmaker read none of Compare's settings and turned a year-only range into "Jan 2025 to Q4 2024". It now opens as the same chart type over the whole saved year, with the title, theme, sort, colours and Per capita. A note under it says that Compare bars are whole-year figures while Chartmaker bars show the latest month or quarter. A Compare "change between years" view opens as a line over those years.
- **Chartmaker saves opened on Compare** now carry the year, Per capita, sort and every shared style setting.
- **Country pages and Dashboard saves** now keep every editor setting and the three switches. Reopening sets the switches back first, so the chart shows the same figures as when it was saved. Chartmaker reads these saves too (type, title, colour, theme, switches).
- **Dashboard Download data and Customise & export ignored the switches.** Both, and the fullscreen chart, now use the figures on screen (US real GDP with all three switches on: $70,054 per person for 2025, as on the tile).
- **Per capita paragraph appeared on unrelated Compare metrics** (inflation and others). The popover is reused, and the paragraph from a GDP popover was never removed. It now appears only where Per capita changes the figure.
- **Switch order** is now Convert to USD$, Adjust for inflation, Per capita on all 62 country pages, Chartmaker, the Dashboard and the indicator pages, and in the info popovers.
- Empty Open list text on country pages corrected ("No saved charts yet. Open any chart's Customise & export, then Save chart.").

## Data

- Trade for Brazil, Canada, Denmark, South Korea and Mexico: IMF international trade in goods, monthly from 2006, exports and imports added. Checked against the IMF over 30 months for each country.
- Poland trade in zloty (Eurostat in euro × ECB monthly rate), exports and imports added. Matches in all 141 months.
- Unemployment for Morocco, Indonesia, Pakistan and Peru: IMF World Economic Outlook (LUR), national definition.
- Source tables on Compare and in data-metric-sources.json updated for all of the above. `citation_provider.py`: 0 mismatches.

## Display

- One number format: indicator-page headlines now show bn and tn to one decimal, as every tile does (A$2.9tn, £3.1tn, R$13.2tn). Ranking table cells keep two decimals. JS and Python formatters agree on 216 test cases. KIT_VERSION 17.
- Population change under a thousand reads "+496 people".
- "$" alone is shown as "US$" outside the US and dollarised economies.
- Australia's year-on-year CPI tile says it is quarterly.

## Known and left as is

- 58 unused gdp_real info entries remain in page code. Nothing displays them.
- ALLOW_SHRINK entries for v1.9.139 (trade in five scripts, unemployment in four) come out after the first data run. Switzerland's stays until an OECD group-E run.
