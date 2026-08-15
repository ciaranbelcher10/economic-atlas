# Update package — 15 Aug 2026 (fixes CPI gaps + follow-up integrity sweep)

21 files. Upload each one via the GitHub web UI, overwriting the existing file
at the same path in the repo root. No new files, no deletions.

## 1. Future-dated IMF forecast points stripped from 3 countries
`fetch_sg.py`, `fetch_cl.py`, `fetch_co.py` — added a filter so any FRED
observation dated beyond the current calendar year is dropped before it's
written to the JSON. Some IMF REO/WEO-mirrored FRED series (Singapore's
gdp_growth/current_account/cpi; Chile and Colombia's debt_gdp/deficit) bundle
IMF forecast years (out to 2030/2031) into the same series as real
observations with no flag distinguishing the two. This is what was making
compare.html / dashboard.html anchor to "2031" as the latest year.

`data-sg.json`, `data-cl.json`, `data-co.json` — hotfixed directly: the
2027–2031 forecast points already baked into the live files have been
stripped, and `new_points_meta`/`new_points` updated to match. Self-heals
correctly on the next Actions run now that the fetch scripts are patched too.

## 2. Wrong-country trade-partner data — 12 pages
`argentina.html`, `indonesia.html`, `poland.html`, `sweden.html`,
`switzerland.html`, `singapore.html`, `thailand.html`, `turkey.html`,
`austria.html`, `ireland.html`, `denmark.html`, `norway.html` — the
trade-partner map widget on each of these was fetching a **different real
country's** live UN Comtrade file and displaying it as their own (8 fetching
South Korea's, Austria fetching Germany's, Ireland fetching the
Netherlands'). Fixed by pointing each page at its own (currently
non-existent) `data-XX-trade-partners.json`, so the fetch 404s cleanly and
falls through to the honest, country-specific illustrative fallback data
+ disclosure banner every one of these pages already had built in.

This was a separate bug from the "wrong data-XX.json" one found earlier in
the day — same root cause pattern (copy-templated, never corrected), but a
different fetch call, in a script block that wasn't in the original audit.

## 3. CPI gaps

- **Argentina** (`fetch_ar.py`, `argentina.html`): tried everything before
  landing on this. OECD's live prices system returns nothing for Argentina.
  Every FRED mirror of Argentine CPI is stale (last updated 2024–2025).
  Argentina's own government open-data API (`datos.gob.ar`) looked
  promising but turned out to be frozen since mid-2025, orphaned by a
  2023-24 ministry restructuring — confirmed via a live test call (the API
  itself works, but that specific catalog stopped being fed). Landed on
  **INDEC's own CSV** (`serie_ipc_divisiones.csv`) — Argentina's national
  statistics office, publishing directly, confirmed genuinely current via
  INDEC's own press releases (through April 2026 as of this build). This is
  a better, more authoritative source than any mirror, but its exact column
  layout couldn't be verified before shipping — the sandbox used to build
  this can't reach indec.gob.ar (network egress is allowlisted to dev
  domains only; confirmed via `x-deny-reason: host_not_allowed`, not the
  site itself). So the parser is defensive: it finds the "Nivel general"
  column by header text rather than a hardcoded position, tries both comma
  and semicolon delimiters, and falls back to OECD's live system if it
  can't make sense of the file. **Check the Actions log on the first real
  run** — look for `[indec-ipc]` lines to see exactly what it found. If it
  fails, cpi falls through to OECD (which currently also fails for
  Argentina) and stays a disclosed gap rather than showing something wrong.
  The footer text has been updated to reflect this new attempt honestly
  rather than claiming it's confirmed working.
- **Sweden** (`fetch_se.py`): OECD's live prices system was returning nothing
  for Sweden specifically. Added a verified fallback to Eurostat's HICP
  all-items series for Sweden (`CP0000SEM086NEST`, via FRED), same pattern
  already working for Germany and Austria, with a YoY transform.
- **Thailand** (`fetch_th.py`): added a verified fallback to the IMF
  Asia-Pacific REO CPI series (`THAPCPIPCPPPT`), same family already used for
  Singapore. Also added the same future-year forecast filter as fix #1 above,
  since this series carries the same IMF-projection-years issue.

## Verified before packaging
- All 6 `fetch_*.py` files: `py_compile` clean.
- All 12 edited HTML files: tag-balance clean, every inline `<script>` block
  passes `node --check`.
- Diffed every file against a fresh clone — confirmed each HTML edit is
  exactly the intended lines, nothing else changed.
- Cross-checked several headline figures (Argentina inflation, Switzerland
  unemployment) against current real-world sources — in line.
- Confirmed indec.gob.ar returns a real (non-404) response and INDEC's
  press releases show genuinely current monthly IPC releases.

## Not verified — needs the real Actions run or a browser pass
- **fetch_ar.py's INDEC CSV parsing** — this is the one piece of this whole
  update that's genuinely unverified end-to-end, because the exact CSV
  layout couldn't be inspected before shipping. It's written defensively
  and fails safe (falls back to OECD, then to a disclosed gap) rather than
  silently feeding wrong numbers if the parse doesn't work — but check the
  first Actions log for `[indec-ipc]` lines before trusting the Argentina
  CPI chart.
- Actually clicking "Make it real" / "Dollarise" live on each of the 9 new
  country pages. Source-level, the logic looks correct and 8 of 9 countries
  now have `gdp_real` present with the corrected data feeding it (Singapore's
  disabled button is genuinely correct — it has no `gdp_real` series at all,
  not a bug). Worth a quick click-through once this is deployed to confirm.
- Chart panel rendering/scale on the live pages.
