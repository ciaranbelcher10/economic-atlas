# Adding a New Country to The Economic Atlas

This is the complete, file-by-file instruction manual for taking a country
from zero to fully live on the site: country page, indicator pages, Compare,
Dashboard, ChartMaker, rankings, and the automated data pipeline. It exists
because the individual pieces of this process are scattered across roughly a
dozen files, several of them duplicating the same list of countries
independently, and missing one of them produces a bug that's easy not to
notice (a country that shows on the map but not in Compare, or vice versa).

Budget a full working day per country. Nothing here shortcuts that; it exists
so the day is spent on genuine sourcing and verification work, not on
rediscovering which files need touching.

---

## 0. Before starting: the two things that can't be fixed later

**Currency regime.** Decide whether the country uses its own currency or the
euro. This determines which existing page to derive the new one from (see
Step 1) and which Dollarise FX pattern applies. Getting this wrong means
re-deriving from scratch.

**Data source availability.** Before writing a single line, confirm answers
to all of these — a "no" on any of them doesn't rule out the country, but
changes how much of the site it can support at launch:

- Does FRED mirror a GDP level series for this country, and is it still
  being updated (not dead — check the series page directly, many
  OECD-mirrored FRED series have silently stopped)?
- Is there a live, non-annual FX rate history if the country has its own
  currency (needed for Dollarise)?
