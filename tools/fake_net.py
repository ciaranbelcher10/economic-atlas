"""Shared offline harness for the v1.7.56 fetcher tests (no network).

FakeNet maps URL substrings to replies in the shapes the 13 Oct 2026
probes recorded; anything unmatched raises, so a test fails loudly if a
fetcher calls a source the test did not expect. Imported only by tests.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile


class Reply:
    def __init__(self, body, status=200):
        self.status_code = status
        self._body = body
        self.text = body if isinstance(body, str) else json.dumps(body)

    def json(self):
        return self._body if not isinstance(self._body, str) else json.loads(self._body)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeNet:
    def __init__(self, routes):
        self.routes = routes          # [(substring, body or callable(url))]
        self.calls = []

    def get(self, url, *a, **kw):
        self.calls.append(url)
        for key, body in self.routes:
            if key in url:
                return Reply(body(url) if callable(body) else body)
        raise RuntimeError(f"FakeNet: no route for {url}")


def csv_rows(header, rows):
    return ",".join(header) + "\n" + "\n".join(",".join(str(c) for c in r) for r in rows) + "\n"


def months(start_y, start_m, end_y, end_m):
    y, m, out = start_y, start_m, []
    while (y, m) <= (end_y, end_m):
        out.append(f"{y}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def imf_csv_rows(per_value, **dims):
    """IMF SDMX CSV with TIME_PERIOD as YYYY-MNN."""
    head = ["TIME_PERIOD", "OBS_VALUE"] + list(dims)
    return csv_rows(head, [[p.replace("-", "-M"), v] + list(dims.values()) for p, v in per_value])


def bis_rows(per_value):
    return csv_rows(["TIME_PERIOD", "OBS_VALUE"], per_value)


def wb(points):
    return [{"page": 1}, [{"date": d, "value": v} for d, v in points]]


def run_main(module, setup=None):
    """Run module.main() in an empty temp directory; return (rc, data)."""
    here = os.getcwd()
    with tempfile.TemporaryDirectory() as d:
        os.chdir(d)
        try:
            if setup:
                setup(d)
            rc = module.main()
            data = json.load(open(module.OUT_FILE)) if os.path.exists(module.OUT_FILE) else None
            keep = os.environ.get("FAKE_NET_KEEP")     # a directory to copy the written file into
            if keep and data is not None:
                with open(os.path.join(keep, module.OUT_FILE), "w") as fh:
                    json.dump(data, fh)
        finally:
            os.chdir(here)
    return rc, data


class Checker:
    def __init__(self):
        self.fails = 0

    def __call__(self, cond, msg):
        print(("  ok    " if cond else "  FAIL  ") + msg)
        self.fails += not cond

    def done(self):
        print(f"\n{self.fails} failures")
        sys.exit(1 if self.fails else 0)
