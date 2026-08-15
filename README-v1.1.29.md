# v1.1.29 — Currency architecture sweep + Compare fix

40 files. Upload via GitHub web UI, overwriting existing files at the same
paths. No `.yml` changes needed.

**Note on what's NOT in this package:** the trade-partner wrong-country
fetch fix and the IMF-forecast-year JSON strip (data-sg/cl/co.json) were
already confirmed live in the repo when this session started — they're not
included here because there's nothing left to ship for them.

---

## 1. The root cause of the Turkey Dollarise bug — fixed everywhere, not just Turkey

**What was actually happening:** `gdp_real` for Turkey (and several other
countries) is sourced from IMF IFS in the country's own currency (e.g. TRY).
`gdp_level` was sourced *separately* from World Bank in USD. Since
`gdp_level` was already in USD, clicking "Dollarise" ran it through the
TRY/USD rate a second time — a silent, badly wrong number.

**Checked every country's currency-denominated series and found this wasn't
Turkey-specific.** Argentina, Indonesia, Poland had the identical
gdp_level-in-USD-while-gdp_real-in-local-currency mismatch. Chile, Colombia,
Denmark, Norway, Thailand have both gdp_level *and* gdp_real natively in
USD (legitimate constant-price-USD World Bank/IMF data, not a mismatch
between the two, but still not local-currency-by-default). Japan and the US
are internally consistent already.

**Two-part fix:**

**(a) Universal safety-net guard — `argentina.html` through `us.html` (32
files), `compare.html`, `dashboard.html`.** Added a check (`isAlreadyUSD` /
`isAlreadyUSDUnit`) that looks at the actual unit string of the series being
converted — not just which country it belongs to — and skips re-conversion
if it's already USD-denominated. This was duplicated identically across
every page (same as the mini-map pattern), so the same fix propagated to
all 32 country pages plus the two aggregator pages, byte-for-byte identical
function bodies confirmed before and after.

This fixes the acute bug immediately on deploy, for every country, even
before any data pipeline changes take effect.

**(b) Proper root-cause fix for the four clearest cases — `fetch_tr.py`,
`fetch_ar.py`, `fetch_id.py`, `fetch_pl.py`.** Rather than convert the
existing multi-decade USD series using today's exchange rate (which would
badly distort history — Turkey's Lira and Argentina's Peso have depreciated
by orders of magnitude over decades, so applying 2026's rate to 1990s GDP
would be nonsensical), found and wired in the genuine local-currency
nominal-GDP sibling series from the same IMF IFS family already providing
gdp_real:
- Turkey: `NGDPSAXDCTRQ` (TRY, matches `NGDPRSAXDCTRQ`)
- Argentina: `NGDPSAXDCARQ` (ARS, matches `NGDPRNSAXDCARQ` — note: SA vs
  NSA, a minor adjustment-convention mismatch, not a currency one)
- Indonesia: `NGDPSAXDCIDQ` (IDR, matches `NGDPRSAXDCIDQ`)
- Poland: `NGDPSAXDCPLQ` (PLN, matches `NGDPRSAXDCPLQ`)

All four verified live via search before wiring in. The old World-Bank-USD
`gdp_level` is kept as a fallback in each script, clearly labeled as USD in
its own text so the frontend guard from (a) correctly leaves it alone if
this fallback ever gets used.

**Known follow-up, not done in this pass:** Chile, Colombia, Norway, Thailand
still have USD-denominated `gdp_real`/`gdp_level` as their only source (not
a mismatch bug now, thanks to the safety-net guard, but not
local-currency-by-default either).

**Denmark was fixed properly in a follow-up pass** — found and verified
Eurostat's `CLVMNACSCAB1GQDK` (real, chained 2010 DKK) and
`CPMNACSCAB1GQDK` (nominal DKK), both live and quarterly through Q4 2025.
This is a genuine upgrade, not just a currency fix: Denmark's `gdp_real`
was previously annual, lagged Penn World Table data; it's now live
quarterly DKK matching `gdp_growth`'s own cadence. `fetch_dk.py` updated
accordingly, old World Bank USD series kept as a labeled fallback.

**Norway specifically checked and ruled out** — Eurostat's mirror of
Norway's GDP (`CLVMNACSCAB1GQNO`) turned out to be denominated in
**Euros**, not Norwegian Krone (Eurostat normalizes non-euro EEA members to
EUR in this series), which would have been a worse, more misleading fix
than what's currently there. OECD's own NOK-denominated series for Norway
(`NORGDPNQDSMEI`) is genuinely in NOK but stale since Q3 2023, same
dead-end pattern as several other legacy OECD MEI mirrors found this
session. No confirmed-live NOK total-GDP series found via search this
session — left as-is rather than guess.

**Chile, Colombia, Thailand** — same search effort applied, no confirmed-live
local-currency total-GDP series found (Chile's OECD MEI mirror is stale
since 2023, same pattern as Norway). These three remain on the
constant-USD Penn World Table source. Worth another look with more time,
ideally checking each country's central bank or national statistics office
directly rather than relying on FRED mirrors, the same way Argentina's CPI
fix ultimately required going to INDEC directly rather than any mirror.

## 2. New countries missing from Compare — found and fixed

`compare.html`'s country-loading layer (`FILES`, `COUNTRY_LABEL`,
`COUNTRY_COLOR`, `ISO_OF`) already had all 9 new countries correctly wired.
The actual bug: `REGION_GROUPS` — the array that `renderCountryPicker()`
iterates to build the selectable country modal — was never updated when
the 9 countries were added. They were present in the data layer and
completely invisible in the UI.

Added Turkey, Poland, Switzerland, Austria, Sweden to "Europe" (matching
the site's existing unified-Europe-column convention), Indonesia,
Singapore, Thailand to "Asia", Argentina to "South America". Verified
programmatically: every country in `FILES` is now in exactly one region
group, with zero missing and zero extras.

## Verified before packaging
- All 6 touched `fetch_*.py`: `py_compile` clean.
- All 34 touched HTML files (32 country pages + compare + dashboard):
  tag-balance clean, every inline `<script>` block passes `node --check`.
- Confirmed exactly one occurrence of the new guard function per file — no
  duplicates, no misses.
- Diffed the whole repo against a fresh clone to confirm the file list and
  scope match what's described above.
