"""Methodology by economy (v1.9.15): what each of the 62 economies' series actually are.

Built on every regeneration from the same catalogue that builds the indicator pages, so the page describes
exactly what readers can see, links to those pages, and cannot drift from the data: it prints each series' own
label (which names the measure, the publisher's identifier and, where stated, the seasonal adjustment),
its frequency, and the adjustment the label establishes. It says "Not stated" rather than guess.

Two kinds of prose are added to that, both guarded:

  - GAPS are computed: a core indicator is "not tracked" for an economy when its catalogue has no entry for it
    (the euro area members' exchange rate is shared by design, and the US is the base currency, so it is not a gap for them);
  - NOTES are written by hand for choices a reader could otherwise misread, each with a check that is evaluated
    against the data at render time. A note whose check fails is NOT printed (the page never states something
    that is no longer true), a warning is logged, and tools/generated_pages_gate.py fails loudly.

This module has no side effects and imports nothing from the generator: the generator passes in what it needs.
"""
from __future__ import annotations

import html
import re

FREQ_WORD = {"months": "Monthly", "quarters": "Quarterly", "years": "Annual"}

# metric slug -> theme, in display order. Every metric in generate_indicator_pages.METRICS must appear (gated).
THEMES = [
    ("Output", ["gdp", "real-gdp", "gdp-growth-rate", "gdp-annual-growth-rate", "productivity"]),
    ("Prices", ["inflation-rate", "inflation-rate-national-definition", "core-inflation-rate", "cpih-inflation-rate",
                "pce-inflation-rate", "producer-price-inflation", "inflation-rate-mom",
                "inflation-rate-mom-seasonally-adjusted", "inflation-rate-qoq", "cpih-inflation-rate-mom"]),
    ("Labour", ["unemployment-rate", "youth-unemployment-rate", "employment-rate", "labour-force-participation-rate",
                "economic-inactivity-rate"]),
    ("Money and markets", ["interest-rate", "10-year-government-bond-yield", "exchange-rate", "business-confidence"]),
    ("External", ["balance-of-trade", "exports", "imports", "trade-intensity", "current-account-to-gdp",
                  "foreign-direct-investment"]),
    ("Public finances", ["government-debt", "government-net-debt", "government-budget", "government-debt-interest"]),
]

# What every economy is expected to have. Each item is satisfied by any one of its slugs. An economy lacking one
# is told so under "Not tracked"; nothing is estimated or filled in.
CORE = [
    ("GDP", ["gdp"]),
    ("Real GDP", ["real-gdp"]),
    ("GDP growth", ["gdp-growth-rate", "gdp-annual-growth-rate"]),
    ("Inflation", ["inflation-rate"]),
    ("Unemployment", ["unemployment-rate"]),
    ("Employment rate", ["employment-rate"]),
    ("Labour force participation", ["labour-force-participation-rate"]),
    ("Policy interest rate", ["interest-rate"]),
    ("10-year bond yield", ["10-year-government-bond-yield"]),
    ("Exchange rate", ["exchange-rate"]),
    ("Business confidence", ["business-confidence"]),
    ("Trade balance", ["balance-of-trade"]),
    ("Current account", ["current-account-to-gdp"]),
    ("Foreign direct investment", ["foreign-direct-investment"]),
    ("Government debt", ["government-debt"]),
    ("Government budget balance", ["government-budget"]),
]
EXCHANGE_RATE_SHARED = ("Exchange rate",)    # the euro area members use the euro's own series: not a gap for them
FX_BASE = {"US"}                             # the dollar is the base currency of "against the US dollar": nothing to track

OECD_QNA_NOTE = "latest quarters from OECD QNA"


def _theme_of(slug):
    for name, slugs in THEMES:
        if slug in slugs:
            return name
    return None


def entry_rows(cslug, entries, adjustment_of):
    """One dict per catalogue entry, grouped and ordered by THEMES, then registry order within a theme."""
    order = {s: (i, j) for i, (_, slugs) in enumerate(THEMES) for j, s in enumerate(slugs)}
    rows = []
    for e in entries:
        slug = e["m"]["slug"]
        s = e["s"]
        label = (s.get("label") or "").strip()
        adj = adjustment_of(label, e["key"], s.get("freq", ""))
        rows.append(dict(theme=_theme_of(slug), slug=slug, title=e["title"], page=f"{cslug}-{slug}", key=e["key"],
                         label=label, freq=FREQ_WORD.get(s.get("freq", ""), s.get("freq", "")),
                         adj=_adj_short(adj, label), order=order.get(slug, (99, 0))))
    rows.sort(key=lambda r: r["order"])
    return rows


