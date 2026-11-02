"""v1.9.61: Brazil Copom decision dates from the BCB calendar API (probe cal15).

    python3 tools/test_fetch_calendar_cal15.py   -> "N ok, 0 failed"

Fixture is the raw JSON saved by probe cal15 on 2 Nov 2026. Offline; live files checked unchanged.
"""
import hashlib, io, json, os, sys, tempfile
from contextlib import redirect_stdout, redirect_stderr
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import requests  # noqa: E402
import fetch_calendar_br as BR  # noqa: E402

RAW = (ROOT / "tools" / "fixtures" / "calendar" / "bcb_reunioes_copom_20261102.json").read_bytes()
LIVE = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in ROOT.glob("data-calendar-*.json")}
ok = bad = 0
def check(c, n):
    global ok, bad
    if c: ok += 1
    else: bad += 1; print("FAIL", n)
def mutate(f):
    d = json.loads(RAW); f(d["conteudo"]); return json.dumps(d, ensure_ascii=False).encode()

ev, pr = BR.parse(RAW)
d = [e["date"] for e in ev]
check(pr == [], f"parses cleanly: {pr}")
check(d == ["2026-11-04", "2026-12-09", "2027-01-27", "2027-03-17", "2027-04-28", "2027-06-16", "2027-08-04", "2027-09-22",
            "2027-10-27", "2027-12-08"], f"ten decisions, each on the meeting's second day: {d}")
check(d[:2] == ["2026-11-04", "2026-12-09"], "same 2026 dates as the old hand-typed list")
check(all(e["concept"] == "rate_decision" and e["country"] == "Brazil" and e["time"] is None and e["source"] == BR.SRC
          and "\u2014" not in e["name"] for e in ev), "event fields, no invented time")
check(BR.parse(mutate(lambda c: c.pop(0)))[0][0]["date"] == "2026-11-04", "a run that starts on day two still gives that day")
check(any("not JSON" in p for p in BR.parse(b"<html>Erro interno</html>")[1]), "an HTML error page is caught")
check(any("no 'conteudo'" in p for p in BR.parse(b'{"x": 1}')[1]), "a changed shape is caught")
check(any("no meeting days" in p for p in BR.parse(b'{"conteudo": []}')[1]), "an empty list is caught")
check(any("unexpected entry" in p for p in BR.parse(mutate(lambda c: c[0].update(evento="Feriado")))[1]), "a non-Copom entry is caught")
check(any("not read" in p for p in BR.parse(mutate(lambda c: c[0].update(dataEvento="03/11/2026")))[1]), "an unreadable date is caught")
check(any("more than two days" in p for p in BR.parse(mutate(lambda c: c.append(dict(c[1], dataEvento="2026-11-05T03:00:00Z"))))[1]),
      "a three-day run is caught")
check(any("8 times a year" in p for p in BR.parse(json.dumps({"conteudo": [
    {"evento": "Reunião do Copom", "dataEvento": f"2027-{m:02d}-01T03:00:00Z"} for m in range(1, 12)]}).encode())[1]),
      "too many decisions in a year is caught")
tz = BR.parse(mutate(lambda c: c[0].update(dataEvento="2026-11-03T02:00:00Z")))[0]
check([e["date"] for e in tz][:2] == ["2026-11-02", "2026-11-04"], f"dates read in Brasilia time (02:00Z is still 2 Nov there): {[e['date'] for e in tz][:2]}")
p = BR.params(date(2026, 11, 2))
check(p == {"lista": "Reuniões do Copom", "inicioAgenda": "'2026-11-02'", "fimAgenda": "'2027-12-07'"}, f"query as the site sends it: {p}")

class R:
    def __init__(s, body, code=200): s.content, s.status_code = body, code
    def raise_for_status(s):
        if s.status_code != 200: raise requests.HTTPError(str(s.status_code))
def run(resp, existing=None):
    seen = {}
    def get(url, params=None, headers=None, timeout=None):
        seen.update(url=url, params=params)
        if isinstance(resp, Exception): raise resp
        return resp
    old = requests.get; requests.get = get
    cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        if existing is not None: Path(BR.OUT).write_text(existing)
        out, err = io.StringIO(), io.StringIO()
        try:
            with redirect_stdout(out), redirect_stderr(err): rc = BR.main()
            body = Path(BR.OUT).read_text() if Path(BR.OUT).exists() else None
        finally:
            os.chdir(cwd); requests.get = old
    return rc, body, out.getvalue(), err.getvalue(), seen
OLD = '{"events": [{"date": "2026-12-09", "name": "kept"}]}'
rc, body, out, err, seen = run(R(RAW), OLD)
check(rc == 0 and body != OLD and "BCB:" in out and seen["url"] == BR.URL and seen["params"]["lista"] == BR.LISTA, f"good response writes: {out}{err}")
for bad_resp in [R(b"<html>Erro interno do Servidor!</html>", 500), R(b"<html>shell</html>"), requests.ConnectionError("x")]:
    rc, body, out, err, _ = run(bad_resp, OLD)
    check(rc == 0 and body == OLD and err.startswith("WARNING BCB:"), f"failure keeps file and warns: {err}")
rc, body, out, err, _ = run(R('{"conteudo": [{"evento": "Reunião do Copom", "dataEvento": "2020-01-01T03:00:00Z"}]}'.encode()), OLD)
check(body == OLD and "no upcoming" in err, "only past dates keeps the file")

src = (ROOT / "fetch_calendar_br.py").read_text()
yml = (ROOT / ".github" / "workflows" / "update-calendar.yml").read_text()
check("date(2026," not in src and "hardcoded from" not in src.lower(), "no hand-typed dates left")
check("python fetch_calendar_br.py" in yml and "dates hardcoded from news reporting" not in yml, "workflow log line updated")
for n, h in LIVE.items():
    check(hashlib.sha256((ROOT / n).read_bytes()).hexdigest() == h, f"{n} untouched")
print(f"{ok} ok, {bad} failed")
sys.exit(1 if bad else 0)
