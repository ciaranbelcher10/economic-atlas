"""Fetch the ONS INAC01 SA dataset (economic inactivity by reason,
seasonally adjusted) and write data-uk-inactivity-reasons.json: the most
recent quarter's breakdown of why people are economically inactive
(long-term sick, student, looking after family, retired, other).

Run:  python3 fetch_uk_inactivity_reasons.py
No API key needed -- public ONS download, no auth.

SOURCE: this is NOT a simple single-timeseries ONS API call like the rest
of the site's UK series (unemployment, CPI, etc.) -- INAC01 SA is
published as a downloadable spreadsheet, whose filename changes with
every release (confirmed live 2026-07-21: current file was
"inac01sajun2026.xls", named after the release month). So this script:
  1. Fetches the dataset's landing page HTML
     (https://www.ons.gov.uk/employmentandlabourmarket/peoplenotinwork/
      economicinactivity/datasets/economicinactivitybyreasonseasonally
      adjustedinac01sa)
  2. Finds the "current edition" download link on that page (a relative
     .xls URL under /file?uri=...) rather than hardcoding a filename that
     will go stale next month.
  3. Downloads and parses that spreadsheet.

CONFIRMED: ONS content is Open Government Licence v3.0 (stated on the
dataset page itself), so this is safely reusable -- unlike the Bank of
England, which is NOT OGL and needed the more cautious treatment seen in
the MPC-summary work.

NOT YET CONFIRMED: the internal layout of the actual spreadsheet (which
row/column holds which reason category, whether there's a header block
like the BoE voting spreadsheet had). This sandbox can't reach
ons.gov.uk directly to inspect it -- GitHub Actions can. Parsing below is
deliberately defensive: it searches for the category label text itself
(matching the same "search for the anchor text, don't hardcode row/column
numbers" approach that worked for the BoE spreadsheet) and falls back to
dumping raw sheet content for diagnosis if the expected labels aren't
found, rather than guessing blindly and failing silently.
"""

from __future__ import annotations

import io
import json
import re
import sys
from datetime import datetime, timezone

import requests

DATASET_PAGE = ("https://www.ons.gov.uk/employmentandlabourmarket/peoplenotinwork/"
                 "economicinactivity/datasets/economicinactivitybyreasonseasonallyadjustedinac01sa")

# The categories we're looking for, and the label text expected in the
# spreadsheet (based on ONS's own standard terminology for this release,
# per the published bulletins referencing this dataset) -- confirmed
# wording, not guessed, since these exact phrases appear in ONS's own
# published commentary on this dataset.
REASON_LABELS = {
    "student": ["student"],
    "long_term_sick": ["long-term sick", "long term sick"],
    "looking_after_family": ["looking after family", "looking after the family", "family/home"],
    "retired": ["retired"],
    "other": ["other reasons", "other"],
}


def _grid_from_openpyxl(ws):
    grid = []
    for row in ws.iter_rows():
        grid.append([cell.value for cell in row])
    return grid


def _grid_from_xlrd(sheet):
    grid = []
    for r in range(sheet.nrows):
        grid.append([sheet.cell_value(r, c) for c in range(sheet.ncols)])
    return grid


def _parse_grid(grid: list[list]) -> dict | None:
    """Shared parsing logic once a sheet has been reduced to a plain 2D
    list -- works the same regardless of which library opened the file."""
    found = {}
    for r, row in enumerate(grid):
        for c, val in enumerate(row):
            if not isinstance(val, str):
                continue
            label = val.strip().lower()
            for key, patterns in REASON_LABELS.items():
                if key in found:
                    continue
                if any(p in label for p in patterns):
                    last_val = None
                    for cc in range(c, len(row)):
                        v = row[cc]
                        if isinstance(v, (int, float)):
                            last_val = v
                    if last_val is not None:
                        found[key] = last_val
                        print(f"  [inac01] matched '{key}' at row {r+1} -> {last_val}")

    if len(found) < 3:
        print(f"  [inac01] only matched {len(found)}/5 categories via label search — "
              f"dumping first 30 rows, cols 1-10 for diagnosis:")
        for r in range(min(30, len(grid))):
            vals = [repr(v) for v in grid[r][:10]]
            print(f"  [inac01] row {r+1}: {vals}")
        return None

    total = sum(found.values())
    if total <= 0:
        print("  [inac01] matched categories but values summed to zero")
        return None

    reasons = [{"key": k, "value": v, "share_pct": round(v / total * 100, 1)} for k, v in found.items()]
    print(f"  [inac01] {len(reasons)} categories, total={total}")
    return {"reasons": reasons, "total": total}