def _adj_short(adj, label=""):
    if not adj:
        # Eurostat flags a series "SCA": seasonally and calendar adjusted. The label says so in words of its own,
        # which the shared classifier (written for FRED identifiers) does not read, so say it here.
        if re.search(r"\bSCA\b", label or ""):
            return "Seasonally and calendar adjusted"
        return "Not stated"
    if adj.lower().startswith("not applicable"):
        return "Not applicable"
    return adj


def gaps(entries, country, euro_members):
    """Titles of core indicators this economy's catalogue does not have."""
    have = {e["m"]["slug"] for e in entries}
    out = []
    for title, slugs in CORE:
        if title in EXCHANGE_RATE_SHARED and (country in euro_members or country in FX_BASE):
            continue
        if not any(s in have for s in slugs):
            out.append(title)
    return out


class Ctx:
    """What a note's check may look at: the economy's catalogue and a few generator helpers."""

    def __init__(self, catalogue_by_country, is_rolling3m, growth_coverage):
        self.cat = catalogue_by_country
        self.is_rolling3m = is_rolling3m
        self.growth_coverage = growth_coverage

    def entry(self, country, key):
        for e in self.cat.get(country, {}).get("catalogue", []):
            if e["key"] == key:
                return e
        return None

    def label(self, country, key):
        e = self.entry(country, key)
        return (e["s"].get("label") or "") if e else ""

    def unit(self, country, key):
        e = self.entry(country, key)
        return (e["s"].get("unit") or "") if e else ""


# (economy, text, check). The check receives a Ctx and must return True only while the text is accurate.
NOTES = [
    ("UK",
     "Unemployment, employment and inactivity are the ONS's rolling three-month averages. Each reading is named "
     "for the three months it covers (for example Jun\u2013Aug 2026), not for one month, and is compared with the "
     "previous non-overlapping three months.",
     lambda c: c.entry("UK", "unemployment") is not None
     and all(c.is_rolling3m("UK", k) for k in ("unemployment", "employment", "inactivity", "unemployment_1624")
             if c.entry("UK", k) is not None)),
    ("South Africa",
     "Unemployment is the OECD's seasonally adjusted rate for ages 15 to 64 (FRED series LRUN64TTZAQ156S). "
     "Stats SA's own headline rate is not seasonally adjusted, so the two can differ.",
     lambda c: "LRUN64TTZAQ156S" in c.label("South Africa", "unemployment")
     and ", SA" in c.label("South Africa", "unemployment")),
    ("Switzerland",
     "GDP growth is calculated from the chained-volume series CLVMNACSAB1GQCH. It is not adjusted for major "
     "sporting events, so it can differ from the rate SECO headlines.",
     lambda c: "CLVMNACSAB1GQCH" in c.label("Switzerland", "gdp_growth")),
    ("Poland",
     "The trade balance is Eurostat's goods balance (exports minus imports) in euros. It is left in euros when "
     "Dollarise is switched on.",
     lambda c: "Eurostat" in c.label("Poland", "trade_balance") and "\u20ac" in c.unit("Poland", "trade_balance")),
    ("Argentina",
     "GDP is not seasonally adjusted, so growth is shown year on year: a quarter-on-quarter rate would mostly "
     "show the seasons.",
     lambda c: "not seasonally adjusted" in c.label("Argentina", "gdp_growth")
     and "YoY" in c.label("Argentina", "gdp_growth")),
]


