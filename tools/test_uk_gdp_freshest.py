#!/usr/bin/env python3
"""UK GDP: read the freshest ONS dataset (v1.9.14).

ONS keeps each GDP series in several datasets: PN2 (first quarterly estimate) is refreshed only at each first
estimate and by design carries no revisions; QNA (quarterly national accounts) is refreshed six weeks later with
the revised figures. fetch_data.py read PN2 alone, so for six weeks of every quarter the site showed the first
estimate: Q2 2026 growth 0.4% against the ONS's revised 0.5% (30 September 2026).

  1. fetch_ons_freshest picks the dataset that goes furthest in time, and on a tie the one listed first (the
     revised one); a dataset that fails is skipped; all failing raises; differing frequencies keep the first;
  2. YBHA, ABMI and IHYQ list the QNA dataset first and PN2 second, and ONLY those three use the new selection;
  3. end to end, the real build_uk() run offline with mocked ONS responses writes the revised QNA value, and
     takes PN2 instead when it has the newer quarter.

No network: every ONS request is mocked. Run from the repo root:  python3 tools/test_uk_gdp_freshest.py
"""
import contextlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import requests  # noqa: E402
import fetch_data  # noqa: E402

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


class Resp:
    def __init__(self, payload=None, status=200):
        self._p, self.status_code = payload, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} Client Error")

    def json(self):
        return self._p


def q_payload(points, nxt="12 November 2026"):
    """ONS-style quarterly payload from [["2026-Q2", 0.5], ...]."""
    return {"quarters": [{"date": f"{p[:4]} {p[5:]}", "value": str(v)} for p, v in points],
            "description": {"nextRelease": nxt}}


def m_payload(points):
    return {"months": [{"date": f"{p[:4]} {['JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC'][int(p[5:])-1]}", "value": str(v)} for p, v in points]}


def run_freshest(payloads, uris):
    """payloads: {'qna': payload | None | 'error', 'pn2': ...}. Returns fetch_ons_freshest(uris)."""
    def fake_get(url, **kw):
        for tag, p in payloads.items():
            if f"/{tag}" in url:
                if p == "error":
                    return Resp(status=404)
                return Resp(p)
        return Resp(status=404)
    with mock.patch.object(fetch_data.requests, "get", side_effect=fake_get), contextlib.redirect_stdout(io.StringIO()):
        return fetch_data.fetch_ons_freshest(uris)


QNA, PN2 = "/x/ihyq/qna", "/x/ihyq/pn2"
BASE = [["2025-Q4", 0.1], ["2026-Q1", 0.6]]


@case
def tie_goes_to_the_revised_dataset():
    res = run_freshest({"qna": q_payload(BASE + [["2026-Q2", 0.5]]), "pn2": q_payload(BASE + [["2026-Q2", 0.4]])}, [QNA, PN2])
    check(res and res[1][-1] == ["2026-Q2", 0.5], f"tie must take QNA's revised 0.5, got {res and res[1][-1]}")
    res = run_freshest({"qna": q_payload(BASE + [["2026-Q2", 0.5]]), "pn2": q_payload(BASE + [["2026-Q2", 0.4]])}, [PN2, QNA])
    check(res and res[1][-1] == ["2026-Q2", 0.4], "a tie goes to whichever is listed FIRST (so the list order is the policy)")


@case
def newer_period_wins_even_if_unrevised():
    res = run_freshest({"qna": q_payload(BASE + [["2026-Q2", 0.5]]), "pn2": q_payload(BASE + [["2026-Q2", 0.5], ["2026-Q3", 0.3]])}, [QNA, PN2])
    check(res and res[1][-1] == ["2026-Q3", 0.3], f"PN2's newer quarter must win, got {res and res[1][-1]}")
    res = run_freshest({"qna": q_payload(BASE + [["2026-Q2", 0.5]]), "pn2": q_payload(BASE)}, [QNA, PN2])
    check(res and res[1][-1][0] == "2026-Q2", "QNA wins when PN2 has not reached the quarter yet")


@case
def failing_dataset_is_skipped():
    res = run_freshest({"qna": "error", "pn2": q_payload(BASE + [["2026-Q2", 0.4]])}, [QNA, PN2])
    check(res and res[1][-1] == ["2026-Q2", 0.4], "with QNA unavailable PN2 must still be used (the old behaviour)")
    res = run_freshest({"qna": q_payload(BASE + [["2026-Q2", 0.5]]), "pn2": "error"}, [QNA, PN2])
    check(res and res[1][-1] == ["2026-Q2", 0.5], "with PN2 unavailable QNA must be used")
    try:
        run_freshest({"qna": "error", "pn2": "error"}, [QNA, PN2])
        check(False, "all datasets failing must raise, not return None silently")
    except requests.HTTPError:
        pass


@case
def keeps_metadata_of_the_winner():
    res = run_freshest({"qna": q_payload(BASE + [["2026-Q2", 0.5]], nxt="31 December 2026"),
                        "pn2": q_payload(BASE + [["2026-Q2", 0.4]], nxt="30 September 2026")}, [QNA, PN2])
    check(res and res[2] == "31 December 2026", f"next-release must come from the chosen dataset, got {res and res[2]}")


