#!/usr/bin/env python3
"""Eurostat-first series (v1.9.12): Croatia, Bulgaria, Lithuania, Estonia, Latvia, Cyprus, Malta.

FRED answers HTTP 400 for thirteen of the series these fetchers asked it for (the OECD-derived copies do not
exist for these countries), and Eurostat then supplied every one of them: all 21 stored series already carry
Eurostat labels. So the doomed FRED request is removed and Eurostat is asked first. The data does not change.

What this runs: each fetcher's REAL main(), in a temporary directory with a copy of its data file, with FRED,
Eurostat and every other network call mocked. It records which FRED series ids were requested and which
series were fetched from Eurostat, and checks:

  1. FRED is never asked for the thirteen removed ids, but still is asked for the other series;
  2. Eurostat is asked for exactly the removed series, and what it returns is what the file holds afterwards;
  3. when Eurostat answers nothing, the series is reported as Missing (so a real outage stays visible) and the
     previous series is kept, not deleted;
  4. FRED_SERIES no longer lists the removed keys; EUROSTAT_FALLBACK still does;
  5. tools/citation_ids.py treats these as Eurostat-first (the dataset is the id): with the pages' real citations
     all thirteen match, and a citation that does not name the Eurostat dataset flips exactly that metric to UNCITED.

Run from the repo root:  python3 tools/test_eurostat_first.py
"""
import contextlib
import copy
import importlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import requests  # noqa: E402

fails = []


def check(cond, msg):
    if not cond:
        fails.append(msg)
        print("FAIL", msg)


def case(fn):
    try:
        fn()
    except Exception as exc:  # noqa: BLE001
        fails.append(f"{fn.__name__} raised {type(exc).__name__}: {exc}")
        print("FAIL", f"{fn.__name__} raised {type(exc).__name__}: {exc}")
    return fn


# country -> (module, {series key: the FRED id that used to be requested and answered HTTP 400})
LAB3 = ("bond_yield_10y", "participation_rate", "employment_rate")
SPEC = {
    "hr": ("fetch_hr", {"bond_yield_10y": "IRLTLT01HRM156N", "participation_rate": "LRAC64TTHRQ156S", "employment_rate": "LREM64TTHRQ156S"}),
    "bg": ("fetch_bg", {"bond_yield_10y": "IRLTLT01BGM156N", "participation_rate": "LRAC64TTBGQ156S", "employment_rate": "LREM64TTBGQ156S"}),
    "lt": ("fetch_lt", {"bond_yield_10y": "IRLTLT01LTM156N", "participation_rate": "LRAC64TTLTQ156S", "employment_rate": "LREM64TTLTQ156S"}),
    "ee": ("fetch_ee", {"bond_yield_10y": "IRLTLT01EEM156N"}),
    "lv": ("fetch_lv", {"bond_yield_10y": "IRLTLT01LVM156N"}),
    "cy": ("fetch_cy", {"bond_yield_10y": "IRLTLT01CYM156N"}),
    "mt": ("fetch_mt", {"bond_yield_10y": "IRLTLT01MTM156N"}),
}
COUNTRY = {"hr": "Croatia", "bg": "Bulgaria", "lt": "Lithuania", "ee": "Estonia", "lv": "Latvia", "cy": "Cyprus", "mt": "Malta"}
ALL_GONE = {sid for _, ids in SPEC.values() for sid in ids.values()}
check(len(ALL_GONE) == 13, f"test setup: expected 13 removed ids, got {len(ALL_GONE)}")
# series every one of these countries has that must NOT be dragged along by the change
STILL_FRED = "cpi"


def run_main(code, eurostat_answers):
    """Run fetch_xx.main() offline. Returns (log, fred_asked, es_asked, data_after, data_before)."""
    modname, _ = SPEC[code]
    mod = importlib.import_module(modname)
    tmp = Path(tempfile.mkdtemp(prefix=f"ef_{code}_"))
    shutil.copy(ROOT / f"data-{code}.json", tmp / f"data-{code}.json")
    before = json.loads((tmp / f"data-{code}.json").read_text())
    fred_asked, es_asked = [], []

    def fake_fred(sid, freq, key):
        fred_asked.append(sid)
        if sid in ALL_GONE:
            raise requests.HTTPError("400 Client Error: Bad Request for url: .../series/observations?series_id=" + sid)
        raise requests.ConnectionError("offline")     # every other FRED series fails quietly; the guard keeps the old one

    def fake_es(name):
        es_asked.append(name)
        if not eurostat_answers:
            return None
        s = before["series"][name]
        return s["points"], s["freq"], s["label"]       # exactly what is stored, so the guard sees an equal series

    buf = io.StringIO()
    cwd = os.getcwd()
    os.chdir(tmp)
    try:
        with mock.patch.dict(os.environ, {"FRED_API_KEY": "dummy"}), \
                mock.patch.object(mod, "fetch_fred", fake_fred), \
                mock.patch.object(mod, "fetch_eurostat_fallback", fake_es), \
                mock.patch.object(mod.eurostat_gdp, "fetch_levels", return_value={}), \
                mock.patch.object(mod.eurostat_unemp, "fetch", return_value={}), \
                mock.patch.object(requests, "get", side_effect=requests.ConnectionError("offline")), \
                mock.patch.object(time, "sleep", return_value=None), \
                contextlib.redirect_stdout(buf):
            mod.main()
    finally:
        os.chdir(cwd)
    after = json.loads((tmp / f"data-{code}.json").read_text())
    shutil.rmtree(tmp, ignore_errors=True)
    return buf.getvalue(), fred_asked, es_asked, after, before