- Does this country's central bank rate exist on FRED or its own source?
- For debt/deficit: do NOT assume an IMF-WEO FRED family exists for every
  country — it's been confirmed absent for several. The reliable fallback
  is Eurostat's `gov_10dd_edpt1` (EU members and the euro area) or, for
  non-EU/EFTA countries outside that dataset's coverage, per-country checking
  is required (see Norway's `gov_10q_ggdebt`/`gov_10q_ggnfa` precedent, which
  needed two *different* Eurostat datasets because the EDP notification table
  doesn't cover EFTA members).
- Unemployment/participation/employment: the portable OECD-harmonized FRED
  naming family (`LRHU...`) works reliably only for full OECD members.
  Non-members (confirmed cases so far: Brazil, South Africa, Morocco) need
  individual, per-country checking — do not assume the pattern transfers.
- Productivity and net debt have **no portable cross-country pattern at
  all**. Each one is a fresh, individual sourcing job every time; never
  attempt a naming-pattern shortcut for these two.

If several of these come back genuinely unavailable, that's a real signal
the country may not be ready yet, not just a gap to paper over later.

---

## 1. Derive the new country page

Copy the most recently built existing country page that matches **both**
recency of build **and** currency regime:

- Eurozone member → derive from another Eurozone member's page.
- Own-currency country → derive from another own-currency page.

After deriving, before anything else:

1. Grep case-insensitively **without word boundaries** for the old country's
   name and its currency/country code. Word-boundary-only greps miss
   substring matches inside longer identifiers and variable names.
2. Check every `SRC_*` citation string individually for leftover series IDs
   from the donor country — these are rendered verbatim on the live page, so
   a leftover string isn't just an internal bug, it's a visible one.
3. Check every hardcoded prose description or tooltip for the old country's
   name or its adjective form ("British", "German", etc.) — these don't show
   up in a code-identifier grep.

### The `sampleData()` function

Every country page includes a `sampleData()` function providing realistic,
illustrative placeholder data (`sample: true` in its return value) — this is
what renders on the page in the window before the real fetch script has run
for the first time, or if a fetch ever fails outright. It is not decorative:
build it with genuinely plausible shapes (correct order of magnitude,
believable volatility, real historical inflection points like 2008 or 2020
where you know the direction even before real data lands) rather than flat
placeholder numbers, because this is what a visitor sees if anything goes
wrong before the real fetch succeeds.

After deriving and editing `sampleData()`:
- Actually **execute** it via Node (not just `node --check`) and confirm it
  returns the expected series keys with no thrown error. `node --check` is
  blind to runtime errors like a deleted variable initialisation — this has
  caused real breakage before.

### The embedded mini-map (`dest()` and country-code `Set`s)

Every country page has its own **separate, independently embedded** copy of
a small world mini-map, complete with its own `dest()` function and its own
country-code `Set` definitions (e.g. `UK=new Set(["826"])`,
`EZ=new Set([...])`). This is not shared code — it's duplicated verbatim
across all 32+ country pages.

Adding a new country means:
1. Adding the new country's own `Set` and a `dest()` branch **on the new
   page itself**.
2. Adding the exact same `Set` and `dest()` branch to **every other existing
   country page's mini-map** — all 32 (soon 33+) of them — plus the
   homepage's own copy of the same map. Missing this means clicking the new
   country on any *other* page's mini-map does nothing or resolves to the
   wrong destination.
3. For Eurozone members specifically: their ISO code is already inside the
   shared `EZ` Set on every page. The member country's own `dest()` check
   **must be placed before** the `EZ` check in the ternary, on every page,
   or clicks resolve to `eurozone.html` instead of the member's own page.

---

## 2. The nav dropdown (site-wide, not just the new page)

The "Country Breakdowns" nav dropdown is an identical block of markup
repeated across essentially every page on the site (all country pages, the
homepage, Compare, Dashboard, ChartMaker, Calendar, rankings, indicator
pages — everywhere the nav appears). Adding a country means:

- Adding one new `<a href="newcountry">New Country</a>` line in the correct
  regional `<div class="dcol">` column, on **every page** that carries the
  dropdown.
- **Never** move the `class="active"` attribute off whichever link
  currently has it when bulk-editing — each page's own active link stays
  exactly where it is; only the new page (once it exists) gets a fresh
  `active` link pointing at itself.
- This is exactly the kind of edit where "bulk find-replace across
  near-identical files" is a documented risk. Verify with exact occurrence
  counts before and after the edit (`grep -c` per file), and confirm a
  single sed pattern actually covers every page's regional column rather
  than assuming it does.

---

## 3. Wire it into `generate_indicator_pages.py`

This is the **one file that, once updated, automatically generates**
indicator pages, embeds, OG images, rankings, and the sitemap for the new
country — no separate list to maintain for any of those four things.

Add one line to the `COUNTRIES` dict near the top of the file:

```python
"New Country": ("nc", "newcountry", "XX", "Region"),
```

The four values are: the two-letter code used in the data filename
(`data-nc.json`), the URL slug used for the country page and its indicator
pages, the ISO alpha-2 code (used for flags), and the region label shown
in the nav dropdown and rankings' region column.

Everything else in this file — the 30 `METRICS` entries (GDP, inflation,
unemployment, interest rates, trade, public finances, business confidence —
see the full list in the file itself for the exact slug/key/title/category
for each), the 11 `RANKINGS`, and the ranking→Compare deep link added
2026-09 — reads from `COUNTRIES` and from the country's own `data-XX.json`
automatically. Nothing in this file needs a second, separate per-country
list.

After adding the line, actually run the generator (`python3
generate_indicator_pages.py`) and confirm it completes without error and
without exceptions for the new country specifically — a missing metric key
in the country's data file surfaces as a skipped page, not a crash, so check
the printed count of generated pages against what you expect, not just that
the script exited cleanly.

---

## 4. The four independent country-file maps

These four lists all serve the same underlying purpose — mapping a country
name to its `data-XX.json` filename — but are maintained completely
independently, in four different files, with no shared source. All four
need the new country added, in the same format already used for every
other entry:

1. **`compare.html`** — the `FILES` object (also carries `COUNTRY_COLOR`
   and `COUNTRY_LABEL` right beside it in the same file — see Step 5 for
   colour).
2. **`dashboard.html`** — its own separate `FILES` object.
3. **`chartmaker.html`** — its own separate `FILES` object.
4. **`check_data_freshness.py`** — its own separate `DATA_FILES` dict,
   used by the hourly freshness-alert check, not by any page.

There is no single source of truth for this mapping across the codebase.
Each of the four must be edited by hand.

---

## 5. Compare's colour palette

`compare.html` carries a 48-colour palette (`COMPARE_PALETTE`), of which
only 32 are currently assigned to a country via `COUNTRY_COLOR` — this was
deliberately over-generated ahead of need, specifically so that adding new
countries doesn't require regenerating the whole palette (which would risk
shifting existing countries' established colours, something people build
muscle memory around).

