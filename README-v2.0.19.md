# v2.0.19: Convert to PPP on the indicator pages (Phase 4 complete)

- The GDP, real GDP and GDP per capita pages for every economy with checked PPP factors (180 pages) get Convert to PPP. It is joined to Convert to USD$ where that switch exists, and the two are never on together. The rules are the same as everywhere else (ppp.js): each year at its own factor; real GDP at its price base year's factor, so growth is unchanged. A note below the switches explains the conversion and names any years left out. Pages for the euro area and Taiwan, which have no factor, get no switch.
- Chartmaker: a long series name in the Data panel ends in an ellipsis instead of being cut mid-word. Hovering shows the full name.
- generate_indicator_pages.py: KIT_VERSION 18, PPP_VERSION 1, PPP button and config. indicator-kit.js: PPP conversion, note, Int$ symbol, and the USD$/PPP exclusion.
- Tests: tools/test_v219_indicator_ppp.js (generated pages with live data), tools/test_v216_chartmaker_ppp.js (18 checks).
