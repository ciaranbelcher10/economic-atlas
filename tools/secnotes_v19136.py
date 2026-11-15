"""v1.9.136: the country section notes, rewritten to the Lithuania standard (claude/v1.9.135-text-review.md).

A note stays only when a reader would otherwise misread a figure: a different headline measure, a break, a
missing series, a currency change. Sources live in the (i); history, narration and source-choice reasons go.
NOTES maps (page, first 60 characters of the current note) to the new text; "" removes the note.
RULES apply to the boilerplate shared by many pages. Used by tools/migrate_v19136.py.
"""
import re

RULES = [
    (r"^CPI is the national consumer price index, taken from the OECD's prices database\.$", ""),
    (r"^CPI is the national consumer price index, taken from the IMF's monthly consumer price data\.$", ""),
    (r"^Inflation here is the EU-harmonised index of consumer prices \(HICP\), published by Eurostat\. It is built to be comparable across EU countries, so it can differ from the national CPI quoted domestically\.$",
     "Inflation is the EU-harmonised index (HICP), which can differ from the national CPI."),
    (r"^Debt and the budget balance are Eurostat's excessive deficit procedure figures for general government(?: \([^)]*\))?, calendar years\.(?: .*)?$", ""),
    (r"^Debt and the budget balance are the IMF World Economic Outlook's general government figures, actual years only\.$", ""),
    (r"^CPI here is an annual figure from the IMF's Asia and Pacific Regional Economic Outlook\. .*$",
     "Inflation is annual; no monthly series is available."),
]

