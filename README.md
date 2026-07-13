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

## UK page structure
Six sections via the category banner: Headline (tiles), GDP, Inflation &
rates, Labour market, Trade, Public finances. Every chart carries a
one-line plain-English explainer and an explicit source.

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
