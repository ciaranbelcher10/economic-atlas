#!/usr/bin/env node
/* v1.9.102: MPC vote wording from the per-rate tally, Chartmaker preview follows the site theme
 * (PNG background set by its own switch, white by default), touch screens drop the section-chip hover.
 * Run: NODE_PATH=/tmp/node_modules node tools/test_v19102.js */
const fs = require("fs"), path = require("path"), vm = require("vm");
const ROOT = path.resolve(__dirname, "..");
let checks = 0, failures = 0; const ok = (c, m) => { checks++; if (!c) { failures++; console.log("  FAIL  " + m); } };
const UK = fs.readFileSync(path.join(ROOT, "uk.html"), "utf8");
// ---- MPC wording (the helpers run for real) ----
const a = UK.indexOf("function decisionFor"), b = UK.indexOf("function renderMPC(");
ok(a > 0 && b > a, "MPC helpers sit before renderMPC");
const ctx = {}; vm.createContext(ctx); vm.runInContext(UK.slice(a, b), ctx);
const T = (m) => { const r = ctx.mpcVoteSplit(m); return r && r.text; };
ok(T({decision_rate:4, previous_rate:3.75, hold:0, hike:9, cut:0, rate_votes:{"4.25":1, "4":8}}) === "8\u20131 to raise to 4%, 1 preferred 4.25%", "5 Nov reads 8\u20131 to raise to 4%, 1 preferred 4.25%");
ok(T({decision_rate:3.75, previous_rate:3.75, hold:6, hike:3, cut:0, rate_votes:{"4":3, "3.75":6}}) === "6\u20133 to hold at 3.75%, 3 preferred 4%", "hold with dissents");
ok(T({decision_rate:3.75, previous_rate:3.75, hold:7, hike:1, cut:1, rate_votes:{"3.5":1, "3.75":7, "4.25":1}}) === "7\u20132 to hold at 3.75%, 1 preferred 4.25%, 1 preferred 3.5%", "split dissent lists the higher rate first");
ok(T({decision_rate:4, previous_rate:3.75, hold:0, hike:9, cut:0, rate_votes:{"4":9}}) === "9\u20130 to raise to 4%", "unanimous has no preferred clause");
ok(T({decision_rate:0.1, previous_rate:0.25, hold:0, hike:0, cut:9, rate_votes:{"0.1":9}}) === "9\u20130 to cut to 0.1%", "cut wording and small rates");
ok(ctx.mpcVoteSplit({decision_rate:4, previous_rate:3.75, hold:0, hike:9, cut:0}) === null, "no tally falls back");
ok(ctx.mpcVoteSplit({decision_rate:4, previous_rate:3.75, rate_votes:{"4.25":9}}) === null, "tally without the decided rate falls back");
ok(ctx.mpcVoteCounts({hike:9, hold:0, cut:0}) === "9 to raise, 0 to hold, 0 to cut", "fallback is plain counts");
const R = UK.slice(b, UK.indexOf("function renderMPCHistory"));
ok(/mpcVoteSplit\(latest\)/.test(R) && /split\.score \+ " <small>" \+ split\.what \+ split\.pref/.test(R), "latest card shows the score large and the wording small");
ok(!/voteLabel/.test(R), "old hold\u2013hike label gone from the latest card");
ok(/var hsplit = mpcVoteSplit\(m\);\s*var votePart = hsplit \? hsplit\.score/.test(UK), "history rows use the same score");
// ---- fetcher writes the tally ----
const PY = fs.readFileSync(path.join(ROOT, "fetch_boe_mpc.py"), "utf8");
ok(/"rate_votes": rate_votes/.test(PY) && /def _rate_key/.test(PY), "fetcher emits rate_votes");
// ---- Chartmaker ----
const CM = fs.readFileSync(path.join(ROOT, "chartmaker.html"), "utf8");
ok(/czmBuildBars\(cmPreviewTheme\(\), false\) : czmBuildSVG\(cmPreviewTheme\(\), false\)/.test(CM), "preview builds with the site theme");
ok(/czmBuildBars\(exportTheme, true\)/.test(CM) && /czmBuildSVG\(exportTheme, true\)/.test(CM), "PNG builds with the switch's theme");
ok(/var exportTheme = "light";/.test(CM), "PNG defaults to white");
ok(!/THEMES\[exportTheme\]/.test(CM), "no preview colour still reads the PNG theme");
ok(/attributeFilter:\["data-theme"\]/.test(CM), "preview re-renders when the site theme flips");
const seg = CM.slice(CM.indexOf('getElementById("cmThemeSeg").querySelectorAll'), CM.indexOf('getElementById("cmThemeSeg").querySelectorAll') + 500);
ok(!/renderChart\(\)/.test(seg.split("});\n});")[0]), "PNG switch no longer repaints the preview");
ok(/<span class="cm-pnglbl" id="cmThemeLbl">PNG<\/span>/.test(CM) && /aria-labelledby="cmThemeLbl"/.test(CM), "switch is labelled PNG");
ok(/\[data-theme="dark"\] \.cm-chart-outer\{background:#12181A;\}/.test(CM), "dark frame behind the dark preview");
const ctx2 = { document: { documentElement: { attr: null, getAttribute(){ return this.attr; } } } };
vm.createContext(ctx2); vm.runInContext((CM.match(/function cmPreviewTheme\(\)\{[\s\S]*?\n\}/) || [""])[0], ctx2);
ok(ctx2.cmPreviewTheme() === "light", "light site, light preview");
ctx2.document.documentElement.attr = "dark"; ok(ctx2.cmPreviewTheme() === "dark", "dark site, dark preview");
// ---- section chips ----
const ST = fs.readFileSync(path.join(ROOT, "style.css"), "utf8");
ok(/@media \(hover:none\)\{\s*nav\.cat button:not\(\.active\):hover\{border-color:var\(--hair\); color:var\(--ink\);\}/.test(ST), "touch screens drop the chip hover");
console.log(`test_v19102: ${checks} checks, ${failures} failures`);
process.exit(failures ? 1 : 0);