To add a country's colour:
1. Pick an unused colour from `COMPARE_PALETTE` that is **not already
   assigned** in `COUNTRY_COLOR`, and that sits reasonably far in hue from
   its neighbours in the palette's existing spread (the palette is
   hue-sorted, so a colour from a "gap" in currently-used hues is safer than
   one adjacent to an already-assigned colour).
2. Add it to `COUNTRY_COLOR` in `compare.html`.
3. If more than 16 further countries are ever added (i.e. the palette's
   spare capacity runs out), the whole palette needs regenerating via the
   same greedy farthest-point method used originally (documented in the
   comment directly above `COMPARE_PALETTE` in `compare.html`) — that's a
   dedicated task on its own, not a quick addition.

---

## 6. The fetch script and the hourly workflow

Write `fetch_XX.py` following the pattern of an existing script for a
country in the same currency regime and data-source mix. Then wire it into
`.github/workflows/update-data.yml` as its own step:

```yaml
- name: Run fetch_XX.py
  continue-on-error: true
  run: |
    echo ">>> RUNNING fetch_XX.py" >> pipeline_log.txt
    python fetch_XX.py 2>&1 | tee -a pipeline_log.txt
  env:
    FRED_API_KEY: ${{ secrets.FRED_API_KEY }}
    # plus any other secret this specific script needs (ESTAT_APP_ID,
    # MOSPI_USERNAME/MOSPI_PASSWORD, etc. — only if this country's
    # sourcing actually requires it)
```

Reminders specific to this file, from hard-won experience:
- `.github/workflows/*.yml` files are edited **only** via GitHub's own
  web pencil-icon editor — never uploaded as a file, regardless of how
  the rest of the deployment package is delivered.
- `continue-on-error: true` on this step is deliberate and required —
  one country's fetch failing must never block every other country's
  fetch in the same hourly run.
- `generate_indicator_pages.py` and `generate_og_images.py` already run
  automatically after all fetch steps (see the tail of
  `update-data.yml`) — no per-country wiring needed there, per Step 3.
- `check_data_freshness.py` runs last and needs its own separate
  `DATA_FILES` entry (Step 4, item 4) to include the new country in its
  alerting at all.

### Data-quality gates specific to what the fetch script writes

Every fetch script writes `"sample": False` to its output when it's
returning genuine fetched data (only the hand-written `sampleData()` in the
country page's own JS uses `sample: true`, and only as a pre-launch/failure
fallback — see Step 1). Before considering the fetch script done:

- Never fabricate data for a metric with no confirmed live source. A
  disclosed gap (the metric simply absent, with the reason stated on the
  page) is always preferable to a stale or guessed number standing in for
  it.
- `SRC_*` citation strings are rendered verbatim on the live public page —
  internal verification language ("CONFIRMED LIVE", "placeholder citation",
  "inferred by pattern") must never appear in them. Write clean,
  reader-facing text only; put internal caveats in code comments or
  docstrings instead.
- Every series needs a seasonal-adjustment determination
  (`adjustment_of()` in `generate_indicator_pages.py` — see
  `methodology.html`'s "Seasonal adjustment" section for the full rule
  order). Where the source's own naming convention doesn't already cover
  it, check the actual fetch query parameters this script uses (many
  APIs, including Eurostat's, accept an explicit seasonal-adjustment
  filter as a query parameter — if this script requests a specific one,
  that request itself is the most authoritative answer, more so than any
  external documentation).

