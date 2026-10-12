"""
One place that says, for every country page, which exchange rates it shows
and how each is written. Used by fetch_fx_daily.py (builds the data) and
generate_indicator_pages.py (builds the exchange-rate indicator pages), so
the two can never disagree about a symbol, a unit or which way a rate runs.

Convention (v1.6.16): every rate is quoted as dollars, euros or pounds per
unit of the HOME currency, so a rising number always means a stronger home
currency. Where one unit is worth a tiny amount, the rate is given per a
round number of units instead ("$0.64 per ¥100"), fixed per currency so the
label never changes as the rate moves.
"""

# Federal Reserve H.10 daily series on FRED. "usd_per_unit" says which way
# the Fed publishes it: True = US$ per 1 unit (EUR, GBP, AUD), False = units
# per US$1 (everything else).
H10 = {
    "EUR": ("DEXUSEU", True), "GBP": ("DEXUSUK", True), "AUD": ("DEXUSAL", True),
    "CAD": ("DEXCAUS", False), "JPY": ("DEXJPUS", False), "BRL": ("DEXBZUS", False),
    "CHF": ("DEXSZUS", False), "DKK": ("DEXDNUS", False), "INR": ("DEXINUS", False),
    "KRW": ("DEXKOUS", False), "MXN": ("DEXMXUS", False), "NOK": ("DEXNOUS", False),
    "SEK": ("DEXSDUS", False), "SGD": ("DEXSIUS", False), "THB": ("DEXTHUS", False),
    "CNY": ("DEXCHUS", False),
    "ZAR": ("DEXSFUS", False),
    "MYR": ("DEXMAUS", False),
    "NZD": ("DEXUSNZ", True),
    "TWD": ("DEXTAUS", False),
}

# Currencies with no free official daily or monthly series: World Bank
# PA.NUS.FCRF annual average, read from the country's own data file
# (fx_to_usd, local currency per US$).
ANNUAL = {"ARS", "CLP", "COP", "IDR", "ILS", "MAD", "PLN", "TRY", "CZK", "HUF", "RON", "SAR", "PHP", "VND", "NGN", "EGP"}

SYMBOL = {"USD": "$", "EUR": "\u20ac", "GBP": "\u00a3", "JPY": "\u00a5", "CAD": "C$", "AUD": "A$",
          "MXN": "MX$", "BRL": "R$", "SGD": "S$", "INR": "\u20b9", "KRW": "\u20a9", "IDR": "Rp",
          "ILS": "\u20aa", "ZAR": "R", "CNY": "CN\u00a5",
          "THB": "\u0e3f", "TRY": "\u20ba", "ARS": "AR$", "CLP": "CLP$", "COP": "COL$", "MYR": "RM", "NZD": "NZ$", "PHP": "\u20b1", "TWD": "NT$", "VND": "\u20ab", "NGN": "\u20a6", "EGP": "E\u00a3"}
NAME = {"USD": "US dollar", "EUR": "euro", "GBP": "pound", "JPY": "yen", "CAD": "Canadian dollar",
        "AUD": "Australian dollar", "MXN": "Mexican peso", "BRL": "Brazilian real", "SGD": "Singapore dollar",
        "INR": "Indian rupee", "KRW": "South Korean won", "IDR": "Indonesian rupiah", "ILS": "Israeli shekel",
        "ZAR": "South African rand", "CHF": "Swiss franc", "DKK": "Danish krone", "SEK": "Swedish krona",
        "NOK": "Norwegian krone", "PLN": "Polish zloty", "MAD": "Moroccan dirham", "THB": "Thai baht",
        "ARS": "Argentine peso", "CLP": "Chilean peso", "COP": "Colombian peso", "TRY": "Turkish lira",
        "CNY": "Chinese yuan",
        "MYR": "Malaysian ringgit",
        "NZD": "New Zealand dollar",
        "CZK": "Czech koruna",
        "HUF": "Hungarian forint",
        "RON": "Romanian leu",
        "SAR": "Saudi riyal",
        "PHP": "Philippine peso",
        "TWD": "New Taiwan dollar",
        "VND": "Vietnamese dong",
        "NGN": "Nigerian naira",
        "EGP": "Egyptian pound"}
QUOTE_NAME = {"USD": "US dollars", "EUR": "euros", "GBP": "pounds"}

# Units of home currency per quoted figure, where one unit is worth very little.
SCALE = {"JPY": 100, "INR": 100, "HUF": 100, "THB": 100, "TRY": 100, "KRW": 1000, "ARS": 1000,
         "CLP": 1000, "COP": 1000, "IDR": 10000, "PHP": 100, "TWD": 100, "VND": 10000, "NGN": 1000, "EGP": 100}

# Where a currency was redenominated or replaced after hyperinflation, the
# World Bank still reports the whole history in today's units, so the early
# years run to absurd sizes ($72 trillion per ARS 1,000 in 1963) and flatten
# everything since. Charts start when the current currency began; the
# figures themselves are untouched and the chart description says why.
SERIES_START = {
    "ARS": ("1992", "the current peso, introduced in 1992"),
    "CLP": ("1976", "the current peso, reintroduced in 1975"),
    "ILS": ("1986", "the new shekel, introduced in 1985"),
    "PLN": ("1995", "the redenominated zloty of 1995"),
    "TRY": ("2005", "the new lira of 2005"),
    # v1.7.51: Vietnam ran multiple official rates until the March 1989
    # reform; the World Bank figures for 1983 to 1988 (1.0 to 612 dong per
    # US$) are not market rates and pushed the axis to $10,000 per 10,000 dong.
    "VND": ("1989", "the unified exchange rate of the 1989 reform",
            "earlier official rates were not market rates"),
    # v1.7.53 (run 1 audit, 12 Oct 2026): the naira was fixed until 1986 and
    # held at 21.9 per US$ from 1994 to 1998 while the market rate was far
    # weaker; the official and market rates were unified in 1999.
    "NGN": ("1999", "the unified exchange rate of 1999",
            "earlier official rates were fixed, not market rates"),
    # The pound was administratively fixed (0.7 per US$ through the 1980s)
    # until the rates were unified in 1991.
    "EGP": ("1991", "the unified exchange rate of 1991",
            "earlier official rates were fixed, not market rates"),
}

