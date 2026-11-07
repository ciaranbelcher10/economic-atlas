// Parity check: indicator-kit.js fmtNum() must print exactly what the
// Python fmt_num() baked into the page. Run tools/test_indicator_fmt.py first.
global.window = {}; global.document = {};
require("../indicator-kit.js");
const F = window.EATLAS_FMT;
// v1.9.97: build the Python side first so this runs on its own in the test loop.
{ const r = require("child_process").spawnSync("python3", [require("path").join(__dirname, "test_indicator_fmt.py")], { stdio: "inherit", env: Object.assign({}, process.env, { PYTHONDONTWRITEBYTECODE: "1" }) });
  if (r.status !== 0) { console.log("test_indicator_fmt: test_indicator_fmt.py failed (exit " + r.status + ")"); process.exit(2); } }
const cases = JSON.parse(require("fs").readFileSync("/tmp/fmt_cases.json", "utf8"));
let bad = 0;
for (const [v, unit, key, country, mode, want] of cases) {
  const got = F.fmtNum(v, {unit, key, country, mode});
  if (got !== want) { if (bad < 15) console.log("MISMATCH", country, key, mode, v, "py:", want, "js:", got); bad++; }
}
console.log(cases.length + " cases, " + bad + " mismatches");
process.exit(bad ? 1 : 0);