---

## 7. Wire into every live feature immediately — don't hold back for "later"

Once Steps 1–6 are done for a country, wire it into the nav, the homepage
map, Dashboard, and Compare **immediately**, using the illustrative-but-
reasoned `sampleData()` (Step 1) if the real fetch hasn't run yet. Reconcile
once the first real Actions run has confirmed live data. Never hold a
country back from Compare or Dashboard pending "real" data landing first —
a country visible with clearly-labelled illustrative data is better than a
country invisible everywhere until every metric is individually confirmed.

---

## 8. Verification, before packaging

Run the full mandatory gate (as for any other change to this codebase):

1. Python `HTMLParser` tag-balance check across every touched HTML file.
2. `node --check` on every inline `<script>` block touched (excluding
   `src=` externals and `application/ld+json`), or simply run
   `tools/html_gate.py` across the whole site, which does both of the
   above automatically and reports pass/fail counts.
3. Actually **execute** `sampleData()` via Node (Step 1) — required, not
   optional, and not satisfied by `node --check` alone.
4. Actually run `generate_indicator_pages.py` end to end and confirm the
   printed page count matches expectations for the new country's metric
   coverage.
5. Diff the whole working tree against a **fresh** `git clone --depth 1` of
   the repo, and package only the files that actually changed — never
   re-zip the whole site as a default. Given how many files a new-country
   add touches (see the full list in Step 9 below), this diff is
   essential; it's very easy to miss that an unrelated file was
   accidentally touched, or to forget one of the four independent file
   maps in Step 4.

---

## 9. The complete checklist — every file a new country touches

Use this as the final pre-package checklist. Every item should have a
corresponding change in the diff against a fresh clone.

- [ ] `data-XX.json` — new file (or `sampleData()`-sourced pre-launch)
- [ ] `fetch_XX.py` — new file
- [ ] `.github/workflows/update-data.yml` — new fetch step (web editor only)
- [ ] `xx.html` — new country page, derived per Step 1, with its own
      `sampleData()` and its own mini-map `dest()`/`Set`s
- [ ] **Every other existing country page's mini-map** — `dest()`/`Set`s
      updated (Step 1)
- [ ] Nav dropdown — new link added on every page site-wide (Step 2)
- [ ] `generate_indicator_pages.py` — one line in `COUNTRIES` (Step 3)
- [ ] `compare.html` — `FILES`, `COUNTRY_COLOR`, `COUNTRY_LABEL` (Steps 4–5)
- [ ] `dashboard.html` — `FILES` (Step 4)
- [ ] `chartmaker.html` — `FILES` (Step 4)
- [ ] `check_data_freshness.py` — `DATA_FILES` (Step 4)
- [ ] Regenerated: 30 indicator pages + 30 embeds + OG images for the new
      country (automatic from Step 3, once `COUNTRIES` is updated —
      confirm the count)
- [ ] `sitemap.xml` — new indicator/embed/country-page entries (automatic
      from the same regeneration run)

### Optional, not required for launch

