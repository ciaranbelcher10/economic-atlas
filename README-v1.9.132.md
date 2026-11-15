# v1.9.132: monthly exchange rates are monthly averages

The fetch scripts turned FRED's daily exchange rates (DEX*) into months by keeping the last day of each month, so every fx_to_usd history held month-end rates (EUR/USD Jan 2024 stored as 1.0855; the January average was 1.0905). Every dollar figure converted with them was slightly off. It was found by comparing the site's 2024 US$ GDP with the World Bank: Mexico was 2.3% low.

fetch_fred now averages the daily values within each month for DEX* series (33 scripts; Singapore separately). China and Malaysia get fetch_fred_avg for fx_to_usd. No other daily series changes (policy rates keep their latest value). The data files take the new histories on the next data run.

World Bank cross-check of 2024 US$ GDP before this fix (20 economies):
- Within 1%: CN, FR, IT, ES, KR, ID, TR, PL, AR, ZA, UK.
- Revisions newer than the World Bank's copy: JP (Cabinet Office 2020-benchmark figure $4,186.9bn; site $4,196bn), CH (FSO revised 2024 to CHF 854bn; site $969.9bn), US, DE.
- Basis difference: IN (World Bank uses the April-March fiscal year).