@case
def structure():
    for code, (modname, ids) in SPEC.items():
        mod = importlib.import_module(modname)
        for key in ids:
            check(key not in mod.FRED_SERIES, f"{modname}: FRED_SERIES still lists {key}")
            check(key in mod.EUROSTAT_FALLBACK, f"{modname}: EUROSTAT_FALLBACK lost {key}")
        check(STILL_FRED in mod.FRED_SERIES, f"{modname}: the change must not touch the other FRED series ({STILL_FRED})")


@case
def eurostat_first_and_no_doomed_fred_calls():
    for code, (modname, ids) in SPEC.items():
        log, fred, es, after, before = run_main(code, eurostat_answers=True)
        gone = [s for s in fred if s in ALL_GONE]
        check(not gone, f"{modname}: FRED was still asked for {gone}")
        check(any(s not in ALL_GONE for s in fred), f"{modname}: FRED loop no longer runs at all ({fred})")
        check(set(ids) <= set(es), f"{modname}: Eurostat not asked for {sorted(set(ids) - set(es))} (asked {es})")
        for key in ids:
            check(after["series"][key]["points"] == before["series"][key]["points"],
                  f"{modname}: {key} differs after the run")
            check(after["series"][key]["label"] == before["series"][key]["label"] and "Eurostat" in after["series"][key]["label"],
                  f"{modname}: {key} label wrong: {after['series'][key]['label']}")
        for key in ids:
            check(f"ok  {key}" in log and "Eurostat fallback" in log, f"{modname}: no ok line for {key}")
        check("400" not in log, f"{modname}: the log still shows an HTTP 400 for these series")


@case
def eurostat_outage_stays_visible_and_keeps_data():
    for code, (modname, ids) in SPEC.items():
        log, fred, es, after, before = run_main(code, eurostat_answers=False)
        missing = [ln for ln in log.splitlines() if ln.startswith("Missing:")]
        check(missing, f"{modname}: no 'Missing:' line when Eurostat answered nothing")
        for key in ids:
            check(missing and key in missing[0], f"{modname}: {key} not named as Missing ({missing})")
            check(after["series"][key]["points"] == before["series"][key]["points"],
                  f"{modname}: {key} was deleted or changed during an outage (the guard must keep it)")


@case
def citation_gate_checks_eurostat_first_series():
    def run(sources):
        mini = Path(tempfile.mkdtemp(prefix="ci_"))
        for f in ["compare.html"] + [p.name for p in ROOT.glob("fetch_*.py")]:
            shutil.copy(ROOT / f, mini / f)
        (mini / "data-metric-sources.json").write_text(json.dumps(sources, ensure_ascii=False, indent=2), encoding="utf-8")
        r = subprocess.run([sys.executable, str(ROOT / "tools" / "citation_ids.py")], capture_output=True, text=True, timeout=150,
                           env=dict(os.environ, ATLAS_REPO=str(mini), PYTHONDONTWRITEBYTECODE="1"))
        shutil.rmtree(mini, ignore_errors=True)
        counts = {k: int(v) for k, v in re.findall(r"^\s+(MATCH|MISMATCH|CROSS-TABLE|UNCITED|NO-ID)\s+(\d+)", r.stdout, re.M)}
        return r, counts

    base = json.loads((ROOT / "data-metric-sources.json").read_text(encoding="utf-8"))
    r0, c0 = run(base)
    check(r0.returncode == 0 and c0.get("MISMATCH") == 0 and c0.get("UNCITED") == 0 and c0.get("CROSS-TABLE") == 0,
          f"the real citations must all be clean: {c0} {r0.stderr[-200:]}")
    for code, (modname, ids) in SPEC.items():
        for key, sid in ids.items():
            tampered = copy.deepcopy(base)
            tampered[COUNTRY[code]][key]["source"] = f"FRED series {sid} - the old source, not the Eurostat dataset."
            r1, c1 = run(tampered)
            check(c1.get("UNCITED") == 1 and c1.get("MATCH") == c0.get("MATCH", 0) - 1,
                  f"{COUNTRY[code]} {key}: citing {sid} instead of the Eurostat dataset must flip exactly one metric "
                  f"from MATCH to UNCITED; before {c0}, after {c1}")


print("test_eurostat_first:", "FAILED" if fails else "ok", f"({len(fails)} failures)")
sys.exit(1 if fails else 0)
