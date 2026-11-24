// v2.0.16: ppp.js rules. node tools/test_v216_ppp.js
const P = require("../ppp.js"); let f = 0;
const ok = (c, m) => { if(!c){ f++; console.log("FAIL", m); } };
const fac = [["2023", 0.672], ["2024", 0.675]];
let r = P.convert([{x:"2023-Q4",y:700000},{x:"2024",y:2904950},{x:"2025",y:3000000},{x:"2026",y:1}], "£m", fac);
ok(r.pts.length === 2 && Math.abs(r.pts[1].y - 2904950/0.675) < 1e-6, "each year by its own factor");
ok(r.unit === "Int$m", "unit Int$m");
ok(r.droppedYears.join() === "2025,2026", "missing years dropped");
ok(/2025 and 2026 not shown at current prices: PPP factor for 2025 and 2026 not yet published/.test(P.note(r, "2024")), "note names years");
let g = P.convertReal([{x:"2023",y:100},{x:"2024",y:110}], "£m (2022 prices)", fac, {year:"2024", deflator:1.2});
ok(g.ok && Math.abs(g.pts[1].y / g.pts[0].y - 1.1) < 1e-12, "real growth unchanged");
ok(g.unit === "Int$m (2024 prices)", "real unit");
ok(!P.convertReal([{x:"2024",y:1}], "£m", fac, {year:"2019", deflator:1}).ok, "no anchor factor -> not offered");
ok(!P.convert([{x:"2024",y:1}], "£m", []).ok, "no factors -> ok false");
ok(P.eligible("gdp_level") && !P.eligible("exports"), "GDP family only");
ok(/not available/.test(P.note(null, null, {notOffered:true})), "not offered note");
console.log(f ? f + " failed" : "test_v216_ppp: all passed"); process.exit(f ? 1 : 0);