@case
def different_frequencies_keep_the_first():
    # "2026-Q1" sorts above "2026-12" as a string, so without the frequency check a quarterly dataset listed second
    # would displace a monthly one listed first. Both orders are tried.
    res = run_freshest({"qna": q_payload(BASE), "pn2": m_payload([["2026-01", 1.0], ["2026-02", 2.0]])}, [PN2, QNA])
    check(res and res[0] == "months", f"a dataset on another frequency must not displace the first (monthly first): {res and res[0]}")
    res = run_freshest({"qna": q_payload(BASE), "pn2": m_payload([["2026-01", 1.0], ["2026-02", 2.0]])}, [QNA, PN2])
    check(res and res[0] == "quarters", f"a dataset on another frequency must not displace the first (quarterly first): {res and res[0]}")


@case
def single_uri_behaves_like_fetch_ons():
    res = run_freshest({"pn2": q_payload(BASE)}, [PN2])
    check(res and res[1] == BASE, "a single dataset passes straight through")


@case
def structure():
    us = fetch_data.UK_SERIES
    check(fetch_data.PICK_FRESHEST == {"gdp_level", "gdp_real", "gdp_growth"}, f"PICK_FRESHEST is {fetch_data.PICK_FRESHEST}")
    for key, cdid in (("gdp_level", "ybha"), ("gdp_real", "abmi"), ("gdp_growth", "ihyq")):
        uris = us[key][0]
        check(uris == [f"/economy/grossdomesticproductgdp/timeseries/{cdid}/qna",
                       f"/economy/grossdomesticproductgdp/timeseries/{cdid}/pn2"], f"{key}: URIs are {uris}")
    # no other series may have been moved onto the new selection by accident
    src = (ROOT / "fetch_data.py").read_text(encoding="utf-8")
    check("fetch_ons_freshest(uris) if key in PICK_FRESHEST else fetch_ons(uris)" in src, "build_uk does not gate the selection on PICK_FRESHEST")
    check(len(re.findall(r"fetch_ons_freshest\(", src)) == 2, "fetch_ons_freshest should be defined once and called once")
    others = [k for k, v in us.items() if k not in fetch_data.PICK_FRESHEST and len(v[0]) > 1]
    check("current_account" in others, f"the multi-source annual current_account must keep first-that-answers: {others}")


def build_uk_offline(qna_points, qna_next, pn2_points, pn2_next):
    """Run the real build_uk() offline with mocked ONS GDP-growth datasets; return the gdp_growth series written."""
    def fake_get(url, **kw):
        if "ihyq/qna" in url:
            return Resp(q_payload([tuple(p) for p in qna_points], qna_next))
        if "ihyq/pn2" in url:
            return Resp(q_payload([tuple(p) for p in pn2_points], pn2_next))
        raise requests.ConnectionError("offline")

    tmp = Path(tempfile.mkdtemp(prefix="uk_"))
    shutil.copy(ROOT / "data-uk.json", tmp / "data-uk.json")
    for f in ROOT.glob("*.json"):
        if f.name.startswith(("data-metric", "data-fx", "data-bond")):
            shutil.copy(f, tmp / f.name)
    cwd = os.getcwd()
    os.chdir(tmp)
    try:
        with mock.patch.dict(os.environ, {"FRED_API_KEY": ""}), \
                mock.patch.object(fetch_data.requests, "get", side_effect=fake_get), \
                mock.patch.object(time, "sleep", return_value=None), \
                contextlib.redirect_stdout(io.StringIO()):
            fetch_data.build_uk()
        return json.loads((tmp / "data-uk.json").read_text(encoding="utf-8"))["series"]["gdp_growth"]
    finally:
        os.chdir(cwd)
        shutil.rmtree(tmp, ignore_errors=True)


@case
def end_to_end_build_uk_writes_the_revised_value():
    pts = json.loads((ROOT / "data-uk.json").read_text(encoding="utf-8"))["series"]["gdp_growth"]["points"]
    assert pts[-1][0] >= "2026-Q2", f"data moved on: {pts[-2:]}"
    last_p = pts[-1][0]
    first_est = [list(p) for p in pts]
    revised = [list(p) for p in pts]
    first_est[-1][1], revised[-1][1] = 0.4, 0.5
    g = build_uk_offline(revised, "31 December 2026", first_est, "30 September 2026")
    check(g["points"][-1] == [last_p, 0.5], f"build_uk must write QNA's revised 0.5 for {last_p}, got {g['points'][-1]}")
    check(g.get("next") == "31 December 2026", f"next release must come from QNA, got {g.get('next')}")


@case
def end_to_end_build_uk_takes_a_newer_first_estimate():
    pts = json.loads((ROOT / "data-uk.json").read_text(encoding="utf-8"))["series"]["gdp_growth"]["points"]
    nxt_q = {"Q1": "Q2", "Q2": "Q3", "Q3": "Q4"}.get(pts[-1][0][5:], None)
    assert nxt_q, f"unsupported last period {pts[-1][0]}"
    new_p = f"{pts[-1][0][:4]}-{nxt_q}"
    qna = [list(p) for p in pts]
    pn2 = [list(p) for p in pts] + [[new_p, 0.3]]            # the next first estimate has arrived; QNA has not caught up
    g = build_uk_offline(qna, "31 December 2026", pn2, "10 February 2027")
    check(g["points"][-1] == [new_p, 0.3], f"build_uk must take PN2's newer quarter {new_p}, got {g['points'][-1]}")
    check(g.get("next") == "10 February 2027", f"next release must come from PN2, got {g.get('next')}")


print("test_uk_gdp_freshest:", "FAILED" if fails else "ok", f"({len(fails)} failures)")
sys.exit(1 if fails else 0)
