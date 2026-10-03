# Audit tools

Reusable harnesses built during the fourth site audit (September 2026). They
exist because that audit's find rate was limited by tooling rather than by
remaining defect density: each new harness unlocked a category of defect that
had been invisible to greps and reading.

Nothing in here is served content or touched by any workflow. These are
developer tools, run by hand.

## Setup

They locate the repo automatically as the parent of this directory, so from a
clone you can just run them:

```
python3 tools/citation_ids.py
node tools/sampledata_gate.js
```

Override with `ATLAS_REPO=/path/to/clone` if you keep them elsewhere.

Requires `python3` and `node`. The Python harnesses need no third-party
packages. The JS harnesses that load a whole page (`coverage_gate.js`,
`test_freshness_lights.js`, `test_chartmaker_inflation.js`,
`test_dashboard_inflation.js`, `test_basis_select.js`) need `jsdom`, which is
not in the repo; without it they crash with MODULE_NOT_FOUND rather than
fail a check. From the repo root:

```
npm install jsdom --no-save
NODE_PATH=$(pwd)/node_modules node tools/coverage_gate.js
```

`data-metric-sources.json` is written as `json.dumps(d, indent=2,
ensure_ascii=False) + "\n"`. Prove that round trip on the unmodified file
before editing it.

---

## `auth_harness.js` — auth failure branches, executed

```
node tools/auth_harness.js uk.html    # one page, full table
node tools/auth_harness.js --all      # root, indicators/ and embed/, summary
```

Runs the page's real auth `<script>` under a stubbed DOM and a scripted
Supabase client, then drives sign up, log in, forgot password, set password
and log out through seven outcomes each: success, an API error, offline, an
outage (5xx), a rejected promise, a request that never answers, and a success
that arrives after the timeout. It reports whether the button was left
disabled, whether a promise rejection went unhandled, and what message a
visitor would see.

Expected: `harness errors 0, button left disabled 0, unhandled rejections 0,
raw library text shown 0` over 169 pages and 5,915 scenarios. The
`indicators/` pages are generated, so until the pipeline has regenerated them
from `generate_indicator_pages.py` they still report the old behaviour (640
unhandled rejections, 128 pages times 5 calls).

**What it found:** the live library (supabase-js 2.116.0) does not reject on a
network failure; it resolves with `AuthRetryableFetchError`. The earlier
diagnosis ("the promise rejects, so the button stays disabled") described the
code correctly but not what the library does. The live defects were the raw
library text shown to visitors ("Failed to fetch", "HTTP 503"), a request that
never answers leaving the button disabled, log out failing silently, and the
128 indicator pages carrying the same code the root-page count never included.

A `ReferenceError` for a function the page defines in a different script block
is listed separately and not counted, because the harness loads only the auth
block. Before relying on that exemption, check the call cannot run before the
defining block has executed.

## `citation_provider.py` — does each citation name the right publisher?

```
python3 tools/citation_provider.py          # mismatches and a summary
python3 tools/citation_provider.py --all    # every (country, metric) row
```

`citation_ids.py` compares identifiers, but 72 citations carry none, and a
citation can quote no id and still name the wrong publisher or the wrong
measure. This reads the provider family (HICP, OECD, IMF, World Bank,
Eurostat, INDEC, ONS, BLS and so on) from the served series label, Compare's
`SOURCE_MAP` and `data-metric-sources.json`, taking the first family each
text names, and flags rows where two surfaces disagree.

Expected once the pipeline has run with package 2A: `MISMATCH 0`. Before that
run it reports 2 (Denmark and Ireland `cpi`), because their data files still
hold the OECD national series while every citation already names HICP.
`UNCLASSIFIED` counts surfaces naming no recognised family; it is not
evidence of a correct citation. The page surface covers each country page's
chart, tile and info-panel source strings (a source read from the series label
at runtime is skipped). `INFO PANEL` checks that every page info panel carries
the popover file's text verbatim; expected `405 equal, 0 drifted`. When a
citation changes, change `data-metric-sources.json` and the page info panel
together.

First run found 18 live mismatches: 8 inflation rows (Argentina cited OECD for
INDEC data; Sweden and Poland cited OECD for HICP; Morocco, Singapore and
Thailand cited OECD for IMF data; Ireland claimed "harmonized" for a national
series), Eurozone debt, deficit and unemployment, five member trade balances,
Poland's trade balance, Germany's real GDP and growth, and Singapore's current
account. Compare's export footer now reads the popover file first, so the two
copies cannot drift apart silently again.

## `test_projection_guard.py` and `test_inflation_sources.py`

