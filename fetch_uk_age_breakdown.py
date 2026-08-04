"""Fetch the ONS A05 SA dataset (employment, unemployment and economic
inactivity by age group, seasonally adjusted) and write
data-uk-age-breakdown.json: the most recent period's unemployment and
inactivity rates broken down by age band.

Run:  python3 fetch_uk_age_breakdown.py
No API key needed -- public ONS download, no auth.

SOURCE: https://www.ons.gov.uk/employmentandlabourmarket/peopleinwork/
employmentandemployeetypes/datasets/employmentunemploymentandeconomic
inactivitybyagegroupseasonallyadjusteda05sa/current
Confirmed OGL v3.0. Same mechanism as INAC01: filename changes every
release (confirmed live 2026-07-21, current was "a05saapr2026.xls"), so
this scrapes the landing page for the current edition link rather than
hardcoding a filename.

CONFIRMED LIVE (2026-08-04): the internal layout is a 4-row hierarchical
header, not the single-cell "metric + age band" text this script
originally searched for -- that's exactly why the first two live runs
found nothing. Row 5 carries the age band (sparse: only the first column
of each block is populated, e.g. "Aged 16 and over", "Aged 16-64 " --
note the trailing space, "Aged 16-17"), row 6 carries the metric
(Employment/Unemployment/Activity/Inactivity, also sparse), row 7 gives
"level" or "rate (%)" for every column, and row 8 is the CDID code
(informational only -- position, not the code itself, is what maps a
column to its band+metric). Confirmed identical across the 'People',
'Men', and 'Women' sheets; this uses 'People' (the blended total) since
that matches what the site displays elsewhere. Data rows start at row
10, most recent at the bottom.

Only 20 of the (at least) 64 data columns have been directly observed,
covering bands "16 and over", "16-64", and "16-17" -- the remaining ~44
columns almost certainly continue the same 8-columns-per-band pattern
(Employment/Unemployment/Activity/Inactivity x level/rate) for the other
bands ONS publishes here, but since that's still inference rather than
something actually seen, extraction below reads the header rows at
runtime and uses whatever bands it actually finds -- it never assumes a
fixed set or fixed column count. If ONS's real bands differ from the
"25-49"/"50-64" placeholders previously used on the site, whatever is
actually found here is written out with its real label.
"""

from __future__ import annotations

import io
import json
import re
import sys
from datetime import datetime, timezone

import requests

DATASET_PAGE = ("https://www.ons.gov.uk/employmentandlabourmarket/peopleinwork/"
                 "employmentandemployeetypes/datasets/"
                 "employmentunemploymentandeconomicinactivitybyagegroupseasonallyadjusteda05sa/current")

# Confirmed live 2026-08-04 -- see module docstring. Only metric names
# matching this set are trusted; anything else means the sheet layout has
# changed and extraction should fail loudly rather than guess.
KNOWN_METRICS = {"Employment", "Unemployment", "Activity", "Inactivity"}
WANTED_METRICS = {"Unemployment": "unemployment_rate", "Inactivity": "inactivity_rate"}


def _grid_from_openpyxl(ws):
    return [[cell.value for cell in row] for row in ws.iter_rows()]


def _grid_from_xlrd(sheet):
    return [[sheet.cell_value(r, c) for c in range(sheet.ncols)] for r in range(sheet.nrows)]


def _to_float(v):
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = v.strip()
        if s in ("", "..", "-", ":", "n/a"):
            return None
        try:
            return float(s.replace(",", ""))
        except ValueError:
            return None
    return None


def _s(v):
    """Cell value as a stripped string, tolerant of None/non-str values."""
    if v is None:
        return ""
    return str(v).strip()


def find_current_xls_link(html: str) -> str | None:
    m = re.search(r'href="(/file\?uri=[^"]+\.xls)"', html)
    if m:
        return "https://www.ons.gov.uk" + m.group(1).replace("&amp;", "&")
    return None


def _dump(grid, label, n=40, cols=14):
    print(f"  [a05] {label} — dumping first {n} rows, cols 1-{cols}:")
    for r in range(min(n, len(grid))):
        print(f"  [a05] row {r+1}: {[repr(v) for v in grid[r][:cols]]}")


