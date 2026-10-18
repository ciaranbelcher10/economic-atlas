"""Fetch Hong Kong's official release dates and write data-calendar-hk.json (v1.8.14).

One official source: the Census and Statistics Department's annual schedule of regular
press releases, an Excel file each year linked from
censtatd.gov.hk/en/press_release.html (Regular_Press_Releases_Schedule_<year>.xlsx;
the 2027 file covers Sep 2026 to Dec 2027 and the 2026 file Sep 2025 to Dec 2026, one
sheet, columns Release Date, Subject, Sub-subject, Series, Title; probe of 18 Oct 2026).
The files are read with the standard library only (zipfile and XML), so the workflow
needs no spreadsheet package. Releases are issued at 4:30pm Hong Kong time.

Served: Consumer Price Index (cpi), Unemployment and Underemployment (jobs), the
external merchandise trade headline (trade) and Gross Domestic Product titles (gdp).
Every other row is counted and its subject and series printed, so the mapping can be
widened from the Actions log. Not served: HKMA decisions (it follows the US Federal
Reserve and publishes no schedule of its own).
"""
from __future__ import annotations

import io
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from datetime import date, datetime, timedelta, timezone

from calendar_common import clean_name, run_single

OUT = "data-calendar-hk.json"
BASE = "https://www.censtatd.gov.hk"
PAGE = BASE + "/en/press_release.html"
FILE = BASE + "/FileManager/EN/Common/Regular_Press_Releases_Schedule_{y}.xlsx"
SRC = "censtatd.gov.hk regular press releases schedule (official C&SD release schedule)"
TIME = "4:30pm HKT"
M = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def read_xlsx(blob: bytes) -> list[dict]:
    """Rows of the first sheet as {column letter: text} (numbers kept as text)."""
    z = zipfile.ZipFile(io.BytesIO(blob))
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall(f"{{{M}}}si"):
            shared.append("".join(t.text or "" for t in si.iter(f"{{{M}}}t")))
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rid = wb.find(f"{{{M}}}sheets")[0].get(f"{{{R}}}id")
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    target = next(r.get("Target") for r in rels if r.get("Id") == rid)
    path = target[1:] if target.startswith("/") else "xl/" + target
    rows = []
    for row in ET.fromstring(z.read(path)).iter(f"{{{M}}}row"):
        vals = {}
        for c in row.findall(f"{{{M}}}c"):
            col = re.match(r"[A-Z]+", c.get("r")).group(0)
            v, t = c.find(f"{{{M}}}v"), c.get("t")
            if t == "s" and v is not None:
                vals[col] = shared[int(v.text)]
            elif t == "inlineStr":
                vals[col] = "".join(x.text or "" for x in c.iter(f"{{{M}}}t"))
            elif v is not None:
                vals[col] = v.text
        rows.append(vals)
    return rows


def to_date(v: str | None) -> date | None:
    if v is None:
        return None
    v = v.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", v):
        return date.fromisoformat(v[:10])
    if re.fullmatch(r"\d+(\.\d+)?", v):                      # Excel serial day number
        return date(1899, 12, 30) + timedelta(days=int(float(v)))
    return None


def classify(subject: str, series: str, title: str) -> str | None:
    s, t = series.lower(), f"{series} {title}".lower()
    if "consumer price index" in s:
        return "cpi"
    if "unemployment and underemployment" in s or "unemployment and underemployment" in title.lower():
        return "jobs"
    if s.startswith("external merchandise trade"):
        return "trade"
    if "gross domestic product" in t and "chain volume" not in t and "income and expenditure" not in t:
        return "gdp"
    return None


def parse(blob: bytes) -> tuple[list[dict], list[str], dict]:
    rows = read_xlsx(blob)
    head = next((r for r in rows if "Release Date" in r.values()), None)
    if not head:
        return [], ["no 'Release Date' header row in the sheet"], {}
    col = {v: k for k, v in head.items()}
    need = ("Release Date", "Subject", "Series", "Title")
    if any(n not in col for n in need):
        return [], [f"header lacks {[n for n in need if n not in col]}"], {}
    events, problems, skipped, dated = [], [], {}, 0
    for r in rows[rows.index(head) + 1:]:
        d = to_date(r.get(col["Release Date"]))
        if d is None:
            continue
        dated += 1
        subject, series, title = (r.get(col[k], "") or "" for k in ("Subject", "Series", "Title"))
        concept = classify(subject, series, title)
        if concept is None:
            skipped[(subject, series)] = skipped.get((subject, series), 0) + 1
            continue
        events.append({"date": d.isoformat(), "country": "Hong Kong", "concept": concept,
                       "name": clean_name(title or series), "source": SRC, "time": TIME})
    if dated < 20:
        problems.append(f"only {dated} dated rows; the schedule normally lists over 100")
    elif not any(e["concept"] == "cpi" for e in events):
        problems.append("no Consumer Price Index row found")
    return events, problems, skipped


def fetch_events(s, today: str) -> list[dict]:
    page = s.get(PAGE, timeout=40)
    page.raise_for_status()
    years = {int(y) for y in re.findall(r"Regular_Press_Releases_Schedule_(\d{4})\.xlsx", page.text)}
    this = datetime.now(timezone.utc).year
    years |= {this, this + 1}
    events, parsed, skipped_all = [], 0, {}
    for y in sorted(years):
        r = s.get(FILE.format(y=y), timeout=60)
        if r.status_code == 404:
            continue
        r.raise_for_status()
        ev, problems, skipped = parse(r.content)
        if problems:
            raise ValueError(f"{y} file: " + "; ".join(problems))
        events += ev
        parsed += 1
        for k, n in skipped.items():
            skipped_all[k] = max(skipped_all.get(k, 0), n)
    if not parsed:
        raise ValueError("no schedule file could be fetched")
    if skipped_all:
        top = sorted(skipped_all.items(), key=lambda kv: -kv[1])[:8]
        print("note Hong Kong: rows not served (subject, series: count): " + "; ".join(f"{a} / {b}: {n}" for (a, b), n in top))
    return events


def main() -> int:
    return run_single(OUT, "Hong Kong", fetch_events, "Hong Kong")


if __name__ == "__main__":
    sys.exit(main())
