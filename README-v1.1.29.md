# v1.1.29 — Complete currency architecture fix + Compare fix

46 files. This is the FULL package — upload every file via the GitHub web
UI, overwriting existing files at the same paths. No `.yml` changes needed.

**Important:** a fresh clone at the start of this session showed that
NONE of the fixes from prior sessions (Argentina fx/CPI, Israel/Morocco
debt sources, Denmark currency upgrade, the original currency safety-net,
Compare's REGION_GROUPS) had actually been deployed yet — only the
INDEC CPI, Sweden HICP, Thailand REO CPI, and the three forecast-year JSON
strips (data-sg/cl/co.json) were live. So this package includes
everything, reconstructed and re-verified from scratch against a fresh
clone, rather than assuming partial deployment.

---

## 1. Currency safety-net fix — 32 country pages + compare.html + dashboard.html

Root cause: several countries' `gdp_level` was sourced from World Bank in
USD while `gdp_real` came from a different, genuinely local-currency
source — so "Dollarise" was converting an already-dollar figure through
the local FX rate a second time. Fixed with a guard (`isAlreadyUSD`) that
checks the actual unit string of each series before converting.

**This version is series-aware, not just page-aware** — a second issue
surfaced during verification: Australia, Canada, Mexico, South Africa, and
Brazil's own currencies (AUD/CAD/MXN/ZAR/BRL) all happen to use the `$`
glyph too, and their `gdp_level`/`gdp_real` genuinely ARE local currency
(same solid IMF IFS series family used for the newly-fixed countries) —
so a blanket "anything starting with $ is already USD" rule would have
incorrectly stopped Dollarise from converting these five countries'
GDP figures at all. But `trade_balance` on those same five pages really
is USD-denominated (OECD's "667S" family), and still needs the normal
protection. So the guard only treats `$`-prefixed `gdp_level`/`gdp_real`
as local-currency when the page defines its own `NATIVE_SYMBOL_OVERRIDE`
(a pre-existing per-country display mechanism already used to show "A$",
"C$", "R", etc. instead of a bare "$") — every other `$`-prefixed series,
on every page, is still correctly treated as genuinely USD.

**Also found and fixed:** Chile and Colombia had a `NATIVE_SYMBOL_OVERRIDE`
of `"CLP$"` / `"COL$"` that was actively wrong — their `gdp_level`/
`gdp_real` are genuinely USD (no live peso source was ever wired in,
despite searching), so that override was falsely relabeling dollar figures
as pesos, implying a conversion that never happened. Removed the override
on both pages so they now correctly show bare `$`, matching the genuinely-
USD data underneath.

## 2. Proper root-cause fix for six countries — genuine local-currency GDP

Rather than convert an existing multi-decade USD series using today's
exchange rate (which would badly distort history for currencies that have
moved a lot, like the Lira or Peso), sourced the genuine local-currency
nominal-GDP sibling series from the same IMF IFS / Eurostat families
already providing `gdp_real`:

- **Turkey** — `NGDPSAXDCTRQ` (TRY)
- **Argentina** — `NGDPSAXDCARQ` (ARS; note SA vs gdp_real's NSA, a minor
  adjustment-convention mismatch, not a currency one)
- **Indonesia** — `NGDPSAXDCIDQ` (IDR)
- **Poland** — `NGDPSAXDCPLQ` (PLN)
- **Denmark** — `CLVMNACSCAB1GQDK` (real) / `CPMNACSCAB1GQDK` (nominal),
  both Eurostat DKK. This is also a data-quality upgrade, not just a
  currency fix: Denmark's `gdp_real` was previously annual, lagged Penn
  World Table data; it's now live quarterly DKK matching `gdp_growth`'s
  own cadence.

All verified live via search before wiring in. Old World-Bank-USD
`gdp_level` kept as a fallback in each script, clearly labeled as USD.

**Argentina's `fx_raw` also fixed**: the series ID (`CCUSMA02ARM618N`) was
simply wrong/nonexistent on FRED, causing a 400 error on every run.
Replaced with the correct one, `ARGCCUSMA02STM`.

**Israel and Morocco's `debt_gdp`** also fixed this session (unrelated to
currency, but bundled in since both were still on stale World Bank data
frozen since 1999/2011 respectively): Israel now sources from BIS
(`QILGAM770A`, general government), Morocco from IMF MENA REO
(`MARGGDGDPGDPPT`, general government, with the future-year forecast
filter applied since this series bundles IMF projection years). Old World
Bank series kept as labeled-stale fallbacks on both.

## 3. Countries checked, confirmed correct, or confirmed still USD by necessity

- **UK, Eurozone, Germany, France, Italy, Spain, Netherlands, Ireland,
  Japan, South Korea, India, US** — all confirmed already in their own
  currency, no action needed.
- **Chile, Colombia, Norway, Thailand** — confirmed still USD, no
  confirmed-live local-currency alternative found despite searching
  (Norway's Eurostat mirror is in Euros, not Krone; the others' OECD
  mirrors are stale since 2023). Safety-net-protected, not
  local-currency-by-default. Worth another look with more time, likely
  needing to go direct to each country's central bank/statistics office
  the way Argentina's CPI fix ultimately did.
- **Switzerland, Sweden, Singapore, Morocco, Israel (gdp_level)** —
  honestly labeled World Bank USD, not mislabeled, just never sourced
  locally.

## 4. New countries missing from Compare — found and fixed

`compare.html`'s data-loading layer (`FILES`, `COUNTRY_LABEL`,
`COUNTRY_COLOR`, `ISO_OF`) already had all 9 new countries correctly
wired. The actual bug: `REGION_GROUPS` — the array `renderCountryPicker()`
iterates to build the selectable country modal — was never updated when
the 9 countries were added. Fixed and verified programmatically: every
country in `FILES` is now in exactly one region group, zero missing, zero
extra.

## Verified before packaging
- All 12 touched `fetch_*.py`: `py_compile` clean.
- All 34 touched HTML files (32 country pages + compare + dashboard):
  tag-balance clean, every inline `<script>` block passes `node --check`.
- Confirmed exactly one occurrence of every new guard function per file.
- `REGION_GROUPS` programmatically diffed against `FILES` — exact match.