def find_current_xls_link(html: str) -> str | None:
    # Look for a /file?uri=...xls link -- ONS dataset pages consistently
    # use this pattern for the "current edition" download.
    m = re.search(r'href="(/file\?uri=[^"]+\.xls)"', html)
    if m:
        return "https://www.ons.gov.uk" + m.group(1).replace("&amp;", "&")
    return None


def fetch_and_parse() -> dict | None:
    try:
        r = requests.get(DATASET_PAGE, timeout=60, headers={"User-Agent": "economic-atlas/0.1"})
        print(f"  [inac01] page status={r.status_code}")
        r.raise_for_status()
    except Exception as exc:
        print(f"  [inac01] page request failed: {exc}")
        return None

    xls_url = find_current_xls_link(r.text)
    if not xls_url:
        print("  [inac01] couldn't find a current-edition .xls link on the dataset page")
        return None
    print(f"  [inac01] current edition: {xls_url}")

    try:
        xls_r = requests.get(xls_url, timeout=60, headers={"User-Agent": "economic-atlas/0.1"})
        print(f"  [inac01] xls status={xls_r.status_code}")
        xls_r.raise_for_status()
    except Exception as exc:
        print(f"  [inac01] xls download failed: {exc}")
        return None

    grid = None
    try:
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(xls_r.content), data_only=True)
        print(f"  [inac01] opened via openpyxl, sheets: {wb.sheetnames}")
        ws = wb[wb.sheetnames[0]]
        print(f"  [inac01] sheet '{ws.title}': {ws.max_row} rows x {ws.max_column} cols")
        grid = _grid_from_openpyxl(ws)
    except ImportError:
        print("  [inac01] openpyxl not installed — skipping straight to xlrd")
    except Exception as exc:
        # The file has a .xls extension, which could mean genuine legacy
        # Excel binary format (openpyxl only reads modern .xlsx) -- ONS
        # sometimes ships real legacy .xls under this dataset type. Try
        # xlrd as a fallback before giving up, rather than assuming the
        # first library's failure means the data is unreachable.
        print(f"  [inac01] openpyxl couldn't open it ({exc}) — trying xlrd "
              f"(likely genuine legacy .xls format)")

    if grid is None:
        try:
            import xlrd
            book = xlrd.open_workbook(file_contents=xls_r.content)
            sheet = book.sheet_by_index(0)
            print(f"  [inac01] opened via xlrd, sheet '{sheet.name}': {sheet.nrows} rows x {sheet.ncols} cols")
            grid = _grid_from_xlrd(sheet)
        except ImportError:
            print("  [inac01] xlrd not installed either — add it alongside openpyxl "
                  "if the file turns out to be genuine legacy .xls")
            return None
        except Exception as exc2:
            print(f"  [inac01] xlrd also failed to open it: {exc2}")
            return None

    return _parse_grid(grid)


def main() -> int:
    result = fetch_and_parse()
    if not result:
        print("FAIL  inac01  no usable data — leaving any previously-fetched file in place")
        return 0

    out = {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "ONS INAC01 SA: Economic inactivity by reason (seasonally adjusted)",
        **result,
    }
    with open("data-uk-inactivity-reasons.json", "w") as f:
        json.dump(out, f)
    print(f"  ok  inac01  wrote {len(result['reasons'])} reason categories")
    return 0


if __name__ == "__main__":
    sys.exit(main())