```
python3 tools/test_projection_guard.py      # 20/20
python3 tools/test_inflation_sources.py     # 18/18
```

Behavioural tests for the two shared modules. The first proves an IMF outlook
vintage cannot serve its own year as data, and that the shrinkage guard
accepts the corrected, shorter series rather than keeping the projection. The
second proves `cpi` is never filled by a measure other than HICP for the EU
members that use it, that `cpi_national` accepts only the national
methodology, and that stale or short national series are refused (a new key
has no stored version for the shrinkage guard to compare against).

## `compare_values.js` and `test_compare_rules.js` — Compare, executed

```
node tools/compare_values.js 2025                     every card, every country
node tools/compare_values.js 2025 cpi trade_balance   chosen cards only
node tools/compare_values.js --json 2025 > out.json   for before/after diffs
node tools/test_compare_rules.js                      29/29
```

`compare_values.js` runs compare.html's own script under a stubbed DOM, with
`fetch` serving the repo's data files, and prints the figure each card shows,
its measure tag and the note saying how it was built. Point `ATLAS_REPO` at an
older checkout to get the before side of a comparison; the extra columns are
blank on a page that predates them.

`test_compare_rules.js` swaps synthetic series into the page's registry to
prove the complete-year rules (averages, totals, year-end values, GDP, units,
measure filters), then checks invariants over every real country, card and
year: no series in the wrong unit, nothing for a year that has not ended, no
trend line past the latest year, and a how-it-was-built note on every value.
It needs the functions package 2B added, so it will not run against an older
compare.html.

**What it found:** Compare took the fourth quarter as a year's GDP for the US
and Japan, whose quarters are published at annual rates (US 2025 shown as
$31.42tn against $30.76tn); averaged monthly and quarterly trade figures on
one card, so quarterly publishers looked three times smaller than they were
relative to monthly ones; printed the UK and US deficits, published in
currency, as "12396.33%" and "-138928.57%" on the % of GDP card; showed 2026
as a selectable year with averages of however many months had been published;
and showed "not tracked" for every country in the policy rate card's source
popover.

## `history_walk.py` — series shape over git history

**Needs a full clone, not `--depth 1`.** On a shallow clone it reports one
revision per file and finds nothing.

```
python3 tools/history_walk.py walk     # writes tools/history_shapes.json
python3 tools/history_walk.py report   # flags drops, frequency changes, oscillation
```

Reconstructs every series' shape at every commit that touched its data file,
then flags point-count drops, frequency downgrades, start dates moving
forward, provider label changes, and series that oscillate between two states.

**What it found:** Poland's CPI serving 7 points where it should have 139,
oscillating across four shapes for weeks, plus four more live oscillations
nobody had seen. This is the tool that justifies a deep clone.

A useful follow-on question it answers: for each series, current point count
against its own historical maximum. Anything well below its own best is either
a silent truncation or a deliberate swap, and the difference is usually
visible in whether the label changed too.

## `citation_ids.py` — citation identifiers against fetch scripts

```
python3 tools/citation_ids.py
```

Compares the series identifier quoted in each `data-metric-sources.json` entry
against the identifier the country's fetch script actually uses. The sitewide
citation check matches provider *names* only, so a citation naming the wrong
FRED series from the right provider passes straight through it.

**What it found:** 17 mismatches. Colombia's employment rate popover cited the
ages 15-64 series while the script fetched the 15-and-over one, so the figure
was described as a different population than it measured. Fourteen citations
named a Eurostat dataset that does not exist. Sweden's government finance
citations had been copied from Norway's and never updated.

Expected clean result: `MISMATCH 0`, `CROSS-TABLE 0`, `UNCITED 0`, with
`compared 340 of 414 (82%)`. The remaining 74 are `NO-ID`: citations naming no
identifier the resolver can pin to a script. **`NO-ID` is not evidence of a
correct citation**, which is why the coverage line is printed.

`CROSS-TABLE` catches a citation quoting an identifier that belongs to another
country sharing the same fetch script. That is not hypothetical either: the UK
`gdp_real` citation read `ONS series ABMI (PN2) GDPC1`, with a US FRED code
spliced into it, and shipped that way. The UK used to report as 12 `UNCITED`
rows whose `used=` column named US series (`CPIAUCSL`, `UNRATE`), because
`fetch_data.py` serves both countries and the resolver matched whichever table
the regex hit first. It now resolves each country against its own table and
reads ONS codes out of the page URIs, so all 22 UK citations compare properly.

## `run_surface.py` — extract and exercise a page module

