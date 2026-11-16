# The Economic Atlas

**v2.0**

Official economic statistics for 62 economies, with the source named on every figure and no commentary.
Live at [theeconomicatlas.com](https://theeconomicatlas.com).

## Principles

- **Official sources only.** Every figure comes from a national statistics office, a central bank or an
  international body (IMF, OECD, World Bank, Eurostat, BIS, ECB), and the page names the series it came from.
- **One number everywhere.** A figure shown on a country page, an indicator page, a ranking, Compare or the
  Dashboard is the same figure, formatted the same way. Release checks enforce this.
- **No interpretation.** No forecasts, no "what this means", no judgement on whether a number is good or bad.
- **Gaps are shown, not filled.** If a series is unavailable or stale, the page says so. Nothing is estimated
  to fill a gap.

## What is on the site

| Page | What it does |
|---|---|
| `index.html` | World map and entry point to every economy |
| 62 country pages (`uk.html`, `us.html`, `eurozone.html`, ...) | Headline tiles and charts by theme: output, prices, labour, money and markets, trade, public finances |
| `indicators/` | 1,109 indicator pages, one per economy and series, each with its own chart, source line and preview image; `embed/` holds an embeddable version of each |
| `rankings/` | 14 cross-country rankings (GDP, growth, inflation, unemployment, interest rates, bond yields, debt, and others) |
| `compare.html` | Any set of economies side by side on one metric, as bars, lines or a map, by year |
| `chartmaker.html` | Build a custom chart from any series on the site |
| `dashboard.html` | Pin metrics from any country into one view |
| `calendar.html` | Upcoming data releases |
| `methodology.html`, `methodology-by-economy.html` | How figures are sourced and converted, and the exact series behind every indicator |
| `data-status.html` | Latest period and next expected release for every series |
| `about.html`, `contact.html`, `privacy.html`, `terms.html` | As named |

Every chart offers Download data (CSV) and Customise & export (PNG or SVG). Country pages, Compare and
Chartmaker share three switches: Convert to USD$, Adjust for inflation and Per capita.

## How it works

The site is static HTML, CSS and JavaScript served by GitHub Pages, with no build step and no application
server. Data lives in this repo as JSON and is drawn in the browser with Chart.js and D3.

1. **`update-data.yml` runs every hour.** It runs one `fetch_*.py` script per economy plus shared fetchers
   (exchange rates, bond yields, population, UK detail tables). Each script writes its own `data-*.json`.
2. **Every fetch is guarded.** If a source fails, the previous data is kept rather than deleted, and
   `series_guard.py` refuses a result that is shorter or older than what is stored unless the change is
   listed with its reason.
3. **Pages are regenerated from the data.** `generate_indicator_pages.py` rebuilds the indicator pages,
   embeds, rankings, sitemap, feeds and methodology tables, and `generate_og_images.py` rebuilds the preview
   images. The bot commits the result.
4. **Freshness is checked.** `check_data_freshness.py` compares each series with its own publication cadence
   and opens or closes a GitHub issue when something falls behind.
5. Separate daily workflows refresh trade-partner data (`update-trade-data.yml`) and the release calendar
   (`update-calendar.yml`).

Accounts use Supabase (Postgres and Auth, row-level security on every table). They store saved charts and
Dashboard pins. Nothing else on the site depends on them.

## Repository layout

- `*.html`: site pages; country pages are hand-written, with generated key-figure blocks inside them
- `data-*.json`: the data, one file per economy, plus shared exchange-rate, bond and population files
- `data-metric-sources.json`: the source, description and currency note for every series
- `fetch_*.py`: one fetcher per economy; shared source modules such as `imf_trade.py`, `imf_weo.py`,
  `eurostat_trade.py` and `ecb_exr.py`
- `generate_*.py`, `methodology_by_economy.py`: page generators
- `indicator-kit.js`, `percapita.js`, `mobile.js`, `consent.js`: shared front-end code; `style.css`: design system
- `tools/`: release gates, migrations (`migrate_v*.py`) and checks
- `README-v*.md`: release notes for each version

## Release checks

Run before every release:

- `tools/html_gate.py`: tag balance, structured data, inline script syntax, duplicate functions
- `tools/generated_pages_gate.py`: every generated page matches its data, plus site-wide copy and
  consent checks

Also available: `history_depth_gate.py`, `sitemap_gate.py`, `og_gate.py`, `tile_pages_gate.py`,
`country_surfaces_gate.py`, `fx_floor_gate.py` and `citation_provider.py` in `tools/`, and the rendered-page
checks `invariants_gate.js`, `coverage_gate.js` and `sampledata_gate.js`, which load every country page in
jsdom (run with `NODE_PATH` pointing at jsdom, d3, chart.js, topojson, hammerjs and world-atlas).

## Releases

A release is a zip of the changed files, its sha256, and a `DEPLOY-vX.md` with the exact steps: unzip over
`main`, run any migrations, regenerate, run the two gates, stage with
`git add -u && xargs git add < FILES.txt`, commit and push. Workflow YAML is edited by hand on GitHub, never
shipped in a zip.

## Run locally

```bash
python3 -m http.server 8000
```

Then open http://localhost:8000. The data files in the repo are current to the last bot commit, so no API
keys are needed to browse. To run a fetcher yourself you need `requests` (and `openpyxl`, `xlrd` for the UK
tables) and the matching secrets: `FRED_API_KEY` for most economies, `ESTAT_APP_ID` for Japan, and
`MOSPI_USERNAME` and `MOSPI_PASSWORD` for India. A fetcher without its key logs a note and keeps the stored
data.

## Contact

contact@theeconomicatlas.com
