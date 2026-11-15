# v1.9.131: data-quality fixes from the 15 Nov audit

## Currency conversion (US$)
- Indicator pages: US$ GDP converts each quarter at its own rate, then sums four quarters (was the four-quarter total at the latest quarter's rate). Generator bakes `rawPoints` for this.
- Indicator pages: inflation-adjusted US$ converts at one rate, the latest year's average, as the country pages do. Real growth in dollars now equals published real growth.
- Every surface (indicator kit, country pages, chart maker, Compare, Dashboard): no dollar value before `fx.floor` or before the FX history starts (was converted at the earliest rate). Compare's note names the right first year.
- Every copy of `rateForPeriod` (65): with an annual FX history, a quarter or month takes its own year's rate. It used to take the nearest year by date, so Q3 and Q4 got the next year's rate (AR, CZ, HU, IS, ID, PH, PL, RO, TR).
- US and Japan: the per-capita GDP chart shows calendar years, the same figure as the tile. The Dashboard uses the mean of the four annual-rate quarters, not Q4.
- Dashboard map: series already in US$ are rescaled, not converted again (Swiss GDP $1.04tn, not $1.26tn).

## Same figure on every page
- 10-year yields (UK, US, CA, JP, EZ): indicator page, embed and ranking use the daily series the tile uses. Daily periods are labelled ("12 Nov 2026"), with a 10-day staleness rule.
- GDP growth ranking: uses each country's published q/q SA figure where one exists. GDP Growth Rate pages now say which measure they show (quarter on quarter / annualised / year on year).
- Embeds: the UK three-month labour figures keep "Jun–Aug 2026" after the live refresh.
- Percentage tiles: the change is the gap between the two figures as shown.
- JSON-LD temporalCoverage ends at the quarter's last month.

## Sources
- Unemployment for Canada, Australia and Mexico now comes straight from the OECD monthly labour statistics (`oecd_unemp.py`, as Korea, Israel and Turkey). FRED stays as the fallback.

## Copy
- Info (i) panels: a toggle note appears only where that toggle changes the figure (country pages, Compare, Dashboard).
- Turkey and Argentina: the USD notes now describe what the site actually does.
- Double hyphen removed from 32 country pages.

## Gates
- `generated_pages_gate.py` reads the daily bond files; the gate, generator and methodology module know "days". The methodology test anchor is updated.
