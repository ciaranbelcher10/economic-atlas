# v1.9.133: trade converted to local currency at the period's average rate

The OECD "667S" merchandise-trade series are published in US$, and 36 fetch scripts convert them to the page's own currency. They used each quarter's LAST month's exchange rate, while Convert to USD$ converts back at the quarter's AVERAGE rate. So the round trip did not return the published US$ figure: Brazil's last three quarters came back 5-8% above FRED (Q3 2026: FRED US$20.09bn, site US$21.4bn).

_fx_rate_for_period now uses the mean of the period's months (a quarter's three months, a year's twelve). Annual FX histories keep their year's rate. The trade series are reconverted from fresh US$ data on the next data run.

Checked and correct, not bugs: Korea's 2026 quarters (record chip-driven surplus, H1 US$138.3bn) and Mexico's Q2 2026 jump (INEGI monthly surpluses US$4.52bn, 2.26bn and 4.09bn).
