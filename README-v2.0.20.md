# v2.0.20: new-country tooling brought up to date (Phase 5 groundwork)

No page, data file or workflow changes. Tools, two gates, one pipeline script, and the manual.

- `tools/build_country_page.py`: runs again (it had stopped on the per capita, population and PPP keys
  and on the v2.0.4 footer). Writes today's page layout; generic blocks are lifted from the template so
  later migrations carry over.
- `tools/test_build_country_page.py` (new): rebuilds all 29 countries that have a spec and compares them
  with the live pages. Result: 0 structural differences.
- `tools/add_country.py`: wires about 14 surfaces that were hand-edited for every country since v1.7.4,
  every country count sitewide, and a new Compare colour (the palette was full at 62).
- `tools/country_surfaces_gate.py`: checks those surfaces plus the workflows and OECD rotation.
  10,729 checks, 0 gaps.
- `send_calendar_alerts.py`: COUNTRY_SLUGS now covers all 62 economies. Fixes Pakistan's alert emails,
  which showed the country name without a link.
- `tools/invariants_gate.js`: accepts the PPP factor series (it had failed 60 checks since v2.0.16).
- `tools/sampledata_gate.js`: page count from its ISO table instead of a fixed 62.
- `docs/new-country-build-manual.md`: v2.0.20 section.

Rehearsal: a pretend 63rd economy (Kenya, on Vietnam's data) went through add_country, the page
builder, the generator and every gate in a scratch copy, all clean, including invariants_gate rendering
the page in jsdom.
