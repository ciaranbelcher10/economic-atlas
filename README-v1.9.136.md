# v1.9.136: text review, pass 2 (every country page)

Applies the v1.9.135 standard to the text pass 1 left alone: tile source lines, the (i) text, chart descriptions and the country-specific section notes, on all 62 country pages. No fetch scripts, data files or workflow YAML change.

**Tile source lines.** Each tile shows its publisher and series code only (eaShortSrc), so tiles are the same height whatever the source string says. Turkey's debt tile, for example, read "IMF World Economic Outlook (GGXWDG_NGDP / GGXCNL_NGDP) · general government, % of GDP, annual, actual years only. Turkey is neither an EU nor EEA/EFTA member, ..." and now reads "IMF World Economic Outlook (GGXWDG_NGDP / GGXCNL_NGDP)". The (i) and the chart keep the full source line. Checked in jsdom across all 1,664 tiles: longest 87 characters, median 25.

**(i) text and chart descriptions.** The bold definition stays; later sentences stay only if they stop a misreading (the EU-harmonised index differs from the national CPI; a series is not seasonally adjusted, so quarters swing). Removed: why a source was chosen ("neither an EU nor EEA/EFTA member, so ..."), fallbacks ("falls back to ..."), reassurance ("not a sign the feed has broken", "that's real, not a data error"), and narration ("exceptionally volatile in recent years"). Toggle notes use the toggles' current names; "Make it real" (199 places) and "Dollarise" (512) are gone from the page source.

**Section notes.** All 206 rewritten to the Lithuania standard (tools/secnotes_v19136.py lists every one): 149 remain. Kept: a different headline measure, a break or start date, a missing series, a currency conversion. Removed: notes restating the source shown in the (i), data history and narration ("peaked near 28% in 2013", "Oil revenue drives the balance"), and reasons the site cannot get a series.

Also: tools/wb_check.py (World Bank comparison, one request per economy with retries).

Migration: tools/migrate_v19136.py (idempotent).
