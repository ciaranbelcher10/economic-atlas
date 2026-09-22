// Parity check: indicator-kit.js fmtNum() must print exactly what the
// Python fmt_num() baked into the page. Run tools/test_indicator_fmt.py first.
global.window = {}; global.document = {};
require("../indicator-kit.js");
const F = window.EATLAS_FMT;
const cases = JSON.parse(require("fs").readFileSync("/tmp/fmt_cases.json", "utf8"));
let bad = 0;
for (const [v, unit, key, country, mode, want] of cases) {
  const got = F.fmtNum(v, {unit, key, country, mode});
  if (got !== want) { if (bad < 15) console.log("MISMATCH", country, key, mode, v, "py:", want, "js:", got); bad++; }
}
console.log(cases.length + " cases, " + bad + " mismatches");
process.exit(bad ? 1 : 0);