EURO_MEMBERS = {"Austria", "France", "Germany", "Ireland", "Italy", "Netherlands", "Spain", "Belgium", "Portugal", "Finland", "Greece", "Slovakia", "Croatia", "Bulgaria", "Lithuania", "Estonia", "Latvia", "Slovenia", "Luxembourg", "Cyprus", "Malta"}

# country -> (home currency, data-file suffix, quote currencies in display order)
COUNTRY_FX = {
    "UK": ("GBP", "uk", ["USD", "EUR"]),
    "US": ("USD", "us", ["EUR", "GBP"]),
    "Eurozone": ("EUR", "ez", ["USD", "GBP"]),
    "Austria": ("EUR", "at", ["USD", "GBP"]), "France": ("EUR", "fr", ["USD", "GBP"]),
    "Germany": ("EUR", "de", ["USD", "GBP"]), "Ireland": ("EUR", "ie", ["USD", "GBP"]),
    "Italy": ("EUR", "it", ["USD", "GBP"]), "Netherlands": ("EUR", "nl", ["USD", "GBP"]),
    "Spain": ("EUR", "es", ["USD", "GBP"]),
    "Switzerland": ("CHF", "ch", ["EUR", "USD"]), "Denmark": ("DKK", "dk", ["EUR", "USD"]),
    "Sweden": ("SEK", "se", ["EUR", "USD"]), "Norway": ("NOK", "no", ["EUR", "USD"]),
    "Poland": ("PLN", "pl", ["EUR", "USD"]), "Morocco": ("MAD", "ma", ["EUR", "USD"]),
    "Japan": ("JPY", "jp", ["USD"]), "Canada": ("CAD", "ca", ["USD"]), "Australia": ("AUD", "au", ["USD"]),
    "Mexico": ("MXN", "mx", ["USD"]), "Brazil": ("BRL", "br", ["USD"]), "India": ("INR", "in", ["USD"]),
    "South Korea": ("KRW", "kr", ["USD"]), "Singapore": ("SGD", "sg", ["USD"]), "Thailand": ("THB", "th", ["USD"]),
    "China": ("CNY", "cn", ["USD"]),
    "South Africa": ("ZAR", "za", ["USD"]), "Argentina": ("ARS", "ar", ["USD"]), "Chile": ("CLP", "cl", ["USD"]),
    "Colombia": ("COP", "co", ["USD"]), "Indonesia": ("IDR", "id", ["USD"]), "Israel": ("ILS", "il", ["USD"]),
    "Turkey": ("TRY", "tr", ["USD"]),
    "Malaysia": ("MYR", "my", ["USD"]),
    "New Zealand": ("NZD", "nz", ["USD"]),
    "Belgium": ("EUR", "be", ["USD", "GBP"]),
    "Portugal": ("EUR", "pt", ["USD", "GBP"]),
    "Finland": ("EUR", "fi", ["USD", "GBP"]),
    "Greece": ("EUR", "gr", ["USD", "GBP"]),
    "Czechia": ("CZK", "cz", ["EUR", "USD"]),
    "Hungary": ("HUF", "hu", ["EUR", "USD"]),
    "Romania": ("RON", "ro", ["EUR", "USD"]),
    "Saudi Arabia": ("SAR", "sa", ["USD"]),
    "Slovakia": ("EUR", "sk", ["USD", "GBP"]),
    "Croatia": ("EUR", "hr", ["USD", "GBP"]),
    "Bulgaria": ("EUR", "bg", ["USD", "GBP"]),
    "Lithuania": ("EUR", "lt", ["USD", "GBP"]),
    "Estonia": ("EUR", "ee", ["USD", "GBP"]),
    "Latvia": ("EUR", "lv", ["USD", "GBP"]),
    "Slovenia": ("EUR", "si", ["USD", "GBP"]),
    "Luxembourg": ("EUR", "lu", ["USD", "GBP"]),
    "Cyprus": ("EUR", "cy", ["USD", "GBP"]),
    "Malta": ("EUR", "mt", ["USD", "GBP"]),
    "Philippines": ("PHP", "ph", ["USD"]),
    "Taiwan": ("TWD", "tw", ["USD"]),
    "Vietnam": ("VND", "vn", ["USD"]),
    "Nigeria": ("NGN", "ng", ["USD"]),
    "Egypt": ("EGP", "eg", ["USD"]),
}

NBSP = "\u00a0"


def home_unit(code):
    """How one quoted lot of the home currency is written: '£1', '¥100', 'CHF 1'."""
    n = SCALE.get(code, 1)
    num = f"{n:,}"
    sym = SYMBOL.get(code)
    return (sym + num) if sym else (code + NBSP + num)


def quote_symbol(quote, home):
    """'$' normally, 'US$' when the home currency is itself a dollar or peso-$."""
    s = SYMBOL[quote]
    if quote == "USD" and "$" in (SYMBOL.get(home) or ""):
        return "US$"
    return s


def pair_key(home, quote):
    return f"fx_{home.lower()}_{quote.lower()}"


def data_file(suffix):
    return f"data-{suffix}.json"


def fx_file(suffix):
    return f"data-fx-{suffix}.json"
