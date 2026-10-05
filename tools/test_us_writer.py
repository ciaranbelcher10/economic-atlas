"""v1.6.47 gate: fetch_us.py is the only writer of data-us.json and serves
every key the file carried when two scripts wrote it.

Runs fetch_us.main() offline in a temp dir: each FRED/OECD/World Bank call is
answered with the series already served in data-us.json, so a key the script
no longer fetches shows up as 'carried-over' (it would then freeze live).
    python3 tools/test_us_writer.py   -> "N ok, 0 failed"
"""
import io, json, os, re, shutil, sys, tempfile, contextlib
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
ok = bad = 0
def check(name, cond, detail=""):
    global ok, bad
    if cond: ok += 1
    else: bad += 1; print("FAIL", name, detail)

src = open(os.path.join(ROOT, "fetch_data.py"), encoding="utf-8").read()
check("fetch_data.py never writes data-us.json", "data-us.json" not in re.sub(r"#.*", "", src).replace('"""', ""), "")
check("fetch_data.py has no build_us", "def build_us" not in src)
check("fetch_data.py writes data-uk.json", 'finalise(out, previous, "data-uk.json"' in src)
check("fetch_data.py no longer writes data.json", '"data.json"' not in src)

served = json.load(open(os.path.join(ROOT, "data-us.json"), encoding="utf-8"))["series"]
import fetch_us
by_sid = {(sid, tf): k for k, (sid, f, l, u, tf) in fetch_us.FRED_SERIES.items()}
fetch_us.fetch_fred = lambda sid, freq, key: ("SID", sid)
_real_tf = fetch_us.transform
def fake_transform(points, kind):
    if isinstance(points, tuple) and points[0] == "SID":
        k = by_sid[(points[1], kind)]
        return [list(p) for p in served[k]["points"]]
    return _real_tf(points, kind)
fetch_us.transform = fake_transform
fetch_us.fetch_oecd_bci = lambda: [list(p) for p in served["business_confidence"]["points"]]
WB = {"BX.KLT.DINV.WD.GD.ZS": "fdi", "BN.CAB.XOKA.GD.ZS": "current_account"}
fetch_us.fetch_worldbank = lambda code: [list(p) for p in served[WB[code]]["points"]]
fetch_us.fetch_fx_monthly = lambda sid, key: []

tmp = tempfile.mkdtemp(); cwd = os.getcwd()
shutil.copy(os.path.join(ROOT, "data-us.json"), tmp)
os.environ["FRED_API_KEY"] = "offline-test"
buf = io.StringIO()
try:
    os.chdir(tmp)
    with contextlib.redirect_stdout(buf):
        rc = fetch_us.main()
    out = json.load(open("data-us.json"))["series"]
finally:
    os.chdir(cwd); shutil.rmtree(tmp)
log = buf.getvalue()
check("fetch_us.main() returns 0", rc in (0, None), rc)
missing = sorted(set(served) - set(out))
check("no key lost", not missing, missing)
carried = [ln for ln in log.splitlines() if "carried" in ln.lower() and "fx_" not in ln]
check("no key only carried over (all fetched fresh)", not carried, carried[:5])
for k in sorted(served):
    if k in out:
        check(f"{k} points unchanged", out[k]["points"] == served[k]["points"], k)
check("gdp_nominal = gdp_level points", out.get("gdp_nominal", {}).get("points") == out["gdp_level"]["points"])
check("gdp_nominal freq quarters", out.get("gdp_nominal", {}).get("freq") == "quarters")
print(f"{ok} ok, {bad} failed")
sys.exit(1 if bad else 0)
