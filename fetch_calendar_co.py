"""Fetch Colombia's official release dates and write data-calendar-co.json (v1.9.44).

One official source: DANE's release calendar (dane.gov.co/index.php/calendario), read as
three month views (this month and the next two). Every release is a link whose address
carries its date: /calendario/icalrepeat.detail/yyyy/mm/dd/<id>/-/<slug>. Served: cpi
(Indice de Precios al Consumidor), ppi (Indice de Precios del Productor), jobs (Mercado
laboral / GEIH), gdp (Producto Interno Bruto) and trade (Exportaciones, Importaciones,
Balanza comercial). Daily food-price bulletins, surveys and annexes are left out.

Not served: Banco de la Republica rate decisions. Its site sits behind a captcha
(probe of 1 Nov 2026), so no official decision schedule could be read.

The month view gives no release time, so none is given. The first month must parse or
the run fails and the old file is kept; a later month that fails is reported and skipped.
"""
from __future__ import annotations

import html
import re
import sys
import unicodedata
from datetime import date

from calendar_common import clean_name, run_single

OUT = "data-calendar-co.json"
BASE = "https://www.dane.gov.co/index.php/calendario/month.calendar/{y}/{m:02d}/01/-"
SRC = "dane.gov.co calendario (official DANE release calendar)"
LINK_RE = re.compile(r"<a\b[^>]*href=[\"'][^\"']*/calendario/icalrepeat\.detail/(\d{4})/(\d{2})/(\d{2})/\d+/[^\"']*[\"'][^>]*>(.*?)</a>",
                     re.I | re.S)


def fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn").lower()


# (pattern on the accent-free lower-case title, concept, English name)
RULES = [
    (re.compile(r"anex|boletin|sipsa|encuesta de sacrificio"), None, None),
    (re.compile(r"precios al consumidor|\(ipc\)|^ipc\b"), "cpi", "Consumer price index (IPC)"),
    (re.compile(r"precios del productor|\(ipp\)|^ipp\b"), "ppi", "Producer price index (IPP)"),
    (re.compile(r"^mercado laboral\b|gran encuesta integrada|\(geih\)"), "jobs", "Labour market (GEIH)"),
    (re.compile(r"producto interno bruto|\(pib\)|^pib\b"), "gdp", "GDP (PIB)"),
    (re.compile(r"^exportaciones$"), "trade", "Exports"),
    (re.compile(r"^importaciones$"), "trade", "Imports"),
    (re.compile(r"^balanza comercial$"), "trade", "Trade balance"),
]


def parse_month(page: str, year: int, month: int) -> tuple[list[dict], list[str]]:
    events, problems, links = [], [], 0
    for m in LINK_RE.finditer(page):
        y, mo, dd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if (y, mo) != (year, month):
            continue   # days from the neighbouring months shown in the grid belong to those months' views
        links += 1
        title = clean_name(html.unescape(re.sub(r"<[^>]+>", " ", m.group(4))))
        key = fold(title)
        for rx, concept, name in RULES:
            if rx.search(key):
                if concept:
                    events.append({"date": date(y, mo, dd).isoformat(), "country": "Colombia", "concept": concept,
                                   "name": name, "source": SRC, "time": None})
                break
    if links == 0:
        problems.append(f"no release links for {year}-{month:02d} (bot wall or a changed page?)")
    elif links < 15:
        problems.append(f"only {links} release links for {year}-{month:02d}; a month normally has dozens")
    return events, problems


def months_from(today: str, n: int = 3):
    y, m = int(today[:4]), int(today[5:7])
    for _ in range(n):
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def fetch_events(s, today: str) -> list[dict]:
    out = []
    for i, (y, m) in enumerate(months_from(today)):
        try:
            r = s.get(BASE.format(y=y, m=m), timeout=40)
            r.raise_for_status()
            events, problems = parse_month(r.text, y, m)
            if problems:
                raise ValueError("; ".join(problems))
        except Exception as e:  # noqa: BLE001 (first month must work; later ones are best effort)
            if i == 0:
                raise ValueError(f"{y}-{m:02d}: {e}") from e
            print(f"WARNING Colombia {y}-{m:02d} skipped: {e}", file=sys.stderr)
            continue
        out += events
    if not any(e["concept"] in ("cpi", "trade") for e in out):
        raise ValueError("no CPI or trade release found in three months of the calendar")
    return out


def main() -> int:
    return run_single(OUT, "Colombia", fetch_events, "Colombia")


if __name__ == "__main__":
    sys.exit(main())
