"""INDEC (Argentina) release dates for headline indicators -> data-calendar-ar.json.

Run:  python3 fetch_calendar_ar.py

v1.9.60, new. INDEC's release calendar page fills itself from a plain HTML fragment,
/Calendario/FiltrosCalendario/mes/<Mes>-<Año>/<idioma> (the language code is ignored).
Each fragment starts with "<Mes> <Año>", then for each day: the day number, the weekday in
capitals, and pairs of (release title, "16:00hs"). This reads the current month and the
next two.

Only five releases are kept, matched by the start of their Spanish title:
  cpi    Índice de precios al consumidor (IPC). Cobertura nacional
  gdp    Informe de avance del nivel de actividad   (quarterly GDP; not the monthly EMAE)
  trade  Intercambio comercial argentino (ICA)
  jobs   Mercado de trabajo. Tasas e indicadores socioeconómicos
  ppi    Sistema de índices de precios mayoristas (SIPM)
Everything else (surveys, satellite accounts, tourism, and so on) is left out.

Check: every month must have exactly one CPI release; a month without it means the page
changed. If any month cannot be read or fails a check, the existing data-calendar-ar.json
(if any) is left as it is and a "WARNING INDEC: ..." line is printed. Never fails the workflow.
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from datetime import date, datetime, timezone

import requests

from calendar_common import UA, page_lines

URL = "https://www.indec.gob.ar/Calendario/FiltrosCalendario/mes/{mes}-{year}/0"
REFERER = "https://www.indec.gob.ar/indec/web/Calendario-Fecha-0"
OUT = "data-calendar-ar.json"
SRC = "indec.gob.ar release calendar"
MESES = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto",
         "Septiembre", "Octubre", "Noviembre", "Diciembre"]
MONTHS = ["", "January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December"]
DIAS = {"LUNES", "MARTES", "MIERCOLES", "JUEVES", "VIERNES", "SABADO", "DOMINGO"}
KEEP = [
    ("cpi", r"Índice de precios al consumidor \(IPC\)\. Cobertura nacional\.", "INDEC consumer price index (IPC)"),
    ("gdp", r"Informe de avance del nivel de actividad\.", "INDEC GDP advance estimate"),
    ("trade", r"Intercambio comercial argentino \(ICA\)\.", "INDEC trade in goods (ICA)"),
    ("jobs", r"Mercado de trabajo\. Tasas e indicadores socioeconómicos\.", "INDEC labour market (EPH)"),
    ("ppi", r"Sistema de índices de precios mayoristas \(SIPM\)\.", "INDEC wholesale price index (SIPM)"),
]
TRIM = {"Primer": "Q1", "Segundo": "Q2", "Tercer": "Q3", "Cuarto": "Q4"}


def plain(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def period_en(tail: str) -> str:
    """'Octubre de 2026' -> 'October 2026'; 'Tercer trimestre de 2026' -> 'Q3 2026'; else ''."""
    tail = tail.strip().rstrip(".")
    m = re.fullmatch(r"(" + "|".join(MESES[1:]) + r") de (\d{4})", tail)
    if m:
        return f"{MONTHS[MESES.index(m.group(1))]} {m.group(2)}"
    m = re.fullmatch(r"(Primer|Segundo|Tercer|Cuarto) trimestre de (\d{4})", tail)
    return f"{TRIM[m.group(1)]} {m.group(2)}" if m else ""


def parse_month(markup: str, year: int, month: int) -> tuple[list[dict], list[str]]:
    lines = page_lines(markup)
    want = f"{MESES[month]} {year}"
    if not lines or lines[0] != want:
        return [], [f"{want}: fragment starts {lines[:1]}, not the month asked for (bot wall or a changed page?)"]
    events, problems, day, i = [], [], None, 1
    while i < len(lines):
        l = lines[i]
        if re.fullmatch(r"\d{1,2}", l):
            if i + 1 >= len(lines) or plain(lines[i + 1]).upper() not in DIAS:
                problems.append(f"{want}: day {l} is not followed by a weekday")
                break
            try:
                day = date(year, month, int(l))
            except ValueError:
                problems.append(f"{want}: impossible day {l}")
                break
            i += 2
            continue
        if day is None:
            problems.append(f"{want}: release {l[:60]!r} before any day number")
            break
        t = lines[i + 1] if i + 1 < len(lines) else ""
        tm = re.fullmatch(r"(\d{1,2}):(\d{2}) ?hs", t)
        if not tm:
            problems.append(f"{want}: release {l[:60]!r} has no time line (next: {t[:20]!r})")
            break
        for concept, pat, name in KEEP:
            mm = re.match(pat, l)
            if mm:
                per = period_en(l.split(".")[-1])
                h = int(tm.group(1))
                events.append({"date": day.isoformat(), "country": "Argentina", "concept": concept,
                               "name": f"{name}, {per}" if per else name, "source": SRC,
                               "time": f"{h % 12 or 12}:{tm.group(2)}{'am' if h < 12 else 'pm'} Buenos Aires time"})
                break
        i += 2
    if not problems:
        n = sum(e["concept"] == "cpi" for e in events)
        if n != 1:
            problems.append(f"{want}: {n} CPI releases; INDEC publishes exactly one a month")
    return events, problems


def months_from(today: date, n: int = 3) -> list[tuple[int, int]]:
    y, m, out = today.year, today.month, []
    for _ in range(n):
        out.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def main() -> int:
    now = datetime.now(timezone.utc).date()
    events = []
    try:
        s = requests.Session()
        s.headers.update(UA)
        s.headers["Referer"] = REFERER
        for y, m in months_from(now):
            r = s.get(URL.format(mes=MESES[m], year=y), timeout=40)
            r.raise_for_status()
            page = r.content.decode("utf-8", "replace")
            ev, pr = parse_month(page, y, m)
            if pr:
                raise ValueError("; ".join(pr[:3]) + f" | sample: {re.sub(r'\s+', ' ', page[:200])}")
            events += ev
        events = [e for e in events if e["date"] >= now.isoformat()]
        if not events:
            raise ValueError("no upcoming headline release")
    except Exception as e:
        print(f"WARNING INDEC: {type(e).__name__}: {str(e)[:300]}; existing {OUT} kept", file=sys.stderr)
        return 0
    with open(OUT, "w") as f:
        json.dump({"generated": datetime.now(timezone.utc).isoformat(), "country": "Argentina", "events": events}, f, indent=2)
    kinds = {}
    for e in events:
        kinds[e["concept"]] = kinds.get(e["concept"], 0) + 1
    print(f"INDEC: wrote {len(events)} upcoming releases ({', '.join(f'{k} {v}' for k, v in sorted(kinds.items()))}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