```
python3 tools/run_surface.py calendar.html EATLAS_PREFS
```

Pulls a named `window.X = (function(){...})()` module out of a page by brace
matching and writes it to `tools/_extracted.js`, so it can be run under node
with a stubbed DOM and its failure branches actually exercised rather than
read.

**What it found:** `EATLAS_PREFS` exists in seven different implementations
across 41 pages, and only `compare.html` persists anonymous preferences. It
also ruled out three suspected defects that a grep would have flagged.

## `promise_extract.py` — testable claims from prose pages

```
python3 tools/promise_extract.py methodology.html
```

Extracts visible text, splits into sentences, and flags the ones making
testable claims: universals (every, all, always, never), cadence promises,
coverage counts, provenance and forecast claims.

**What it found:** the methodology page claimed national statistical office
sourcing "for every country covered" when 10 of 36 data files have one, and
told visitors their trade data might come from a feed discontinued in April
2023 when it is current to last month.

Pay attention to both directions. Behaviour falling short of a promise is a
defect; behaviour exceeding a stale description is also a defect, because the
documentation is wrong and the site is underselling itself.

## `sampledata_gate.js` — execute every country page's `sampleData()`

```
node tools/sampledata_gate.js
```

Runs each country page's `sampleData()` under a stubbed DOM and asserts every
series is non-empty and every point numeric and finite. `node --check` is
blind to runtime errors like a deleted variable initialisation; this is not.

Expected: **32 of 32 clean, 431 series, 72,576 points, 0 nulls**, plus
`fixture series also served 404`, `fixture-only 27`, `SERVED BUT NOT ASSERTED
HERE 10`. Exit code 1 on any failure. Run it before every package.

Read those last three lines every time. `sampleData()` is the offline fixture,
not the data the page serves, so a clean pass does not mean the served data is
sound. Ten served series are absent from the fixture and therefore asserted by
nothing here: `gdp_growth_yoy` (Chile, Colombia), `gdp_level_annual` and
`gdp_real_annual` (Poland, Turkey), `gdp_real` (Singapore, Thailand),
`gdp_real_annual` (Switzerland) and `gdp_nominal` (US). Nulls are counted
separately rather than folded into "points asserted finite", because a null
passes the check without ever being asserted.

The page blocks are `"use strict"`, so function declarations do not leak to
`globalThis` and `sampleData` has to be captured from inside the eval scope.
It returns `{updated, sample, series:{...}}`, not a bare series map.

## `html_gate.py` — structural gate over every published page

```
python3 tools/html_gate.py
```

Tag balance, inline JS syntax and `ld+json` validity across root,
`indicators/` and `embed/`.

Expected: **299 pages, 1,235 inline blocks, 194 ld+json blocks, 0 failures**,
with 636 external scripts reported as not checked.

**Why it exists.** This gate used to be run by hand against the root pages
only and reported "43 pages, 307 JS blocks, 66 ld+json, 0 failures". Every
number was true and every one covered a seventh of the site. The generated
directories are where the OG card defect lived and where 33 pages were found
emitting invalid schema.org `temporalCoverage`, so a gate that skips them is
worse than no gate: it produces a clean number over ground nobody examined.
Every count it prints is "examined", not just "failed", so under-coverage
shows up in the output instead of hiding behind a pass.

## `test_guard.py` — behavioural tests for `series_guard.py`

```
python3 tools/test_guard.py
```

Nineteen branches covering what the shrinkage guard must block, what it must
allow, the stale exemption, the `ALLOW_SHRINK` override, grafting, and the
failure paths. If `tools/history_shapes.json` exists from `history_walk.py`,
it also replays the guard against every recorded shape transition.

Run this after any change to `series_guard.py`.

## `shape_harness.py` — inventory and point-in-time diff

```
python3 tools/shape_harness.py inventory HEAD     # TSV of every (country, metric)
python3 tools/shape_harness.py diff <commitA> <commitB>
```

The inventory is the artefact to read *before* forming a hypothesis. Almost
every real finding in the audit was first visible as a row that did not look
like its siblings: one country's growth rate on a different price basis, one
country's CPI starting eleven years later than everyone else's.

---

## The most important lesson from that audit

`py_compile` is not enough. It passes on an undefined name.

A bulk edit across the fetch scripts once left 21 of them calling a helper
that was never defined, which would have failed 21 country pipelines at
runtime. It was caught only by *importing* each module:

```
for f in *.py; do
  python3 -c "
import importlib.util
sp=importlib.util.spec_from_file_location('m','$f'); m=importlib.util.module_from_spec(sp)
try: sp.loader.exec_module(m)
except SystemExit: pass
" || echo "IMPORT FAIL $f"
done
```

