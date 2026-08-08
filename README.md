# The Economic Atlas

**v1.0**

Official economic data, country by country, updated hourly, with no
commentary. Live at [theeconomicatlas.com](https://theeconomicatlas.com).

## What this actually is
A fully static site (GitHub Pages, no server of its own) with an hourly
GitHub Actions workflow that fetches official data directly from
national statistical offices, central banks, the OECD, the World Bank
and Eurostat, and commits the results straight into this repo as JSON.
The frontend is vanilla HTML/CSS/JS — no framework, no build step.

The one deliberate exception to "no server" is accounts: a Supabase
project (Postgres + Auth, RLS locked down from the start) handles
sign-up/login/password reset, reached client-side via `supabase-js`.
Nothing else in the site depends on it.

**The editorial principle, unchanged since day one**: republish official
statistics with explicit sourcing and zero interpretation. No AI-written
summaries, no "what this means" commentary, no framing of whether a
number is good or bad. Every chart traces back to a named official
source, visible on the page.

## How it actually works, end to end
1. **Hourly, `.github/workflows/update-data.yml` runs every `fetch_*.py`
   script** — one per country/dataset (FRED, OECD, Eurostat, ONS, BoE,
   MoSPI, UN Comtrade). Each writes its own `data-*.json` directly into
   the repo root. A script that can't get real data logs a note and
   leaves the previous file in place rather than guessing or failing
   the whole build.
2. **`check_data_freshness.py` runs immediately after**, comparing each
   series' latest observation against its own known publication
   schedule (monthly CPI vs. quarterly GDP vs. annual FDI, etc.) and
   opens or closes a GitHub issue automatically for anything that's
   gone stale — this is how a real fetch failure gets noticed without
   anyone having to check by hand.
3. **The browser does the rest.** Every page is static HTML that
   `fetch()`es the relevant `data-*.json` files directly and renders
   client-side with Chart.js/D3 — there's no build step and no server
   render, so "deploy" is just "commit changed files" and GitHub Pages
   serves the result.
4. **Accounts are the one live service.** Supabase (Postgres + Auth)
   handles sign-up/login and stores each account's Dashboard pins and
   Compare selections in `profiles.preferences`, synced across devices.
   Logged out, nothing persists between visits.

## Structure
- `index.html` — homepage: clickable world map, links into every country
- 18 country pages (`uk.html`, `us.html`, `eurozone.html`, `japan.html`,
  `india.html`, `canada.html`, `australia.html`, `southkorea.html`,
  `israel.html`, `mexico.html`, `brazil.html`, `southafrica.html`,
  `morocco.html`, `germany.html`, `france.html`, `italy.html`,
  `spain.html`, `netherlands.html`) — each with GDP, inflation, labour
  market, trade and public finances tabs, all sourced from live data,
  plus deeper category-specific features on some pages (see "Deep dives
  beyond the charts" below)
- `compare.html` — side-by-side comparison of any or all 18 tracked
  countries at once across any tracked metric, with a live world map
  (scrub through past years with the slider, switch which metric it
  shows), a sortable summary table, and 1/2/5/10-year horizon
  comparisons, not just a snapshot of "now"
- `dashboard.html` — pin any metric from any country into one personal
  view (synced to your account when logged in), with an on-demand chart
  per tile and a cross-country map that appears automatically once two
  or more pinned tiles share a comparable metric
- `contact.html`, `roadmap.html`, `privacy.html` — as named
- `markets.html` — an old, unlinked stub; deliberately not part of the
  current site (`robots.txt` disallows it), pending a decision on
  whether to build it out properly or retire it
- `style.css` — shared design system (see Design tokens below)
- `fetch_*.py` — one script per country/dataset, run hourly by
  `.github/workflows/update-data.yml`, each writing its own
  `data-*.json`. `check_data_freshness.py` flags any series that's gone
  stale relative to its own publication schedule and opens/closes a
  GitHub issue automatically.
- `og-image.png`, `logo*.png`, `favicon*.png`, `apple-touch-icon.png` —
  brand assets, including the Open Graph/Twitter Card image shown when
  any page is shared on social media or messaging apps
- `sitemap.xml`, `robots.txt` — SEO plumbing, kept in sync with the
  clean-URL scheme below

## Accounts
Real email/password accounts via Supabase (project `skluvrxnuibkordzgtmu`,
`eu-west-2`/London). Email confirmation is required before an account
works; forgot-password and change-password are both wired up, and auth
emails send through a custom domain (Resend SMTP), not Supabase's
generic shared sender.

Everyone signs up on the free plan automatically — there's no plan
picker, and no paid tier exists yet. A `plan` column on the `profiles`
table (`free`/`pro`/`premium`) exists ready for when one does. One
account is flagged `is_admin = true`, currently used only to gate the
in-development Customise & Export feature below — nothing else checks
this flag yet.

**Preferences sync to the account**, not the browser: Dashboard's
pinned tiles and Compare's selected metrics are stored in
`profiles.preferences` and follow you across devices when logged in.
Logged out, nothing persists at all — a visible nudge banner (styled
like Office's "Enable Editing" bar, deliberately reappearing every
visit rather than remembering it was dismissed) explains why and links
straight into sign-up.

**Note for local Postgres/Supabase work**: the `authenticated` role
needs explicit `SELECT`/`INSERT`/`UPDATE` grants on `profiles` — RLS
policies alone aren't enough; Postgres rejects the query at the grant
level before RLS is even evaluated. This was actually missing in
production for a stretch (a real, previously-undetected bug, not just
a note for new setups) — see the grant statement in
`grant_authenticated_role_profiles_access` if setting this up fresh.

## Locked chart features
Every chart has two buttons beneath it, unlocked independently:

- **Download data** — real and unlocked for **any logged-in account**.
  Exports that chart's own data as a CSV, entirely client-side. Logged
  out, it's locked with a prompt to create a free account, and clicking
  it opens the login/signup modal directly rather than a dead end.
- **Customise & export** — currently unlocked **only for the one
  account flagged `is_admin`**, regardless of anyone else's login
  state, while still being tested. For everyone else it stays exactly
  as it's always been: a "Coming soon" link to Contact.

### What Customise & export actually does
A full in-browser chart editor, rendered with its own hand-built SVG
engine (deliberately not dependent on the page's own Chart.js canvas,
so it works even where the CDN can't load):
- Custom date range, chart title, and Y-axis title (auto-detected as
  "%" for percentage metrics, editable either way)
- Switch any chart between line and bar view at will, with bar colours
  matching the site's own up/green-down/indigo convention exactly
- Up to 6 event annotations, either a full-height dashed line or an
  arrow pointing at the exact data point — each with a freely
  draggable label (drag anywhere, or click it to type directly on the
  chart), adjustable font size, and left/centre/right alignment presets
- A reference line at any value, styled to match the event lines rather
  than standing out as a separate colour
- Y/X axis tick-count controls, using a proper "nice numbers" algorithm
  (the same approach real charting libraries use) rather than naively
  slicing the range — so ticks land on 0/2/4/6/8, not 0.335/1.71/3.085
- Export as PNG or SVG, in a light or dark theme independent of
  whatever theme you're browsing in, with the source citation and a
  "Made on theeconomicatlas.com" credit baked into the image itself

**Corrected in this v1.0 review**: this README previously said the
feature wasn't built on Dashboard or Compare yet. It actually is —
`window.EATLAS_CUSTOMIZE` is wired on every tile's `.cz-btn` on
Dashboard and on every card on Compare (`wireMulti`/`wireSnapshot`,
adapted for showing several countries on one chart), unlocking for the
same `is_admin`-flagged account exactly as it does on country pages.
Everyone else still sees the same "Coming soon" locked state site-wide.
Worth actually testing this live before calling it done, since this
correction came from reading the code, not from clicking through it.

## Deep dives beyond the charts
Most sections are charts and tiles, but a few go further wherever the
underlying data supports a genuinely richer story:
- **Bank Rate decisions: MPC vote record** (UK, Inflation & rates tab) —
  every Bank of England Monetary Policy Committee meeting, with the
  actual hold/hike/cut vote split and the economic context (CPI, GDP
  growth, unemployment) as of that meeting date, not just the resulting
  rate.
- **Trade partners** (Trade tab, most countries) — a full partner-by-
  partner breakdown of goods trade from UN Comtrade, switchable between
  a world map, a radial view, and a ranked list, not just a single
  aggregate export/import figure.
- **Where money goes** (Public finances tab, UK) — a COFOG functional
  breakdown of government spending (health, education, defence, debt
  interest, etc.) as a pie, not just a single deficit/debt figure.

These are the exception, not the rule — most metrics are exactly what
they look like: an official figure, charted, sourced. The onboarding
tour (below) uses the MPC vote record as its example of this category,
since it's the most detailed one currently live.

## Onboarding tour
A 31-step guided walkthrough (`EATLAS_TOUR`, duplicated per-page since
this is a static site with no shared JS file — see `window.EATLAS_TOUR`
in any page's own script block) that auto-starts once for a genuinely
first-time visitor and can be replayed any time via "Take the tour" in
the footer. It walks: the homepage map → a full country page tour (tabs,
headline tiles, the full-size chart modal with drag-to-zoom, CSV
download, Customise & Export, and the MPC vote record as an example of
the deeper category features) → Compare (adding countries, the 1/2/5/10
year horizon toggle, adding a metric, switching what the map shows,
scrubbing the map's year slider, zooming in, sorting the summary table)
→ Dashboard (adding metrics for two countries, the map that appears
automatically once they share a comparable metric, viewing a tile's
inline chart, Dollarise) → a closing note on Roadmap pointing to
Contact. Every step targets a real, live element and advances either by
clicking "Next" or by actually performing the described action (both
work) — nothing in the tour is a mocked-up screenshot or a fake
interaction.

## Email alerts
A no-account-required email signup (`alert_signups` table in Supabase,
insert-only RLS — the email can never be read back via the client API,
by design) for people who want to hear about new countries, indicators
or features without creating a full account. Promoted via a dismissible
orange banner site-wide (hidden once logged in) and a form on the
Roadmap page.

**⚠️ Known mismatch, found in a pre-v1.0 review, not yet resolved**:
`privacy.html`'s "Email signup" section states addresses are stored with
"Kit (our email delivery provider)" and describes an unsubscribe-link
flow. Neither exists in the code — signups go straight into the
Supabase `alert_signups` table, there's no Kit integration anywhere in
the repo, and no automated emails are sent to this list at all yet (no
double opt-in/confirmation flow is wired up — the `confirmed` column
exists on the table but nothing sets it or acts on it). Since this
banner is already live and collecting real addresses against a privacy
policy that describes a different, non-existent data flow, this is
worth resolving before promoting email capture any further — either by
building the Kit integration the policy describes, or by rewriting that
section of the policy to match what actually happens today.

## Clean URLs
Every internal link and the sitemap use extensionless paths (`/uk`, not
`/uk.html`) — GitHub Pages resolves these automatically since the repo
runs its default Jekyll pipeline (confirmed via no `.nojekyll` file).
Canonical tags, `sitemap.xml`, and `robots.txt` are all kept in this
same clean-URL form.

## Data freshness
Every tracked figure gets a green or amber dot: green means the latest
observation is as recent as that series' own publication schedule
allows; amber means a newer release is overdue. The same freshness
logic runs both client-side (the dot itself) and server-side
(`check_data_freshness.py`, which flags anything 3x past its expected
cadence and opens a tracking GitHub issue automatically, closing it
once resolved).

## Run locally
```bash
python3 fetch_data.py        # pulls live UK data (needs `requests`)
python3 -m http.server 8000
```
Open http://localhost:8000 and click any country on the map. Most
other `fetch_*.py` scripts need their own API key as a repo secret
(FRED_API_KEY at minimum; see the MoSPI section below for India's
unemployment figure specifically) — without them, that page's fetch
just logs a note and skips gracefully rather than failing the build.

## Design tokens
- Nav / buttons: navy #1E4566, blue #4796CE
- Background: cream #F5F6F3 (light mode), dark navy/near-black (dark mode)
- Charts: seaborn mako stops (#2E1E3B, #413D7B, #37659E, #348FA7, #40B7AD, #8AD9B1)
- Type: Avenir Next / Avenir (macOS/iOS native) with Nunito Sans as web fallback
- Both light and dark mode are fully supported sitewide, toggled via
  the moon/sun icon in the nav and persisted in `localStorage`. Charts
  currently use the same colours in both modes, matching the site's
  existing convention rather than a separate dark-mode palette (an
  acknowledged, deliberate gap, not an oversight)

## Deploy
GitHub Pages + `.github/workflows/update-data.yml`, which runs hourly,
re-fetches every country's data, commits any changes, and runs the
freshness check. The one file that must always be edited via the
pencil icon in the GitHub web UI — never uploaded as part of a zip —
is the workflow file itself.

## Contact
contact@theeconomicatlas.com

## Setting up the MoSPI API key (for India unemployment)
India's unemployment figure comes from MoSPI's own PLFS survey via their
eSankhyiki API (api.mospi.gov.in) — the only source that's genuinely live
(monthly, since MoSPI relaunched PLFS in Jan 2025) rather than a stale
mirror. Unlike the FRED key, MoSPI's access tokens expire after **30
minutes**, so there's no static key to store — instead you register an
account once, and `fetch_in.py` logs in fresh on every scheduled run.

**Step 1 — sign up (one-time).** Pick a real email you haven't used on this
platform before, plus a password. Run this once from any terminal with
`curl` (or paste it into Postman as a POST request):
```bash
curl -X POST https://api.mospi.gov.in/api/users/usersignup \
  -H "Content-Type: application/json" \
  -d '{
    "username": "you@example.com",
    "password": "ChooseAStrongPassword123!",
    "organization": "The Economic Atlas",
    "purpose": "View/Download the Data",
    "gender": "Male"
  }'
```
A response code of 200 means it worked. Keep that email and password —
that's your permanent login, not a token.

**Step 2 — add two GitHub secrets**, not one: `MOSPI_USERNAME` (the email
you used) and `MOSPI_PASSWORD` (the password you chose), under Settings →
Secrets and variables → Actions, same place as `FRED_API_KEY`.

**Step 3 — nothing else to do.** `fetch_in.py` already calls MoSPI's login
endpoint itself on every run to get a fresh 30-minute token, then
immediately uses it to fetch the data — no manual token handling needed.
The workflow file already passes both secrets through.

Until both secrets are set, `fetch_in.py` skips unemployment gracefully
(logs a note, doesn't fail the build) and the India page simply won't show
that one chart.

## Known data gaps
Disclosed honestly on the relevant page's own footer, not hidden:
- **Productivity** (GDP per hour worked): only tracked for the UK and US
- **10-year government bond yield**: missing for the UK, US, Eurozone,
  Japan and Canada specifically — the five largest economies, oddly
  the ones never backfilled after later, smaller countries got it
- **Business confidence**: missing for Spain, France, Italy and
  Morocco. (Germany was previously listed here too — re-checked in this
  review and it's actually live now, so it's dropped from this list.)
- **CPI/inflation**: missing entirely for **Mexico and South Africa** —
  found in a pre-v1.0 review, not yet disclosed on either page's own
  footer the way the other gaps here are. Worth fixing the footer text
  even before a live series exists, so it's honestly flagged rather
  than just silently absent.
- **GDP growth**: missing for **Israel** (GDP level is tracked, but not
  a live quarter-on-quarter growth series) — same "found, not yet
  disclosed on the page" situation as the CPI gap above.
- **Eurozone trade** (exports/imports/trade balance): discontinued at
  source (OECD) since April 2023, shown for historical reference with
  explicit "discontinued" labelling
- **France's trade-partner data**: the live Comtrade fetch has never
  once succeeded; the page runs on an honestly-labelled illustrative
  fallback ("Illustrative data... not a live feed") rather than silently
  showing nothing
- **India RBI policy rate**, **Australia RBA cash rate**: no live FRED
  series exists for either central bank's actual policy rate; the
  10-year government bond yield is shown instead in both cases,
  honestly labelled as a bond yield, not the policy rate
- **Canada trade**, **Australia trade**, **India trade**: only the
  combined trade balance is wired in for Canada/Australia, not separate
  exports/imports; India shows exports/trade balance but not imports
  individually — in each case because the matching component either
  doesn't exist live or looked stale relative to the headline series
- **South Korea's actual policy rate** (Bank of Korea base rate): a
  10-year bond yield is shown instead, honestly labelled; exports and
  imports aren't individually broken out, only the combined trade
  balance
- **Morocco**: the thinnest dataset on the site (6 of the ~11 usual
  series) — no live GDP growth, government debt, trade balance, bond
  yield or business confidence. No live exchange-rate source exists for
  the dirham either, so currency-denominated figures show "n/a" rather
  than a converted guess, consistent with how the site handles missing
  FX everywhere else.

### Fixed in this v1.0 review
- **UK unemployment/inactivity by age band**: previously only the
  16-24 band was live; `fetch_uk_age_breakdown.py` was fixed in a prior
  session and is now confirmed producing real data across all bands
  (16-17, 18-24, 25-34, 35-49, 50-64, 65+, plus the 16+ and 16-64
  headline rates).
- **UK inactivity-by-reason was silently mislabelled**: the fetch
  script tried the ONS "People" (all-persons) sheet first, but on
  failure fell through to the "Women" sheet and still wrote the output
  labelled "all persons" — confirmed this had actually happened (the
  live committed JSON's own `"sheet"` field said `"Women"`). Fixed to
  fail loudly and leave the previous good file in place if "People"
  specifically can't be parsed, rather than silently substituting
  gendered data under an all-persons label. Needs one real run of the
  hourly workflow to produce a corrected file.


## Archive: historical per-country data fixes
The sections below predate the wider site rebuild (Compare, Dashboard,
accounts, mobile redesign, clean URLs, the `.com` migration, and the
Customise & Export feature) and are kept for reference on specific
data-pipeline bugs, not as a description of the current site.
## Fixed in 7.6.9
- **Eurozone unemployment/debt/deficit rebuilt from scratch, not patched.**
  A real user-run data audit found these three series had gone from
  "stale" (the original dead-FRED-mirror problem) to completely ABSENT
  after the 7.6.7 fix -- meaning the Eurostat queries were failing
  entirely, including the unemployment one that had been flagged as
  high-confidence. Root cause: the 7.6.7 fix used Eurostat's SDMX 2.1 REST
  API, which requires filter values in a strict, dataset-specific
  positional order -- exactly the kind of thing that's easy to get subtly
  wrong. Rather than guess at the order again, the fetchers now use
  Eurostat's separate "API Statistics" endpoint, which takes named query
  parameters (geo=, sector=, unit=, na_item=, etc.) instead of positional
  ones -- this class of bug becomes structurally impossible, not just less
  likely. The new endpoint's JSON-stat response format was verified
  directly against a real live response (a different dataset, used only to
  confirm the response shape matches what the parser expects) before
  wiring it in. Added full diagnostic logging (HTTP status, row counts,
  raw response snippets on failure) to both this and Japan's CPI fetch, so
  any future failure is diagnosable from the Actions log directly.
- **Japan's CPI showing 2021 data despite the fix being deployed**: this
  wasn't a code bug -- the fix was already correctly in place, but
  `fetch_oecd_cpi()` had zero diagnostic output, so a real failure was
  indistinguishable from "hasn't been re-run since deploying." Added the
  same diagnostic logging pattern used for MoSPI, so the next run's log
  will show exactly what OECD's API returned.

## Fixed in 7.6.6
- **Canada and Australia's CPI fetch worked, but the pages never displayed
  it.** The 7.6.4 fix added `cpi` to both fetch scripts and confirmed it
  was landing correctly in the live JSON (Canada 3.23% for May 2026,
  Australia 4.05% for Q1 2026 -- both plausible, both live) -- but neither
  `canada.html` nor `australia.html` was ever updated to actually render
  it. The "Known gap" note describing the old dead-mirror problem was
  still showing even though the gap itself was closed. Both pages now have
  real cpi charts/tiles wired in, matching the NAMES map, sampleData(),
  and render() consistency already required elsewhere.
- Also fixed, across three separate rounds with a real user testing each
  one: India's MoSPI unemployment fetch. In order: (1) the platform's
  self-signed TLS certificate needed `verify=False`, matching MoSPI's own
  reference client; (2) `sector_code` needed to be Urban-only ("2"), not
  Rural+Urban combined ("3"), since PLFS's monthly bulletin is explicitly
  urban-only by MoSPI's own design; (3) the `month` field comes back as a
  full month name ("December"), not a numeric code as the parameter name
  implied -- confirmed directly from real log output each time, not
  guessed.

## Fixed in 7.6.4
- **India, Canada, Australia CPI**: FRED's OECD "MEI" vintage CPI family
  was discontinued en masse around March 2025 (confirmed via each series'
  own FRED page). Replaced with live queries against OECD's own SDMX
  prices system (DSD_PRICES@DF_PRICES_ALL) -- the same underlying platform
  that publishes OECD's monthly inflation press releases. Japan's dead
  FRED series (JPNCPIALLMINMEI) was removed from FRED_SERIES entirely so a
  future failure can't silently fall back to serving 2021 data as current.
  Australia's CPI is quarterly, not monthly, matching OECD's own
  documentation ("data are available monthly for all the countries except
  for Australia and New Zealand"). None of these three fixes have been
  personally executed end-to-end (no way to test sdmx.oecd.org from the
  build sandbox) -- check the Actions log on first run for "ok  cpi" vs
  "FAIL  cpi".
- **Eurozone CPI was investigated and found NOT to be broken.** It uses a
  different (ECB/Eurostat-sourced) series, CP0000EZ19M086NEST, not the
  dead OECD MEI family -- confirmed genuinely live (May 2026 data) via a
  direct data audit. No fix needed; time was spent on the genuine gaps
  above instead of "fixing" something that already worked.
- **India unemployment (MoSPI)**: hardened with diagnostic logging after
  the SSL fix still didn't produce data on the next run. The login and
  data-fetch functions now print the actual response status and shape on
  every run, so any further failure is diagnosable from the Actions log
  directly rather than requiring another guess.

## Fixed in 7.6.3 (found via real user screenshots after first live run)
- **India/Canada/Australia GDP was ~1000x too large and mislabelled as $**:
  their IMF IFS GDP series are the literal quarterly level, not a
  seasonally-adjusted-annual-rate like the UK/US series -- fixed by rolling
  up 4 quarters with the existing `annualGDP()` helper (already used by the
  UK page) rather than using the raw quarterly figure directly. Also, these
  series are in local currency (rupees/Canadian dollars/Australian
  dollars), not USD -- no FX conversion is performed, so the currency
  symbol is now correctly Rs/C$/A$, not $.
- **India trade balance was nonsense**: the imports series originally wired
  in (XTIMVA01INM664S) turned out to be rupee-denominated, while the
  exports series it was being subtracted from (XTEXVA01INM667S) is
  dollar-denominated -- every previous check confirmed each series was
  individually live, but never cross-checked they shared the same
  currency. Fixed by using a single, self-contained, verified
  dollar-denominated trade balance series (XTNTVA01INM667S) instead of
  deriving one from two mismatched series. Imports on their own are no
  longer shown for India (same call already made for Canada/Australia).

## South Korea (added 7.6.8)
GDP, unemployment, 10-year bond yield, government debt/deficit, trade
balance, CPI, business confidence, FDI and current account -- all
verified live before wiring in, following the same discipline as India/
Canada/Australia. Two lessons already learned from those builds were
applied from day one rather than discovered as bugs:
- GDP (NGDPSAXDCKRQ/NGDPRSAXDCKRQ) is the literal quarterly level, not a
  seasonally-adjusted-annual-rate -- uses the rolling-4-quarter annualGDP()
  helper from the start, with the currency correctly labelled \u20a9 (won),
  not $.
- Trade balance (XTNTVA01KRQ667S) is shown as a single combined series only
  -- not derived from separately paired exports/imports -- avoiding the
  exact currency-mismatch class of bug that broke India's trade balance
  originally.
- CPI is wired in directly via OECD's live SDMX prices system from the
  start, rather than ever risking a dead FRED "MEI" mirror the way Japan/
  India/Canada/Australia's CPI originally was.
- Known gap: exports/imports individually, and the Bank of Korea's actual
  base rate (a 10-year bond yield is shown instead, honestly labelled).