NOTES = {
    ("argentina", "CPI comes directly from INDEC, Argentina's national statistic"): "",
    ("australia", "CPI here is the quarterly series from the OECD's prices datab"):
        "Inflation is the quarterly CPI. The ABS's headline measure is now its monthly CPI.",
    ("belgium", "Inflation is the EU's harmonised index (HICP), the measure th"):
        "Inflation is the EU-harmonised index (HICP), which can differ by a few tenths from Statbel's national CPI. The interest rate is the European Central Bank's deposit facility rate.",
    ("belgium", "Unemployment is Eurostat's monthly, seasonally adjusted rate"): "",
    ("belgium", "Goods only, in euros. Belgium is a transit hub, so goods pass"):
        "Goods only, in euros. Goods passing through Antwerp-Bruges count as both imports and exports.",
    ("belgium", "The 10-year yield is the OECD's monthly average of the Belgia"): "",
    ("bulgaria", "Inflation is the EU's harmonised index (HICP), the measure th"):
        "Inflation is the EU-harmonised index (HICP), shown from 2000; the National Statistical Institute headlines its national CPI, which can differ by a few tenths. The interest rate is the European Central Bank's deposit facility rate from 1 January 2026, when Bulgaria joined the euro.",
    ("bulgaria", "Unemployment is Eurostat's monthly, seasonally adjusted rate"):
        "The Employment Agency's registered unemployment rate, often quoted in Bulgarian news, is a different measure.",
    ("bulgaria", "The 10-year yield is Eurostat's monthly long-term interest ra"):
        "Bulgaria's benchmark bond trades thinly, so the 10-year yield often stays unchanged for months.",
    ("china", "CPI is the national consumer price index, taken from the OECD"):
        "Month-on-month inflation is not shown, as no source publishes the official monthly rate. The interest rate is the one-year loan prime rate (the one-year benchmark lending rate before August 2019), not the seven-day reverse repo rate the People's Bank of China uses for its operations.",
    ("china", "Unemployment is the International Labour Organization's mode"):
        "Unemployment is the International Labour Organization's modelled annual estimate, not the statistics bureau's surveyed urban rate.",
    ("china", "Goods trade from the IMF's international trade in goods data,"):
        "Goods trade is converted from US dollars to yuan at each month's rate. January and February are best read together, as the Lunar New Year moves between them.",
    ("croatia", "Inflation is the EU's harmonised index (HICP), the measure th"):
        "Inflation is the EU-harmonised index (HICP); the Croatian Bureau of Statistics headlines its national CPI, which can differ by a few tenths. The interest rate is the European Central Bank's deposit facility rate from 1 January 2023, when Croatia joined the euro.",
    ("croatia", "Unemployment is Eurostat's monthly, seasonally adjusted rate"):
        "The registered unemployment rate, often quoted in Croatian news, is a different measure.",
    ("croatia", "Goods only, in euros. Croatia imports far more goods than it "):
        "Goods only, in euros; tourism is a service and is not included.",
    ("croatia", "The 10-year yield is Eurostat's monthly long-term interest ra"): "",
    ("cyprus", "Inflation is the EU's harmonised index (HICP), the measure th"):
        "Inflation is the EU-harmonised index (HICP), which can differ by a few tenths from CYSTAT's national CPI. The interest rate is the European Central Bank's deposit facility rate from 1 January 2008, when Cyprus joined the euro.",
    ("cyprus", "Unemployment is Eurostat's monthly, seasonally adjusted rate"):
        "Registered unemployment is a different measure.",
    ("cyprus", "Goods only, in euros. Cyprus usually imports far more goods t"):
        "Goods only, in euros; tourism and shipping are services and are not included. Ships and fuel count as goods, so partners such as the Marshall Islands and Libya can rank highly.",
    ("cyprus", "The 10-year yield is Eurostat's monthly long-term interest ra"):
        "The 10-year yield stays unchanged for long stretches between 2007 and 2015, when Cyprus issued few long-term bonds.",
    ("czechia", "Two inflation measures are shown. The Czech Statistical Offic"):
        "Two inflation measures are shown: the national CPI, which the Czech National Bank targets at 2%, and the EU-harmonised HICP. The national CPI includes owner-occupied housing, so the two can differ by a few tenths.",
    ("czechia", "Unemployment is Eurostat's monthly, seasonally adjusted rate"):
        "The Labour Office's registered unemployment share, often quoted in Czech news, is a different and higher measure.",
    ("czechia", "Goods trade is Eurostat's monthly total with the rest of the "):
        "Goods trade is converted from euros to koruna at each month's ECB rate, so it differs slightly from the Czech Statistical Office's figures.",
    ("czechia", "The 10-year yield is the ECB's monthly long-term interest rat"):
        "The exchange rate is the World Bank's annual average, so it changes once a year.",
    ("egypt", "Inflation is Egypt's consumer price index as the IMF republis"):
        "There is no interest rate on this page, as no current series is available.",
    ("egypt", "Unemployment is the International Labour Organization's mode"):
        "Unemployment is the International Labour Organization's modelled annual estimate. GDP and growth are annual, for fiscal years ending in June.",
    ("egypt", "Goods trade is Egypt's monthly data as the IMF republishes it"):
        "Goods trade is converted from US dollars to Egyptian pounds at each month's rate. February 2016 is shown with exports and imports correctly assigned; the IMF's figures transpose them.",
    ("egypt", "The exchange rate is the World Bank's annual average official"):
        "The exchange rate is the World Bank's annual average, shown from 1991, when official rates were unified.",
    ("estonia", "Inflation is the EU's harmonised index (HICP), the measure th"):
        "Inflation is the EU-harmonised index (HICP), which can differ by a few tenths from Statistics Estonia's national CPI. The interest rate is the European Central Bank's deposit facility rate from 1 January 2011, when Estonia joined the euro.",
    ("estonia", "Unemployment is Eurostat's monthly, seasonally adjusted rate"):
        "Registered unemployment is a different measure.",
    ("estonia", "The 10-year yield is Eurostat's monthly long-term interest ra"):
        "The 10-year yield starts in June 2020, when Estonia first issued a 10-year bond.",
    ("finland", "Inflation is the EU's harmonised index (HICP), the measure th"):
        "Inflation is the EU-harmonised index (HICP). Statistics Finland's national CPI includes owner-occupied housing and usually differs by a few tenths. The interest rate is the European Central Bank's deposit facility rate.",
    ("finland", "Unemployment is Eurostat's monthly, seasonally adjusted rate"):
        "Finnish news usually quotes Statistics Finland's unadjusted or trend figure, which can differ by several tenths.",
    ("finland", "Goods only, in euros. Finland's goods trade is close to balan"):
        "Goods only, in euros. Single deliveries of ships or aircraft can move a month's figure by several hundred million euros.",
    ("finland", "The 10-year yield is the OECD's monthly average of the Finnis"): "",
    ("greece", "Inflation is the EU's harmonised index (HICP), the measure th"):
        "Inflation is the EU-harmonised index (HICP), which includes spending by visitors and can differ by a few tenths from ELSTAT's national CPI. The interest rate is the European Central Bank's deposit facility rate from 2001.",
    ("greece", "Unemployment is Eurostat's monthly, seasonally adjusted rate"):
        "The labour force survey changed method in 2021, so figures before and after are not fully comparable.",
    ("greece", "Goods only, in euros. Greece imports far more goods than it e"):
        "Goods only, in euros; tourism and shipping are services and are not included.",
    ("greece", "The 10-year yield is the OECD's monthly average of the Greek "):
        "There is no 10-year yield for July 2015, when Greek markets were closed.",
    ("hong-kong", "Inflation is the Census and Statistics Department's Composite"): "",
    ("hong-kong", "GDP is quarterly, from the Census and Statistics Department: "):
        "Quarterly growth is seasonally adjusted; the GDP levels are not. Unemployment is the International Labour Organization's modelled annual estimate.",
    ("hong-kong", "Goods trade is Hong Kong's monthly data as the IMF republishes"):
        "Goods trade is converted from US dollars to Hong Kong dollars at each month's rate. Most exports are re-exports of goods made elsewhere.",
    ("hong-kong", "The exchange rate is the Federal Reserve's daily rate. The Ho"):
        "The Hong Kong dollar is linked to the US dollar, so Convert to USD$ changes the level of a series but not its shape.",
    ("hungary", "Two inflation measures are shown. The Hungarian Central Stati"):
        "Two inflation measures are shown: the national CPI, which the Magyar Nemzeti Bank targets at 3%, and the EU-harmonised HICP; their weights differ, so they can differ by a few tenths. In 2022 and 2023 the MNB steered short-term rates with an 18% one-day deposit tender while the base rate stood at 13%.",
    ("hungary", "Unemployment is Eurostat's monthly, seasonally adjusted rate"): "",
    ("hungary", "Goods trade is Eurostat's monthly total with the rest of the "):
        "Goods trade is converted from euros to forint at each month's ECB rate.",
    ("hungary", "Debt and the budget balance are Eurostat's excessive deficit "):
        "Foreign direct investment is not shown, as the available figures include large transit flows that the Magyar Nemzeti Bank excludes from its own measure.",
    ("hungary", "The 10-year yield is the ECB's monthly long-term interest rat"):
        "The exchange rate is the World Bank's annual average, so it changes once a year.",
    ("iceland", "Inflation is Statistics Iceland's national consumer price ind"):
        "Inflation is Statistics Iceland's national CPI, which includes owner-occupied housing. The interest rate is the Central Bank of Iceland's key rate, shown from June 2014, when it took its current form.",
    ("iceland", "GDP and unemployment are Statistics Iceland's figures as the "): "",
    ("iceland", "Goods trade is Statistics Iceland's own monthly external trad"):
        "Goods trade before 2011 is the IMF's series, converted from US dollars at each month's rate, so the series changes source in January 2011.",
    ("iceland", "The exchange rate is the World Bank's annual average official"):
        "The exchange rate is the World Bank's annual average. The OECD's 10-year yield for Iceland ended in August 2022.",
    ("india", "Unemployment is sourced from MoSPI's own Periodic Labour Forc"):
        "Unemployment is monthly from 2025, when MoSPI began publishing it monthly.",
    ("latvia", "Inflation is the EU's harmonised index (HICP), the measure th"):
        "Inflation is the EU-harmonised index (HICP), which can differ by a few tenths from the Central Statistical Bureau's national CPI. The interest rate is the European Central Bank's deposit facility rate from 1 January 2014, when Latvia joined the euro.",
    ("latvia", "Unemployment is Eurostat's monthly, seasonally adjusted rate"):
        "Registered unemployment is a different measure.",
    ("latvia", "The 10-year yield is Eurostat's monthly long-term interest ra"): "",
    ("luxembourg", "Inflation is the EU's harmonised index (HICP), the measure th"):
        "Inflation is the EU-harmonised index (HICP), which can differ by a few tenths from STATEC's national CPI. The interest rate is the European Central Bank's deposit facility rate.",
    ("luxembourg", "Unemployment is Eurostat's monthly, seasonally adjusted rate"):
        "Employment and participation cover residents only, while many people working in Luxembourg live in neighbouring countries. The survey sample is small, so quarterly moves of one to two points are common.",
    ("luxembourg", "Goods only, in euros. Luxembourg usually imports more goods t"):
        "Goods only, in euros; services are not included.",
    ("luxembourg", "The 10-year yield is the OECD's monthly series for Luxembourg "): "",
    ("malaysia", "CPI is the Department of Statistics Malaysia's consumer price"): "",
    ("malaysia", "From DOSM's monthly labour force survey, starting in January "):
        "Labour figures start in January 2011, after the survey was rebased. The employment-to-population ratio is not seasonally adjusted.",
    ("malaysia", "Goods trade as DOSM reports it, in ringgit: exports valued fr"): "",
    ("malaysia", "Debt and the budget balance are the IMF World Economic Outloo"):
        "The general government balance covers all levels of government, so it differs from the federal deficit.",
    ("malaysia", "The exchange rate is the Federal Reserve's daily rate. There "):
        "No 10-year government bond yield is available for Malaysia.",
    ("malta", "Seasonally and calendar adjusted. Figures before Malta joined"):
        "Seasonally and calendar adjusted. Figures before Malta joined the euro in 2008 are converted from Maltese lira at the fixed rate of 0.429300 lira per euro. Real GDP starts in 2000.",
    ("malta", "Inflation is the EU's harmonised index (HICP), the measure th"):
        "Inflation is the EU-harmonised index (HICP), which can differ from the NSO's national retail price index. The interest rate is the European Central Bank's deposit facility rate from 1 January 2008, when Malta joined the euro.",
    ("malta", "Unemployment is Eurostat's monthly, seasonally adjusted rate"):
        "Registered unemployment is a different measure. The survey sample is small, so quarterly moves of a point are common.",
    ("malta", "Goods only, in euros. Malta usually imports far more goods th"):
        "Goods only, in euros; services are not included.",
    ("malta", "The 10-year yield is Eurostat's monthly long-term interest ra"): "",
    ("morocco", "Current account, below, is the only trade-related live series"):
        "No goods trade series is available for Morocco; the current account is shown instead.",
    ("newzealand", "New Zealand measures its consumers price index quarterly, not"):
        "Inflation is quarterly, as New Zealand publishes its CPI four times a year.",
    ("newzealand", "Unemployment is from Stats NZ's Household Labour Force Survey"):
        "Unemployment is quarterly.",
    ("newzealand", "Goods trade from the IMF's international trade in goods data,"):
        "Goods trade is converted from US dollars at each month's rate, so it can differ slightly from Stats NZ's figures.",
    ("newzealand", "Debt and the budget balance are the IMF World Economic Outloo"):
        "Debt and the budget balance are for general government by calendar year, so they differ from the Treasury's core Crown measures for June years.",
    ("newzealand", "The 10-year yield is the OECD's monthly average of the New Ze"): "",
    ("nigeria", "Inflation is Nigeria's consumer price index as the IMF republ"):
        "The CPI was rebased in January 2025, so rates before and after are not strictly comparable. The policy rate is the IMF's copy and runs some months behind the central bank's decisions.",
    ("nigeria", "Unemployment is the International Labour Organization's mode"):
        "Unemployment is the International Labour Organization's modelled annual estimate. GDP and growth are annual.",
    ("nigeria", "There is no monthly goods trade series on this page: the IMF "):
        "No monthly goods trade series is available for Nigeria.",
    ("nigeria", "The exchange rate is the World Bank's annual average official"):
        "The exchange rate is the World Bank's annual average, shown from 1999, when official and market rates were unified.",
    ("pakistan", "Inflation is Pakistan's national consumer price index as the "):
        "No policy rate series is available for Pakistan.",
    ("pakistan", "Unemployment is the International Labour Organization's mode"):
        "Unemployment is the International Labour Organization's modelled annual estimate, shown from 2012. GDP and growth are annual, for fiscal years ending in June.",
    ("pakistan", "Goods trade is Pakistan's monthly data as the IMF republishes"):
        "Goods trade is shown from July 2022; there are no figures for November 2021 to June 2022.",
    ("pakistan", "Debt and the budget balance are the IMF World Economic Outloo"):
        "Pakistan's budget years run July to June.",
    ("pakistan", "The exchange rate is the World Bank's annual average official"):
        "The exchange rate is the World Bank's annual average, shown from 1982, when the rupee's fixed link to the US dollar ended.",
    ("peru", "Inflation is Peru's consumer price index for Metropolitan Lim"):
        "Inflation is the CPI for Metropolitan Lima, the headline measure. The interest rate is the reference rate, shown from September 2003.",
    ("peru", "Unemployment is the International Labour Organization's mode"):
        "Unemployment is the International Labour Organization's modelled annual estimate. Real GDP is not seasonally adjusted, so each quarter is compared with the same quarter a year earlier.",
    ("peru", "Goods trade is the Central Reserve Bank of Peru's monthly tra"):
        "Goods trade is converted from US dollars to soles at each month's rate.",
    ("peru", "The exchange rate is the World Bank's annual average official"):
        "The exchange rate is the World Bank's annual average, shown from 1991, when the sol replaced the inti.",
    ("philippines", "Inflation is the Philippine Statistics Authority's consumer p"):
        "In June 2016 the policy rate was reset from 4.0% to 3.0% when Bangko Sentral ng Pilipinas moved to an interest rate corridor; this was a change in how the rate is set, not an easing.",
    ("philippines", "From PSA's labour force survey, which became monthly in 2021;"):
        "Labour figures are monthly from January 2021 and not seasonally adjusted, so participation and employment dip every January and July.",
    ("philippines", "Goods trade is PSA's monthly data as the IMF republishes it. "):
        "Goods trade is converted from US dollars to pesos at each month's rate.",
    ("philippines", "Debt and the budget balance are the IMF World Economic Outloo"):
        "The general government balance covers all levels of government, so it differs from the national government deficit.",
    ("philippines", "The exchange rate is the World Bank's annual average official"):
        "The exchange rate is the World Bank's annual average. No 10-year government bond yield is available for the Philippines.",
    ("portugal", "Inflation is the EU's harmonised index (HICP), the measure th"):
        "Inflation is the EU-harmonised index (HICP), which can differ by a few tenths from INE's national CPI. The interest rate is the European Central Bank's deposit facility rate.",
    ("portugal", "Unemployment is Eurostat's monthly, seasonally adjusted rate"):
        "Employment and participation are shown from 2009, where the series has a break.",
    ("portugal", "Goods only, in euros. Portugal usually imports more goods tha"):
        "Goods only, in euros; tourism is a service and is not included.",
    ("portugal", "The 10-year yield is the OECD's monthly average of the Portug"): "",
    ("romania", "Two inflation measures are shown. The National Institute of S"):
        "Two inflation measures are shown: the national CPI, which the National Bank of Romania targets at 2.5%, and the EU-harmonised HICP; they differ more than in most EU countries. Both are shown from 2002. The national CPI can be a month behind INS's release.",
    ("romania", "Unemployment is Eurostat's monthly, seasonally adjusted rate"):
        "Unemployment is shown from 2009. Employment and participation rates are not available.",
    ("romania", "Goods trade is Eurostat's monthly total with the rest of the "):
        "Goods trade is converted from euros to lei at each month's ECB rate.",
    ("romania", "Debt and the budget balance are Eurostat's excessive deficit "):
        "GDP is shown from 2000.",
    ("romania", "The 10-year yield is the ECB's monthly long-term interest rat"):
        "The exchange rate is the World Bank's annual average, so it changes once a year. Figures before the July 2005 redenomination are shown in new lei.",
    ("saudiarabia", "Inflation is the General Authority for Statistics' consumer p"):
        "The repo rate is shown from January 2000.",
    ("saudiarabia", "Unemployment is the International Labour Organization's mode"):
        "Unemployment is the International Labour Organization's modelled annual estimate for all residents.",
    ("saudiarabia", "Goods trade is GASTAT's monthly data as the IMF republishes i"): "",
    ("saudiarabia", "Debt and the budget balance are the IMF World Economic Outloo"): "",
    ("saudiarabia", "The riyal's peg to the US dollar means its exchange rate agai"):
        "The riyal is pegged to the US dollar. No 10-year government bond yield is available for Saudi Arabia.",
    ("slovakia", "GDP is Eurostat's quarterly national accounts, seasonally and"):
        "Seasonally and calendar adjusted. Quarterly growth is volatile because car production is a large share of output; the swings match Eurostat's published figures.",
    ("slovakia", "Inflation is the EU's harmonised index (HICP), the measure th"):
        "Inflation is the EU-harmonised index (HICP), which can differ by a few tenths from the national CPI. The interest rate is the European Central Bank's deposit facility rate from 1 January 2009, when Slovakia joined the euro.",
    ("slovakia", "Unemployment is Eurostat's monthly, seasonally adjusted rate"):
        "The labour office's registered unemployment rate, often quoted in Slovak news, is a different measure.",
    ("slovakia", "Goods only, in euros. Cars and electronics dominate Slovakia'"):
        "Goods only, in euros.",
    ("slovakia", "The 10-year yield is the OECD's monthly average of the Slovak"): "",
    ("slovenia", "Inflation is the EU's harmonised index (HICP), the measure th"):
        "Inflation is the EU-harmonised index (HICP), which can differ by a few tenths from SURS's national CPI. The interest rate is the European Central Bank's deposit facility rate from 1 January 2007, when Slovenia joined the euro.",
    ("slovenia", "Unemployment is Eurostat's monthly, seasonally adjusted rate"):
        "Registered unemployment is a different measure.",
    ("slovenia", "Goods only, in euros. Slovenia's trade with Switzerland is un"):
        "Goods only, in euros. Large flows of medicines with Switzerland can move a month's balance sharply.",
    ("slovenia", "The 10-year yield is the OECD's monthly series for Slovenian "): "",
    ("taiwan", "Taiwan's statistics office does not offer its data to automat"):
        "Inflation is annual, from the IMF World Economic Outlook; no monthly series is available. The interest rate is the central bank's discount rate, as in force at the end of each month.",
    ("taiwan", "Unemployment is the annual rate from the IMF World Economic O"):
        "Unemployment is annual.",
    ("taiwan", "Goods trade is Taiwan's monthly customs data as the IMF repub"):
        "Goods trade is converted from US dollars to New Taiwan dollars at each month's rate.",
    ("taiwan", "The exchange rate is the Federal Reserve's daily rate, averag"):
        "No 10-year government bond yield is available for Taiwan.",
    ("vietnam", "Inflation is Vietnam's consumer price index as the IMF republ"): "",
    ("vietnam", "Unemployment is the International Labour Organization's mode"):
        "Unemployment is the International Labour Organization's modelled annual estimate. GDP and growth are annual.",
    ("vietnam", "Goods trade is Vietnam's monthly customs data as the IMF repu"):
        "Goods trade is converted from US dollars to dong at each month's rate; August 2025 uses the average of the July and September rates.",
    ("vietnam", "The exchange rate is the World Bank's annual average official"):
        "The exchange rate is the World Bank's annual average. No 10-year government bond yield is available for Vietnam.",
}


def rewrite(page, text):
    for (p, head), new in NOTES.items():
        if p == page and text.startswith(head):
            return new
    for rx, new in RULES:
        if re.match(rx, text):
            return new
    return text