Expected: 77 pass, 0 failures. Make this part of every gate run.

Glob `*.py`, not `fetch_*.py`. The narrower glob skipped seven root scripts,
`series_guard.py` and `generate_indicator_pages.py` among them, which is to
say it skipped the module every fetch script depends on. Note also that the
loop swallows `SystemExit`, so a script exiting at import would read as clean,
and that importing runs top-level code only, never `main()`.

The cause was a "symbol already present" check that matched the symbol inside
the replacement text it had just inserted. That same mistake happened three
times in one session. When writing a bulk migration, check for `def name`,
never the bare `name`.

## `test_trade_fx.py`: trade converted at each period's own rate

```
python3 tools/test_trade_fx.py
```

OECD "667S" trade series are USD. Fetch scripts convert them to the
country's own currency, and must do so at each period's own exchange rate.
Converting the whole history at today's spot rate rewrote every past
figure: Japan's January 2010 trade balance read 74% too high, Brazil's
2010-Q1 210% too high. Nine fetch scripts did this while seven used the
per-period helper. This fails on any `to_local = lambda v: v * fx_rate`
style converter and exercises `_fx_rate_for_period` on monthly, quarterly
and annual periods against monthly and annual rate history.

Expected: 16 per-period converters, 144 rate-selection cases, 0 failures.

It also checks that each converter only converts series fetched fresh this
run, and keeps last run's converted figures when there is no exchange rate.
Without the first, a carried-over trade series whose converted unit keeps a
bare $ (Australia, Brazil, Canada, Mexico, South Africa) would be multiplied
by the exchange rate a second time; without the second, a fresh USD series
would be published as local currency. Both paths were run end to end with
the network faked (Brazil, Japan, Sweden: normal run, no exchange rate, no
trade fetch); no double conversion occurred in 400 past commits of any of
the five $-unit countries.

The converted series keep a bare `$` unit for Australia, Canada, Mexico,
Brazil and South Africa, so every consumer's `isAlreadyUSDUnit` exception
covers `trade_balance`, `exports` and `imports` as well as GDP. Without that,
Compare showed Brazil's 2025 surplus as $354.8bn (reais read as dollars).

## `test_imf_weo.py`: IMF World Economic Outlook, fetched directly

```
python3 tools/test_imf_weo.py
```

General government debt and deficit for Argentina, Australia, Brazil,
Canada, India, Indonesia, Japan, Korea, Mexico, Turkey and South Africa
come from the IMF's own API through `imf_weo.py`. They used to come from
FRED's copies (GGGDTA...A188N / GGNLBA...A188N), which FRED stopped
refreshing after the April 2025 WEO while every call kept succeeding.

The API does not mark the last actual year, so `imf_weo.parse` keeps only
years before the year of the country's COUNTRY_UPDATE_DATE (the site's
existing rule for IMF vintages) and rejects an edition more than 400 days
old. The test builds replies to the shape the live API returned, including
its out-of-order time axis, and checks: projections never kept, values on
the right year, stale edition / missing update date / missing country all
rejected, and no fetch script still wiring the frozen FRED family.

Expected: 88 checks (8 parser, 7 update-date forms, 72 fetch scripts, 1 wiring count), 0 failures.
The update-date forms exist because the first version only read the date as
a numeric index, and every live run was rejected with "no COUNTRY_UPDATE_DATE".
`citation_ids.py` recognises GGXWDG_NGDP / GGXCNL_NGDP from the
`imf_weo.fetch(..., imf_weo.DEBT|DEFICIT)` call.

## `test_estat_cpi.py`: Japan CPI, 2025 base, published rates

```
python3 tools/test_estat_cpi.py
```

Japan's CPI comes from e-Stat table 0004052037 (2025 base; the Statistics
Bureau's headline since 28 Aug 2026). The previous table, 0003427113 (2020
base), stops in December 2026 and gave rates up to 0.16 point off the
headline (Jul 2026: 2.06% against 1.9%). The new table carries three kinds
of figure under class "tab" (1 index, 2 month on month, 3 year on year), so
the parser must keep them apart; the request is narrowed to all items,
national, because the whole table is past e-Stat's 100,000-value limit and
would come back truncated. Rates are used as published: across a rebasing
they are not equal to rates recalculated from the index (Jun 2026: 1.6%
published, 1.70% recalculated).

Expected: 11 checks, 0 failures. Published rates win where present; any earlier periods are filled from the index so the series never gets shorter.

## `sitemap_gate.py` — every served page in the sitemap, exactly once