def notes_for(country, ctx, log=print):
    """The hand-written notes for this economy whose checks pass, plus the notes generated from labels."""
    out = []
    for econ, text, check in NOTES:
        if econ != country:
            continue
        try:
            ok = bool(check(ctx))
        except Exception as exc:  # a broken check is a failed check
            ok, text = False, f"{text} ({exc})"
        if ok:
            out.append(text)
        else:
            log(f"WARN  methodology note for {econ} not printed, its check no longer holds: {text[:70]}")
    oecd = [e["title"] for e in ctx.cat.get(country, {}).get("catalogue", [])
            if OECD_QNA_NOTE in (e["s"].get("label") or "")]
    if oecd:
        names = oecd[0] if len(oecd) == 1 else ", ".join(oecd[:-1]) + " and " + oecd[-1]
        out.append(f"The latest quarters of {names}" +
                   " come from the OECD's quarterly national accounts, which carry the national statistics office's "
                   "figures sooner than IMF International Financial Statistics.")
    return out


def esc(s):
    return html.escape(str(s), quote=True)


def render_economy(country, cslug, region, entries, rows, missing, notes):
    out = [f'<section class="panel ind-panel doc-sec mb-econ" id="{esc(cslug)}" data-name="{esc(country)}" '
           f'data-region="{esc(region)}">',
           f'<div class="ind-panelhead"><h2>{esc(country)}</h2>'
           f'<span class="mb-meta">{esc(region)} \u00b7 {len(rows)} indicators</span></div>',
           '<div class="rk-scroll"><table class="doc-table mb-table"><thead><tr><th>Indicator</th><th>Series</th>'
           '<th>Frequency</th><th>Adjustment</th></tr></thead><tbody>']
    theme = None
    for r in rows:
        if r["theme"] != theme:
            theme = r["theme"]
            out.append(f'<tr class="mb-theme"><th colspan="4">{esc(theme)}</th></tr>')
        out.append(f'<tr><th scope="row"><a href="indicators/{esc(r["page"])}">{esc(r["title"])}</a></th>'
                   f'<td>{esc(r["label"])}</td><td>{esc(r["freq"])}</td>'
                   f'<td>{esc(r["adj"])}</td></tr>')
    out.append('</tbody></table></div>')
    out.append('<p class="mb-gaps"><strong>Not tracked:</strong> ' +
               (esc(", ".join(missing)) if missing else "nothing on the core list") + '.</p>')
    if notes:
        out.append('<ul class="mb-notes">' + "".join(f"<li>{esc(n)}</li>" for n in notes) + '</ul>')
    out.append('</section>')
    return "\n".join(out)


def gap_summary(per_country_missing):
    """Core indicator -> economies lacking it, in CORE order."""
    out = []
    for title, _ in CORE:
        lacking = sorted(c for c, m in per_country_missing.items() if title in m)
        out.append((title, lacking))
    return out


def build(catalogue_by_country, countries, adjustment_of, is_rolling3m, euro_members, growth_coverage, log=print):
    """Return (sections_html, summary) for every economy in `countries` ({name: (iso, cslug, alpha2, region)}).
    summary: dict(economies=n, missing={country: [titles]}, gap_table=[(title, [economies])], notes={country: [..]})"""
    ctx = Ctx(catalogue_by_country, is_rolling3m, growth_coverage)
    sections, missing, notes = [], {}, {}
    for country in sorted(countries):
        info = catalogue_by_country.get(country)
        if not info:
            continue
        iso, cslug, _a2, region = countries[country]
        entries = info["catalogue"]
        rows = entry_rows(cslug, entries, adjustment_of)
        missing[country] = gaps(entries, country, euro_members)
        notes[country] = notes_for(country, ctx, log)
        sections.append(render_economy(country, cslug, region, entries, rows, missing[country], notes[country]))
    summary = dict(economies=len(sections), missing=missing, gap_table=gap_summary(missing), notes=notes)
    return "\n".join(sections), summary


def render_gap_table(summary):
    rows = []
    for title, lacking in summary["gap_table"]:
        if lacking:
            rows.append(f'<tr><th scope="row">{esc(title)}</th><td>{len(lacking)}</td>'
                        f'<td>{esc(", ".join(lacking))}</td></tr>')
    if not rows:
        return "<p>Every economy has every core indicator.</p>"
    return ('<div class="rk-scroll"><table class="doc-table mb-gap"><thead><tr><th>Core indicator</th>'
            '<th>Economies without it</th><th>Which</th></tr></thead><tbody>' + "".join(rows) +
            '</tbody></table></div>')
