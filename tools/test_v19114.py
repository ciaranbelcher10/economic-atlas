#!/usr/bin/env python3
"""v1.9.114 checks: the population fetcher, run offline against a simulated World Bank response
(no network), plus its place in the hourly workflow."""
import datetime as dt, json, os, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import fetch_population as fp  # noqa: E402

fails = []; checks = 0
def check(ok, msg):
    global checks; checks += 1
    if not ok: fails.append(msg)

TODAY = dt.date(2026, 11, 9)
codes = fp.wb_codes()
def payload(skip=(), override=None, last=2025):
    rows = []
    for code, name in codes.items():
        if code in skip: continue
        base = 1_000_000 + 37 * len(name) * 100_000
        for y in range(1960, last + 1):
            v = int(base * (1.01 ** (y - 1960)))
            if override and (code, y) in override: v = override[(code, y)]
            rows.append({"country": {"id": code}, "countryiso3code": "", "date": str(y), "value": v})
        rows.append({"country": {"id": code}, "date": str(last + 1), "value": None})  # not yet published
    return [{"page": 1}, rows]

# mapping
check(len(codes) == 61, f"61 economies requested (got {len(codes)})")
check(codes.get("GB") == "UK" and codes.get("XC") == "Eurozone", "UK and Eurozone mapped to World Bank codes")
check("Taiwan" not in codes.values(), "Taiwan not requested")
check(all(len(c) == 2 and c.isupper() for c in codes), "all codes are two-letter World Bank ids")

doc = fp.build(payload(), {}, TODAY)
c = doc["countries"]
# v1.9.125: Cyprus population comes only from Eurostat (same area as its GDP); with no Eurostat reply
# and no earlier Eurostat copy it is listed as missing, never filled with the World Bank figure.
check(len(c) == 60 and "Cyprus" not in c, "60 economies written; Cyprus not from the World Bank")
check(set(doc["missing"]) == {"Taiwan", "Cyprus"}, "Taiwan and Cyprus listed as missing")
uk = c["UK"]["points"]
check(uk[0][0] == "1960" and uk[-1][0] == "2025", "UK runs 1960 to 2025, unpublished year skipped")
check(all(isinstance(v, int) and v > 0 for _, v in uk), "whole positive numbers of people")
check(uk == sorted(uk), "points sorted by year")
check(doc["unit"] == "people" and doc["freq"] == "years" and "SP.POP.TOTL" in doc["source"], "metadata")

# a break is refused, and the previous good series is kept
broken = fp.build(payload(override={("FR", 2001): 99_000_000_000}), doc, TODAY)
check(broken["countries"]["France"]["points"] == c["France"]["points"], "series with a break: previous points kept")
check("France" in broken["kept_previous"], "kept-previous economy is named")
fresh_only = fp.build(payload(override={("FR", 2001): 99_000_000_000}), {}, TODAY)
check("France" not in fresh_only["countries"] and "France" in fresh_only["missing"], "break with no history: listed missing")

# an economy that vanishes keeps its previous points; a shorter series does not replace a longer one
gone = fp.build(payload(skip=("JP",)), doc, TODAY)
check(gone["countries"]["Japan"]["points"] == c["Japan"]["points"] and "Japan" in gone["kept_previous"], "vanished economy keeps previous")
short = fp.build(payload(last=2023), doc, TODAY)
check(short["countries"]["UK"]["points"][-1][0] == "2025", "older response never replaces newer data")

# refusals: too few economies, too old
try:
    fp.build(payload(skip=tuple(list(codes)[:10])), {}, TODAY); check(False, "too few economies must refuse")
except ValueError: check(True, "")
try:
    fp.build(payload(last=2019), {}, TODAY); check(False, "stale data must refuse")
except ValueError: check(True, "")
try:
    fp.build({"message": "error"}, {}, TODAY); check(False, "bad shape must refuse")
except ValueError: check(True, "")

# main(): daily skip, failure keeps the file
class Boom:
    def __call__(self, *a, **k): raise AssertionError("network must not be called")
d = tempfile.mkdtemp(); cwd = os.getcwd(); os.chdir(d)
try:
    recent = dict(doc, updated=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    json.dump(recent, open(fp.OUT, "w")); before = open(fp.OUT).read()
    real_get = fp.requests.get; fp.requests.get = Boom()
    os.environ.pop("FORCE_POPULATION", None)
    check(fp.main() == 0 and open(fp.OUT).read() == before, "refreshed recently: skipped without a request")
    os.environ["FORCE_POPULATION"] = "1"
    check(fp.main() == 1 and open(fp.OUT).read() == before, "request fails: exit 1, previous file untouched")
finally:
    fp.requests.get = real_get; os.environ.pop("FORCE_POPULATION", None); os.chdir(cwd)

# workflow
wf = open(os.path.join(ROOT, ".github/workflows/update-data.yml"), encoding="utf-8").read()
i_step = wf.find("      - name: Run fetch_population.py\n        continue-on-error: true\n")
i_commit = wf.find("      - name: Commit updated data")
check(0 < i_step < i_commit, "population step runs before the data commit, and cannot fail the job")
check("python fetch_population.py 2>&1 | tee -a pipeline_log.txt" in wf, "population step logs to the pipeline log")
check("          git add data-population.json 2>/dev/null || true\n" in wf[i_commit:wf.find("      - name: Regenerate")], "data-population.json committed by the bot")

print(f"test_v19114: {checks} checks, {len(fails)} failed")
for f in fails: print("  FAIL", f)
sys.exit(1 if fails else 0)