```
python3 tools/sitemap_gate.py
```

Fails on a duplicate `<loc>`, a served page missing from `sitemap.xml`, a
listed URL with no file behind it, or a listed page that is `noindex` or a
redirect stub. Served pages: root `*.html` (except `404.html` and the
`*-by-country.html` redirect stubs), `indicators/`, `embed/`, `rankings/`.
`rewrite_sitemap()` in `generate_indicator_pages.py` builds the sitemap the
same way, so run the generator first; on the committed tree (before CI has
regenerated it) the gate correctly fails.

Expected after a generator run (v1.6.30): **993 `<loc>`, 993 unique, 993
served pages, 0 duplicates / 0 missing / 0 no file / 0 blocked**
(42 root, 469 indicators, 469 embeds, 13 rankings).

## `test_eurostat_gdp.py` — Eurostat quarterly GDP (v1.6.32)

```
python3 tools/test_eurostat_gdp.py
```

Offline checks for `eurostat_gdp.py` (JSON-stat parsing, rejection of short
or late-starting replies, labels, units) and its wiring into `fetch_at.py`,
`fetch_dk.py` and `fetch_nl.py`: Eurostat is fetched before FRED, FRED skips
the keys Eurostat supplied, and growth labels name the real source.
Expected: **36 ok, 0 failed**.

`citation_ids.py` treats `namq_10_gdp` as the id for gdp_level, gdp_real and
gdp_growth in any script calling `eurostat_gdp.fetch_levels`. Baseline after
v1.6.32: **MATCH 358 / MISMATCH 0 / CROSS 0 / UNCITED 0 / NO-ID 143**.

## `test_growth_basis.py` — one definition of GDP growth (v1.6.33)

```
python3 generate_indicator_pages.py   # first; then revert generated output
python3 tools/test_growth_basis.py
```

Fails if any fetcher derives `gdp_growth` from nominal `gdp_level`, labels a
quarter-on-quarter growth series built from not-seasonally-adjusted data, or
if the GDP growth ranking contains anything other than quarter-on-quarter
growth of seasonally adjusted quarterly real GDP (or a published SA
quarter-on-quarter rate). Countries' own `gdp_growth` series mix QoQ, QoQ
annualised (US), year on year (ES, IN, NO, AR) and annual (SG, TH), so the
ranking computes from `gdp_real`, as Compare does.
Expected: **47 ok, 0 failed**; on the v1.6.32 tree it reports 10 failures.

## `test_eurostat_unemp.py` — EU unemployment direct from Eurostat (v1.6.34)

```
python3 tools/test_eurostat_unemp.py
```

Offline checks for `eurostat_unemp.py` (parsing, short-reply rejection,
query parameters, label) and its wiring into the ten EU fetchers (AT DE DK
ES FR IE IT NL PL SE): Eurostat runs before FRED, FRED skips the key,
`ALLOW_SHRINK` covers the switch. Also checks `fetch_ez.py` takes GDP for
EA21 from `eurostat_gdp` and government finance for EA21 first.
Expected: **51 ok, 0 failed** (v1.6.35 adds three checks: Eurozone HICP
for EA21 from `prc_hicp_minr`, published annual and monthly rates).

`citation_ids.py` treats `une_rt_m` as the id for unemployment in scripts
calling `eurostat_unemp.fetch` (the pattern accepts `une_rt_[maq]`, which
has no digit), and `prc_hicp_minr` as the id for Eurozone `cpi`/`cpi_mom`. `citation_provider.py` reports 10 unemployment MISMATCH
lines (served=OECD) until the next pipeline run replaces the served labels;
0 after.

## `test_markets.js` — Markets page (v1.6.36)

```
node tools/test_markets.js
```

Runs `markets.html` in jsdom against the real data files. Checks every table
renders without script errors and that no table mixes measures: the
10-year table holds exactly the countries carrying `bond_yield_10y`, sorted,
with the Eurozone's end-of-month basis marked; the daily table holds only
the daily `bond_yield_10y` files (UK, US, Canada, Japan); the euro-area par
yield and the SG/MA/TH long-term yields appear only in their own table;
the euro is shown once, no euro member or US dollar row; daily and annual
exchange rates sit in separate tables, all as US$ per unit of home currency.
Since v1.6.37 it also checks the visuals against the tables: the ticker is
dated, the yield bars and currency bars match their tables row for row
(annual-only currencies never in the scoreboard), one daily line per daily
yield, the Eurozone bar shows its end-of-month basis, and every chart has a
text alternative.
Expected: **25 checks, 0 failures**.
