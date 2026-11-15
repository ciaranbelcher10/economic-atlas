# v1.9.138: the verification package

Every one of the 1,011 stored series was compared with an outside source (verification runs 1 to 3, 15 Nov 2026;
findings in the project document `claude/verification-run-1-findings.md`). This release fixes what the comparison
found, plus the currency-label and GDP-per-person work held for this package.

## Data fixes
- **Real GDP in US dollars** (all economies). Real GDP was converted at the latest year's exchange rate while
  priced in its base year (Argentina 2004 pesos, Turkey 2009 lira, Brazil 1995 reais), which put Argentina's real
  GDP at 0.09% of its nominal GDP in dollars. Real GDP is now expressed in constant prices of the latest complete
  year and converted at that year's average rate (the World Bank's constant-dollar method). `merge_population.py`
  stores `usd_anchor` {year, deflator} on every real GDP series; the country pages, indicator pages, Compare, the
  Dashboard and Chartmaker all read it. Argentina's real GDP is now US$692.7bn against US$792.9bn nominal. The
  "unreliable for high-inflation currencies" warning on Argentina and Turkey is retired.
- **India unemployment** showed MoSPI's urban rate (6.9% in September) as the national rate (all-India 5.0%). The
  fetch now requests the all-India rate and falls back to urban only with an "urban areas only" label; the stored
  series carries that label until the next data run.
- **Korea debt and deficit**: the series guard had kept an older IMF edition for 1995 to 2024 (deficit 2024 -0.78
  against the current -2.63). The current WEO edition replaces it (2012 onward).
- **Switzerland**: GDP was the World Bank's US$ series, the only Swiss money series not in francs; real GDP was a
  FRED copy of Eurostat that had stopped taking revisions (growth off by up to 0.25 points in 7 of 12 quarters).
  GDP, real GDP and growth now come from SECO via the OECD quarterly national accounts, in francs; annual GDP is
  the sum of each calendar year's quarters (from 1980). Swiss GDP is US$1.06tn (IMF 1.061tn), US$117k per person.
- **Thailand**: the baht GDP series never reached the page (the guard kept the longer US$ fallback). Now the
  World Bank's baht series (NY.GDP.MKTP.CN, from 1960). GDP per person matches the World Bank exactly.
- **New Zealand, UK, Switzerland, Thailand exchange rates**: these four scripts kept month-end rates while every
  other economy uses the month's average (since v1.9.132). Up to 3.6% off in single months; New Zealand's trade
  is converted with them. Monthly averages from the next data run.
- **Euro-area current account** mixed the 20- and 21-member aggregates by year. Now EA21 (the current membership)
  from 1999, matching the euro area's GDP.
- **Israel** GDP per person read 0 for 1960 to 1964 (new-shekel values rounded away). Values under 100 keep three
  significant figures; Israel's GDP is stored to four decimals of a million shekels.

## Text
- Euro members: the GDP info panel says how years before euro adoption are valued (Eurostat converts them at market
  rates, against the ECU before 1999; the World Bank uses the fixed conversion rate). Several panels had said the
  fixed rate, which is not what the data does. Market-rate euro is kept because it is the same euro as each
  country's trade figures and the US$ conversion.
- Every "Convert to USD$" text and banner that said early periods "fall back to the earliest rate" now says those
  periods have no dollar figure (the behaviour since v1.9.131). Every real-GDP dollar text describes the one-rate
  conversion. The citation file uses the current toggle names.
- Switzerland, Thailand, India, euro-area current account and New Zealand trade citations follow their new sources.

## Held from earlier in this package
- Currency labels: Australia, Brazil, Canada, Mexico and South Africa store AUD, BRL, CAD, MXN and ZAR instead of a
  bare "$"; "$" means US dollars only (KIT_VERSION 15).
- One GDP-per-person rule in Chartmaker and the Dashboard (calendar years at the year's average rate).
- The homepage "Latest" ticker reads feeds/<economy>.json (mobile.js v47).

## For the data run
`ALLOW_SHRINK` entries in fetch_kr.py (debt_gdp, deficit), fetch_in.py (unemployment) and fetch_ch.py (gdp_level)
let the new series replace the old ones once; remove them after the first data run.
