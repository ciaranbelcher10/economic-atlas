# v1.9.135: text review, pass 1

The site's text names, defines and explains the figures. It does not argue for the site, describe its roadmap, say who it is for, or say what it does not do. Full list with before and after: claude/v1.9.135-text-review.md in the project.

No fetch scripts, data files or workflow YAML change.

**Every country page** (tools/migrate_v19135.py, idempotent):
- Removed: the Miscellaneous note, every "On the roadmap" note and the map key's "On the roadmap" (now "Not covered"), the Markets section note ("market prices, not government statistics ... never a news aggregator"), the footer's productivity coverage line and "Ideas or corrections are welcome."
- Footer: "Figures are the latest published and may be revised."
- Section notes: no "we have not yet found", no "a known gap, not shown here rather than estimated", no "so estimates and projections never appear as data", no sentences narrating the chart ("X usually imports more goods than it exports"), and no comparison with the IMF's timing.
- Australia's labour note said unemployment was quarterly from a FRED mirror; it has been OECD monthly since v1.9.131. Removed.
- (i) text: the ECB rate drops "one of the ECB's three main policy rates"; GDP per person source reads "GDP ÷ population (World Bank), calendar years"; the partners map reads "Goods trade only. Services are not included."
- Lithuania, as the template: the Inflation and Labour section notes are gone, since the (i) on those charts already says it.

**About:** "Data and accuracy" replaces "These are not our numbers"; no audience sentence and no "no commentary"; sources are now a laid-out list: international bodies with what each supplies, FRED as a distributor, and the national statistics offices and central banks for the 32 economies read directly (the other economies come through the international bodies). UN Comtrade stays unnamed on About, as the gate requires.

**Methodology:** "Data first, no commentary" removed (7 sections); lede fits one line; "Where the data comes from", "Seasonal adjustment", "How often it updates", "Known limitations" and "Questions about a specific number" rewritten plainly; the inflation toggle is called "Adjust for inflation", not "Make It Real".

**Home:** no "No commentary, no forecasts"; the commentary FAQ is removed from the page and its JSON-LD; the other FAQ answers match their JSON-LD.

**Markets, Dashboard, Compare, Chartmaker, Calendar:** notes cut to what a reader needs (spread definition, end-of-month dates, annual World Bank rates); instructions for obvious controls removed. Chartmaker's colour note no longer says "Mako gradient".

**Gates:** generated_pages_gate.py checks the new About structure (caveat wording, every international source in the data files, every national publisher named on a country page); doc-page tests expect 7 Methodology sections. generate_indicator_pages.py writes the shorter key-figures note.

**Pass 2 (v1.9.136):** the remaining country-specific section notes on the other 61 pages, by hand, to the Lithuania standard.
