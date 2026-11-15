# v1.9.137: Thailand GDP in the rankings (hotfix); Methodology and About captions

**Thailand.** Thailand's GDP comes from the World Bank in US dollars (US$577bn for 2025). The page generator decided which economies were already in dollars from a fixed list (US, Switzerland), so the rankings treated Thailand's dollars as baht and converted them again: US$17.6bn, last of 62, and US$246 per person. The country page was right throughout. The generator now reads the GDP series itself (`gdp_in_usd`): already in dollars when the economy is listed or the series is the World Bank's current-US$ figure. Thailand is now 30th (US$577.01bn) and US$8,057 per person, matching the World Bank. Its GDP indicator page no longer offers Convert to USD$, which would have converted a second time too. The other economies' rank positions shift accordingly (41 indicator pages). Compare and the Dashboard already read the unit and were correct.

**Captions.** The Methodology and About captions run the full width of the page instead of a 62-character column.

The data package replaces the list with explicit currency units in every data file (BRL, CAD, AUD and MXN are stored as a bare "$m" today), and adds a gate that fails when an economy's US$ GDP differs between its country page and the rankings.
