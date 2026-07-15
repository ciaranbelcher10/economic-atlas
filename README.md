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
mirror. It requires a personal access token, following the same self-service
pattern as the FRED key:
1. Go to https://esankhyiki.mospi.gov.in and find the API/Developer section
   (the official user manual PDFs, e.g. "WPI API User Manual.pdf", document
   the exact steps).
2. Using Postman (or the platform's own Swagger UI), call the platform's
   signup API at base URL https://api.mospi.gov.in to register and receive
   an access token.
3. Add that token as a GitHub Actions repo secret named `MOSPI_API_KEY`
   (Settings → Secrets and variables → Actions), same place as
   `FRED_API_KEY`.
4. Add a step to `.github/workflows/update-data.yml` passing it to
   `fetch_in.py`, mirroring the existing `FRED_API_KEY` step:
   ```yaml
   - run: python fetch_in.py
     env:
       FRED_API_KEY: ${{ secrets.FRED_API_KEY }}
       MOSPI_API_KEY: ${{ secrets.MOSPI_API_KEY }}
   ```
Until this secret is set, `fetch_in.py` skips unemployment gracefully (logs
a note, doesn't fail the build) and the India page simply won't show that
one chart.

## Known data gaps
- **India CPI**: the obvious FRED mirror (CPALTT01INM659N) stopped updating
  in March 2025. OECD's own live system clearly still has current India
  CPI, but the correct live SDMX query hasn't been verified end-to-end —
  needs its own session before wiring in, same discipline that caught the
  Japan CPI and Eurozone trade/unemployment/debt bugs.
- **India RBI policy rate**: no live FRED series exists. The 10-year
  government bond yield is used instead and honestly labelled as a bond
  yield, not the policy rate.
- **Eurozone trade** (exports/imports/trade balance): discontinued at
  source (OECD) since April 2023. Shown for historical reference with
  explicit "discontinued" labelling; a live Eurostat SDMX replacement is
  on the roadmap.
- **Canada CPI**, **Australia CPI**: same systemic issue as Japan/India --
  FRED's OECD "MEI" vintage CPI family was discontinued en masse around
  March 2025. StatCan/ABS clearly still publish live, but the replacement
  route needs its own verification pass. 10-year bond yield (Canada:
  interbank overnight rate) shown instead in the meantime.
- **Canada trade**, **Australia trade**: only the combined trade balance is
  wired in, not separate exports/imports -- the matching components either
  don't exist live or looked stale relative to the headline series in
  verification. Individual exports/imports remain a known gap.
- **India RBI repo rate**, **Australia RBA cash rate**: no live FRED series
  exists for either central bank's actual policy rate. The 10-year
  government bond yield is shown instead in both cases, honestly labelled
  as a bond yield rather than mislabelled as the policy rate.