def _extract_from_people_sheet(grid):
    """Row 5 (idx 4) = age band, row 6 (idx 5) = metric, row 7 (idx 6) =
    level/rate, data from row 10 (idx 9) onward. Returns None if the
    header doesn't match what was confirmed live, rather than guessing."""
    if len(grid) < 10:
        return None
    band_row, metric_row, kind_row = grid[4], grid[5], grid[6]

    def forward_fill(row):
        out, last = [], None
        for v in row:
            sv = _s(v)
            if sv:
                last = sv
            out.append(last)
        return out

    bands = forward_fill(band_row)
    metrics = forward_fill(metric_row)

    ncols = len(kind_row)
    columns = []  # (col_index, band, metric, kind)
    for c in range(1, ncols):
        metric = (metrics[c] or "").strip()
        kind = _s(kind_row[c])
        if metric not in KNOWN_METRICS or kind not in ("level", "rate (%)"):
            continue
        band = (bands[c] or "").strip()
        if not band:
            continue
        columns.append((c, band, metric, kind))

    if not columns:
        print("  [a05] header rows didn't match the confirmed layout "
              "(no columns with a recognised metric+kind) -- ONS may "
              "have changed the format since 2026-08-04.")
        return None

    # Most recent period: last row where the date-label column has text
    # and at least one rate column has a numeric value.
    period_row_idx = None
    for r in range(len(grid) - 1, 8, -1):
        label = _s(grid[r][0]) if grid[r] else ""
        if not label:
            continue
        if any(_to_float(grid[r][c]) is not None for c, _, _, kind in columns if kind == "rate (%)" for c in [c]):
            period_row_idx = r
            break
    if period_row_idx is None:
        print("  [a05] found a valid header but no data row with usable rate values")
        return None

    period_label = _s(grid[period_row_idx][0])
    by_band: dict[str, dict[str, float]] = {}
    for c, band, metric, kind in columns:
        if kind != "rate (%)" or metric not in WANTED_METRICS:
            continue
        val = _to_float(grid[period_row_idx][c])
        if val is None:
            continue
        by_band.setdefault(band, {})[WANTED_METRICS[metric]] = round(val, 2)

    # Only keep bands where we actually got both rates -- partial rows
    # are more likely a layout misread than genuinely missing data given
    # this is a fully populated ONS SA series.
    by_band = {b: v for b, v in by_band.items() if "unemployment_rate" in v and "inactivity_rate" in v}
    if not by_band:
        return None

    print(f"  [a05] extracted {len(by_band)} age band(s) for period '{period_label}': "
          f"{list(by_band.keys())}")
    return {"period": period_label, "age_bands": by_band}


def fetch_and_parse() -> dict | None:
    try:
        r = requests.get(DATASET_PAGE, timeout=60, headers={"User-Agent": "economic-atlas/0.1"})
        print(f"  [a05] page status={r.status_code}")
        r.raise_for_status()
    except Exception as exc:
        print(f"  [a05] page request failed: {exc}")
        return None

    xls_url = find_current_xls_link(r.text)
    if not xls_url:
        print("  [a05] couldn't find a current-edition .xls link on the dataset page")
        return None
    print(f"  [a05] current edition: {xls_url}")

    try:
        xls_r = requests.get(xls_url, timeout=60, headers={"User-Agent": "economic-atlas/0.1"})
        print(f"  [a05] xls status={xls_r.status_code}")
        xls_r.raise_for_status()
    except Exception as exc:
        print(f"  [a05] xls download failed: {exc}")
        return None

    sheet_order = []
    get_grid = None
    try:
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(xls_r.content), data_only=True)
        print(f"  [a05] opened via openpyxl, sheets: {wb.sheetnames}")
        sheet_order = list(wb.sheetnames)
        get_grid = lambda name: _grid_from_openpyxl(wb[name])
    except Exception as exc:
        print(f"  [a05] openpyxl couldn't open it ({exc}) — trying xlrd "
              f"(likely genuine legacy .xls format)")
        try:
            import xlrd
            book = xlrd.open_workbook(file_contents=xls_r.content)
            print(f"  [a05] opened via xlrd, sheets: {book.sheet_names()}")
            sheet_order = list(book.sheet_names())
            get_grid = lambda name: _grid_from_xlrd(book.sheet_by_name(name))
        except ImportError:
            print("  [a05] xlrd not installed either")
            return None
        except Exception as exc2:
            print(f"  [a05] xlrd also failed to open it: {exc2}")
            return None

    if "People" not in sheet_order:
        print(f"  [a05] no 'People' sheet found (have: {sheet_order}) -- layout has changed")
        return None

    grid = get_grid("People")
    print(f"  [a05] 'People' sheet: {len(grid)} rows")
    result = _extract_from_people_sheet(grid)
    if result is not None:
        return result

    print("  [a05] extraction failed against the confirmed layout -- dumping "
          "'People' sheet for diagnosis:")
    _dump(grid, "sheet 'People'")
    return None


def main() -> int:
    result = fetch_and_parse()
    if not result:
        print("FAIL  a05  no usable data yet — leaving any previously-fetched file in place. "
              "This is expected on a first run against a real, unconfirmed file layout; "
              "check the sheet names and any header hits printed above.")
        return 0

    out = {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "ONS A05 SA: Employment, unemployment and economic inactivity by age group (seasonally adjusted)",
        **result,
    }
    with open("data-uk-age-breakdown.json", "w") as f:
        json.dump(out, f)
    print(f"  ok  a05  wrote age breakdown for {len(result['age_bands'])} age band(s), period {result['period']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