- **Calendar** (`data-calendar-XX.json` + `fetch_calendar_XX.py` +
  `calendar.html`'s own country list): confirmed optional. As of this
  writing only 16 of 32 live countries have calendar coverage at all — a
  country can be fully live everywhere else without it.
- Country-specific extras (age breakdown, spending by COFOG category,
  trade-partner breakdowns, MPC-vote-style detail, inactivity-reason
  breakdowns): each of these exists for only a handful of countries (UK
  has several; most countries have none). These are enhancements added
  after the core build, never a launch blocker.

---

## 10. The target metric set (benchmarked against UK, the most complete country)

`generate_indicator_pages.py`'s `METRICS` list defines 32 possible
indicator-page metrics site-wide. Not every one is genuinely applicable to
every country, and even the UK — the most fully built page on the site —
currently carries 23 of the 32. Use UK's actual live set below as the
realistic target for a new country, not the full 32, and don't treat a gap
as a failure without first checking whether it's a genuine absence
(a metric this country doesn't publish, or one that's specific to another
country's own statistical convention) versus a real sourcing gap still
worth chasing.

### Carried by UK today (23 metrics — treat this as "full coverage")

| Category | Metric | Data key |
|---|---|---|
| GDP & growth | GDP | `gdp_level` |
| GDP & growth | Real GDP | `gdp_real` |
| GDP & growth | GDP Growth Rate | `gdp_growth` |
| GDP & growth | Productivity | `productivity` |
| Prices | Inflation Rate | `cpi` |
| Prices | Inflation Rate, Month on Month | `cpi_mom` |
| Prices | CPIH Inflation Rate | `cpih` |
| Prices | CPIH Inflation Rate, Month on Month | `cpih_mom` |
| Labour market | Unemployment Rate | `unemployment` |
| Labour market | Youth Unemployment Rate | `unemployment_1624` |
| Labour market | Employment Rate | `employment` |
| Labour market | Economic Inactivity Rate | `inactivity` |
| Interest rates | Interest Rate (policy rate) | `boe_rate` |
| Trade | Balance of Trade | `trade_balance` |
| Trade | Exports | `exports` |
| Trade | Imports | `imports` |
| Trade | Current Account (% of GDP) | `current_account` |
| Trade | Foreign Direct Investment (% of GDP) | `fdi` |
| Public finances | Government Debt (% of GDP) | `debt_gdp` |
| Public finances | Government Net Debt | `net_debt` |
| Public finances | Government Budget Balance | `deficit` |
| Public finances | Government Debt Interest | `debt_interest` |
| Business | Business Confidence | `business_confidence` |

### Not carried by UK (9 metrics) — check applicability before chasing

| Metric | Data key | Why it's likely absent |
|---|---|---|
| GDP Annual Growth Rate | `gdp_growth_yoy` | UK's headline growth figure is quarter-on-quarter (`gdp_growth`); a separate YoY variant exists on the site mainly for countries whose own statistical office publishes YoY as the headline instead (several Latin American and OECD-mirrored countries do) |
| Inflation Rate, MoM (Seasonally Adjusted) | `cpi_mom_sa` | ONS doesn't publish a seasonally adjusted CPI (see `methodology.html`'s seasonal-adjustment section) — genuinely inapplicable, not a gap |
| Inflation Rate, QoQ | `cpi_qoq` | For countries (e.g. Australia) whose CPI is only published quarterly, not monthly — UK's CPI is monthly, so this variant doesn't apply |
| Inflation Rate (National Definition) | `cpi_national` | This exists specifically for countries where the site's headline inflation figure is a *harmonized* measure (HICP) rather than the country's own domestic definition — UK's headline CPI already is its own national definition, so there's no separate "national" variant to add |
| Core Inflation Rate | `core_cpi` | Genuine sourcing gap, not structural — worth checking if ONS publishes a core measure suitable for this slot |
| PCE Inflation Rate | `pce` | US-specific concept (Personal Consumption Expenditures price index is a US national-accounts construct); not applicable elsewhere |
| Producer Price Inflation | `ppi` | Genuine sourcing gap, not structural — ONS does publish PPI; worth checking as a future addition |
| Labour Force Participation Rate | `participation_rate`/`participation` | Genuine sourcing gap — worth checking against ONS's own labour market statistics |
| 10-Year Government Bond Yield | `bond_yield_10y` | Genuine sourcing gap — surprising for UK specifically given gilt yields are widely published; worth prioritising if picked up again |

The three flagged "genuine sourcing gap" rows above (core CPI, PPI,
10-year gilt yield, participation rate) are worth treating as their own
small follow-up task on the UK page itself, separate from any new-country
work — closing gaps on the site's own flagship page raises the bar for
what "full coverage" means for every country built after it.

