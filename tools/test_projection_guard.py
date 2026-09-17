"""Behavioural tests for projection_guard.py.   python3 tools/test_projection_guard.py"""
import os, sys
from datetime import datetime, timezone
sys.path.insert(0, os.environ.get("ATLAS_REPO") or os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import projection_guard as pg

T = datetime(2026, 9, 16, tzinfo=timezone.utc)
cases = []
def check(name, got, want):
    cases.append((name, got == want, got, want))

check("Jan vintage cannot hold last year's outturn", pg.last_actual_year("2026-01-22 14:49:43-06", T), 2024)
check("April vintage holds last year", pg.last_actual_year("2026-04-15 09:00:00-05", T), 2025)
check("March vintage is still pre-April", pg.last_actual_year("2026-03-31 23:59:00-05", T), 2024)
check("October vintage holds last year only", pg.last_actual_year("2025-10-14 10:00:00-05", T), 2024)
check("unreadable stamp fails closed", pg.last_actual_year(None, T), 2024)
check("garbage stamp fails closed", pg.last_actual_year("n/a", T), 2024)
check("outlook id recognised (PPPT)", pg.is_outlook_series("SGPPCPIPCPPPT"), True)
check("outlook id recognised (GGXWDGGDP)", pg.is_outlook_series("CHLGGXWDGGDP"), True)
check("outlook id recognised (Morocco GDPPT)", pg.is_outlook_series("MARGGDGDPGDPPT"), True)
check("outlook id recognised (current account BP6PT)", pg.is_outlook_series("SGPBCAGDPBP6PT"), True)
check("historical debt id not touched", pg.is_outlook_series("DEBTTLSGA188A"), False)
check("monthly FRED id not touched", pg.is_outlook_series("CPIAUCSL"), False)

pts = [["2023", 4.8], ["2024", 2.4], ["2025", 1.19]]
pg.CUTOFFS.clear()
out = pg.trim(pts, "SGPPCPIPCPPPT", "k", fetch=lambda s, k: "2026-01-22 14:49:43-06")
check("trim drops the 2025 projection", out, [["2023", 4.8], ["2024", 2.4]])
check("cutoff recorded", pg.CUTOFFS.get("SGPPCPIPCPPPT"), 2024)
check("non-outlook series passes through", pg.trim(pts, "DEBTTLSGA188A", "k", fetch=lambda s, k: 1/0), pts)

prev = {
    "cpi": {"freq": "years", "label": "CPI (IMF Asia-Pacific REO) (SGPPCPIPCPPPT)", "points": [["2024", 2.4], ["2025", 1.19]]},
    "debt_gdp": {"freq": "years", "label": "Total government debt (IMF MENA REO)", "points": [["2024", 69.0], ["2025", 68.0]]},
    "fdi": {"freq": "years", "label": "FDI (World Bank)", "points": [["2024", 1.0], ["2025", 1.1]]},
    "cpi_m": {"freq": "months", "label": "CPI (SGPPCPIPCPPPT)", "points": [["2025-12", 1.2]]},
}
pg.trim_previous(prev)
check("stored series trimmed by id", prev["cpi"]["points"], [["2024", 2.4]])
check("stored REO series without id takes strictest cutoff", prev["debt_gdp"]["points"], [["2024", 69.0]])
check("unrelated annual series untouched", prev["fdi"]["points"], [["2024", 1.0], ["2025", 1.1]])
check("non-annual series untouched", prev["cpi_m"]["points"], [["2025-12", 1.2]])

# The guard must now accept the shorter, correct series instead of keeping the projection.
import series_guard
new = {"cpi": {"freq": "years", "label": "CPI (IMF Asia-Pacific REO) (SGPPCPIPCPPPT)", "points": [["2023", 4.8], ["2024", 2.4]]}}
stored = {"cpi": {"freq": "years", "label": "CPI (IMF Asia-Pacific REO) (SGPPCPIPCPPPT)", "points": [["2023", 4.8], ["2024", 2.4], ["2025", 1.19]]}}
v_without = series_guard.apply_guard(dict(new), {k: dict(s) for k, s in stored.items()}, log=None)
check("without trim_previous the guard keeps the projection", v_without["cpi"][0], "kept")
pg.trim_previous(stored)
out_series = dict(new)
v_with = series_guard.apply_guard(out_series, stored, log=None)
check("with trim_previous the guard accepts the correction", (v_with["cpi"][0], out_series["cpi"]["points"][-1][0]), ("new", "2024"))

ok = sum(1 for c in cases if c[1])
for name, passed, got, want in cases:
    if not passed:
        print(f"FAIL {name}: got {got!r}, want {want!r}")
print(f"{ok}/{len(cases)} projection guard branches pass")
sys.exit(0 if ok == len(cases) else 1)
