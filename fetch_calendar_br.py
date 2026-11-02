"""BCB (Brazil) Copom rate decision dates -> data-calendar-br.json.

Run:  python3 fetch_calendar_br.py

v1.9.61: read live from the BCB's own calendar API, replacing the hand-typed 2026 list.
The bcb.gov.br calendar component (found in probes cal13 to cal15) reads
  /api/servico/sitebcb/calendario?lista=Reuniões do Copom&inicioAgenda='YYYY-MM-DD'&fimAgenda='YYYY-MM-DD'
(the quotes are part of the value, as the site sends them). It returns {"conteudo": [...]},
one entry per meeting DAY: "evento": "Reunião do Copom", "dataEvento": "2026-11-03T03:00:00Z"
(midnight in Brasília, UTC-3). Each meeting runs over two consecutive days and the rate
decision is announced on the evening of the last day, so each run of consecutive days
becomes one event on its last day. The decision is not at a fixed minute, so no time is given.

If the API cannot be read, fails a check, or leaves no upcoming date, the existing
data-calendar-br.json is left as it is and a "WARNING BCB: ..." line is printed.
The run never fails the workflow.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime, timedelta, timezone

import requests

from calendar_common import UA

LISTA = "Reuniões do Copom"
URL = "https://www.bcb.gov.br/api/servico/sitebcb/calendario"
REFERER = "https://www.bcb.gov.br/controleinflacao/calendarioreunioescopom"
OUT = "data-calendar-br.json"
NAME = "Copom Selic rate decision"
SRC = "bcb.gov.br calendar, Reuniões do Copom"
BRT = timezone(timedelta(hours=-3))


def params(today: date) -> dict:
    return {"lista": LISTA, "inicioAgenda": f"'{today.isoformat()}'",
            "fimAgenda": f"'{(today + timedelta(days=400)).isoformat()}'"}


def parse(raw: bytes) -> tuple[list[dict], list[str]]:
    try:
        data = json.loads(raw)
    except ValueError:
        return [], [f"not JSON (bot wall or a changed API?): {raw[:120]!r}"]
    rows = data.get("conteudo") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return [], ["no 'conteudo' list in the response"]
    days, problems = set(), []
    for r in rows:
        if not isinstance(r, dict) or r.get("evento") != "Reunião do Copom":
            problems.append(f"unexpected entry: {str(r)[:120]}")
            continue
        try:
            d = datetime.strptime(str(r.get("dataEvento")), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).astimezone(BRT).date()
        except ValueError:
            problems.append(f"date not read: {r.get('dataEvento')!r}")
            continue
        days.add(d)
    if not days and not problems:
        problems.append("no meeting days in the response")
    events, run = [], []
    for d in sorted(days):
        if run and d - run[-1] != timedelta(days=1):
            events.append(run[-1])
            run = []
        run.append(d)
        if len(run) > 2:
            problems.append(f"meeting of more than two days ending {d}")
    if run:
        events.append(run[-1])
    out = [{"date": d.isoformat(), "country": "Brazil", "concept": "rate_decision", "name": NAME,
            "source": SRC, "time": None} for d in events]
    for y in {d.year for d in events}:
        n = sum(d.year == y for d in events)
        if n > 10:
            problems.append(f"{y}: {n} decisions; Copom meets 8 times a year")
    return out, problems


def main() -> int:
    today = datetime.now(BRT).date()
    try:
        r = requests.get(URL, params=params(today), headers={**UA, "Accept": "application/json", "Referer": REFERER}, timeout=40)
        r.raise_for_status()
        ev, pr = parse(r.content)
        if pr:
            raise ValueError("; ".join(pr[:3]))
        ev = [e for e in ev if e["date"] >= today.isoformat()]
        if not ev:
            raise ValueError("no upcoming decision date")
    except Exception as e:
        print(f"WARNING BCB: {type(e).__name__}: {str(e)[:300]}; existing {OUT} kept", file=sys.stderr)
        return 0
    with open(OUT, "w") as f:
        json.dump({"generated": datetime.now(timezone.utc).isoformat(), "country": "Brazil", "events": ev}, f, indent=2)
    print(f"BCB: wrote {len(ev)} upcoming Copom decisions (next {ev[0]['date']}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
