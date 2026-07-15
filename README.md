# Economic Atlas

The world economy, country by country, in numbers.

## Structure
- `index.html`  — front page: world map; UK, US and Eurozone are clickable
- `uk.html`     — live UK snapshot (ONS data)
- `us.html`, `eurozone.html`, `markets.html` — wireframe shells, content to come
- `style.css`   — shared design: Avenir/Nunito Sans, wireframe blues, mako charts
- `fetch_data.py` + `data.json` — data layer (see below)

## Run locally
```bash
python3 fetch_data.py        # pulls live ONS data (needs `requests`)
python3 -m http.server 8000
```
Open http://localhost:8000 — click the UK on the map.

## Design tokens
- Nav / buttons: navy #1E4566, blue #4796CE
- Background: cream #F5F6F3
- Charts: seaborn mako stops (#2E1E3B, #413D7B, #37659E, #348FA7, #40B7AD, #8AD9B1)
- Type: Avenir Next / Avenir (macOS/iOS native) with Nunito Sans as web fallback

## Site structure
Front page: roadmap and link to the UK. Contact page:
contact@economicatlas.co.uk. UK page: six sections via the category
banner — Headline (tiles), GDP, Inflation & rates, Labour market,
Trade, Public finances. Each section has its own summary tiles;
headline tiles are clickable and jump to the relevant chart. Every
chart carries a one-line plain-English explainer, unit-aware hover
values and an explicit source. A green banner appears for ~3 days
whenever a fetch brings in a new data point (diffed in fetch_data.py
against the previous data.json). The US page is live (fetch_us.py -> data-us.json; FRED key
required as the FRED_API_KEY repo secret). Eurozone and Markets
pages exist but are unlinked until built. When a third country
arrives, refactor the shared page machinery into a common JS file.

## UK page data (verified series codes)
Charts: ABMI (GDP), IHYQ (GDP growth), LZVB (productivity), MGSX
(unemployment), LF24 (employment), LF2S (inactivity), D7G7 (CPI),
HF6X (debt % of GDP). Tiles additionally: DZLS (monthly borrowing),
AA6H (current account % of GDP).
Tile lights: green = latest observation is as recent as the series'
publication schedule allows; orange = a newer release is overdue.
Additional series: L55O (CPIH), IKBH/IKBI (exports/imports), the OECD
business confidence indicator (BCICP, free SDMX API — replaces the
proprietary PMI), FDI net inflows % of GDP from the World Bank API,
and Bank Rate (IUDBEDR) from the Bank of England's IADB CSV endpoint.
Annual GDP and trade intensity are derived client-side from ABMI and
IKBH/IKBI. All non-ONS fetchers fail gracefully: a failed source shows
its tile as pending rather than breaking the page.

## Deploy
GitHub Pages + the included workflow (.github/workflows/update-data.yml),
which refreshes data.json every weekday morning after ONS releases.

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
    "organization": "Economic Atlas",
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
- **Eurozone unemployment, debt, deficit**: stuck at Jan 2023 / 2010 / 2010
  respectively -- confirmed genuinely stale (dead FRED mirrors), and a live
  OECD replacement was investigated for 7.6.4 but NOT wired in. The CPI fix
  in this same release rested on an exact, single-country working example
  query from OECD's own documentation; the only example found for the
  unemployment dataflow (DSD_LFS@DF_IALFS_UNE_M) was a 26-country broad
  query with no confirmed single-country pattern to replicate, meaning the
  dimension order would have to be guessed -- exactly the kind of
  unverified guess that caused the India trade currency-mismatch bug.
  Deliberately left as an honest gap rather than shipped on a guess; needs
  its own dedicated verification session.
- **India RBI policy rate**: no live FRED series exists. The 10-year
  government bond yield is used instead and honestly labelled as a bond
  yield, not the policy rate.
- **Eurozone trade** (exports/imports/trade balance): discontinued at
  source (OECD) since April 2023. Shown for historical reference with
  explicit "discontinued" labelling; a live Eurostat SDMX replacement is
  on the roadmap.
- **Canada trade**, **Australia trade**: only the combined trade balance is
  wired in, not separate exports/imports -- the matching components either
  don't exist live or looked stale relative to the headline series in
  verification. Individual exports/imports remain a known gap.
- **India RBI repo rate**, **Australia RBA cash rate**: no live FRED series
  exists for either central bank's actual policy rate. The 10-year
  government bond yield is shown instead in both cases, honestly labelled
  as a bond yield rather than mislabelled as the policy rate.

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
