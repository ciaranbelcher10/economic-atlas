#!/usr/bin/env python3
"""v1.9.138: say exactly how euro-area GDP is valued before each country adopted the euro, and what Convert to
USD$ does with those years.

Eurostat's CP_MEUR series (namq_10_gdp), which these pages serve, converts every year before a country adopted the
euro at that period's market exchange rate (against the ECU before 1999). Several info panels said the years were
converted at the fixed conversion rate, which is what the World Bank does and what this data does not do. The
verification run of 15 Nov 2026 found the two valuations differing by up to 34% in early years (Lithuania 1995),
and by 4 to 5% in 1995 for original members (ECU against the fixed rate).

Market-rate euro is kept on purpose: it is the same euro as each country's trade figures (Eurostat, euro at market
rates) and as Convert to USD$ (the actual EUR/USD rate), so every euro and dollar figure for a country sits on one
basis. The text below says so.

Also: the dollar text on euro pages and the US$ banner on every page said points before the exchange-rate
history "fall back to the earliest rate"; since v1.9.131 they have no dollar figure. Idempotent; run from repo root.
"""
import glob
import json
import re

# country page, data-metric-sources name, currency, adoption year, fixed rate (units per euro)
LATE = [
    ("greece", "Greece", "drachma", 2001, "340.750"),
    ("slovenia", "Slovenia", "tolar", 2007, "239.640"),
    ("cyprus", "Cyprus", "Cyprus pound", 2008, "0.585274"),
    ("malta", "Malta", "Maltese lira", 2008, "0.429300"),
    ("slovakia", "Slovakia", "koruna", 2009, "30.1260"),
    ("estonia", "Estonia", "kroon", 2011, "15.6466"),
    ("latvia", "Latvia", "lats", 2014, "0.702804"),
    ("lithuania", "Lithuania", "litas", 2015, "3.45280"),
    ("croatia", "Croatia", "kuna", 2023, "7.53450"),
    ("bulgaria", "Bulgaria", "lev", 2026, "1.95583"),
]
ORIGINAL = [("austria", "Austria"), ("belgium", "Belgium"), ("finland", "Finland"), ("luxembourg", "Luxembourg"),
            ("netherlands", "Netherlands"), ("portugal", "Portugal")]

MARK = "Before "   # sentence start used to detect an earlier run (with the country name check below)


def late_note(name, cur, year, rate):
    return (f" Before {name} adopted the euro on 1 January {year}, Eurostat converts the {cur} figures into euro "
            f"at each period's market exchange rate (against the ECU before 1999), the same basis as {name}'s trade "
            f"figures and the US dollar conversion. Changes over those years include exchange-rate movements. The "
            f"World Bank converts the same years at the fixed conversion rate of {rate} {cur} per euro, so its euro "
            f"figures for those years differ.")


def orig_note(name):
    return (f" Figures for 1995 to 1998, before the euro, are in ECU at market exchange rates; the World Bank converts "
            f"those years at the fixed conversion rate instead, so its figures for them differ by a few per cent.")


DOLLAR_EUR = ("“Convert to USD$” converts each quarter at its own months' average EUR/USD rate (FRED's "
              "DEXUSEU, which starts in January 1999). Periods before 1999 have no dollar figure.")
DOLLAR_RE = re.compile(r"\\u201cConvert to USD\$\\u201d converts each historical point using that point's OWN "
                       r"contemporaneous EUR/USD rate \(monthly resolution, from FRED's DEXUSEU series, which starts "
                       r"1999-01, the euro's launch\)\.[^\"]*")
DOLLAR_RE_JSON = re.compile(r"“(?:Dollarise|Convert to USD\$)” converts each historical point using that point's "
                            r"OWN contemporaneous EUR/USD rate \(monthly resolution, from FRED's DEXUSEU series, which "
                            r"starts 1999-01, the euro's launch\)\.[^\"]*")
BANNER_OLD = ": `figures before ${fx.history[0][0]} use the earliest available rate (no genuine historical rate exists further back)`"
BANNER_NEW = ": `figures before ${fx.history[0][0]} are not shown in dollars (no exchange-rate history before then)`"


def esc(t):
    return t.encode("ascii", "backslashreplace").decode("ascii").replace("\\x", "\\u00")


def page(fn, note):
    s = open(fn, encoding="utf-8").read()
    t = s
    i = t.index("const INFO_CONTENT")
    j = t.index("gdp_level: {", i)
    k = t.index("description: \"", j) + len("description: \"")
    end = t.index("\",", k)
    desc = t[k:end]
    if note and esc(note.strip()[:40]) not in desc:
        t = t[:k] + desc + esc(note) + t[end:]
    t = DOLLAR_RE.sub(lambda m: esc(DOLLAR_EUR), t)
    if t != s:
        open(fn, "w", encoding="utf-8").write(t)
        return True
    return False


def main():
    changed = []
    src = json.load(open("data-metric-sources.json", encoding="utf-8"))
    for fn_, name, cur, year, rate in LATE:
        if page(f"{fn_}.html", late_note(name, cur, year, rate)):
            changed.append(fn_)
        e = src.get(name, {}).get("gdp_level")
        if e and late_note(name, cur, year, rate).strip()[:40] not in e.get("description", ""):
            e["description"] = e["description"] + late_note(name, cur, year, rate)
    for fn_, name in ORIGINAL:
        if page(f"{fn_}.html", orig_note(name)):
            changed.append(fn_)
        e = src.get(name, {}).get("gdp_level")
        if e and orig_note(name).strip()[:40] not in e.get("description", ""):
            e["description"] = e["description"] + orig_note(name)
    # dollar text on every euro page (originals using other GDP sources included) and in the citation file
    for f in glob.glob("*.html"):
        if f.replace(".html", "") in changed:
            continue
        s = open(f, encoding="utf-8").read()
        t = DOLLAR_RE.sub(lambda m: esc(DOLLAR_EUR), s).replace(BANNER_OLD, BANNER_NEW)
        if t != s:
            open(f, "w", encoding="utf-8").write(t)
            changed.append(f.replace(".html", ""))
    for f in [f"{x}.html" for x in changed]:
        s = open(f, encoding="utf-8").read()
        t = s.replace(BANNER_OLD, BANNER_NEW)
        if t != s:
            open(f, "w", encoding="utf-8").write(t)
    for name, ent in src.items():
        for k, v in ent.items():
            if isinstance(v, dict) and isinstance(v.get("dollar"), str):
                v["dollar"] = DOLLAR_RE_JSON.sub(DOLLAR_EUR, v["dollar"])
    raw = open("data-metric-sources.json", encoding="utf-8").read()
    out = json.dumps(src, ensure_ascii=False, indent=2) + ("\n" if raw.endswith("\n") else "")
    open("data-metric-sources.json", "w", encoding="utf-8").write(out)
    print(f"pages changed: {len(set(changed))}")


if __name__ == "__main__":
    main()
