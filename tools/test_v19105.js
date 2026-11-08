#!/usr/bin/env node
/* v1.9.105 density part 2 (phones): one-line home intro and "Jump to", shorter UK map, short swipe hint,
 * MPC card 2 x 2, one-line Compare rank rows, Dashboard on the shared edge with a one-line banner,
 * full-width Add a metric and a 2-line footer, one freshness wording. Desktop text restored on resize.
 * jsdom has no layout: CSS checked statically (layout was checked in Chromium at 390px when built).
 * Run: NODE_PATH=/tmp/node_modules node tools/test_v19105.js */
const fs = require("fs"), path = require("path"), { JSDOM } = require("jsdom");
const ROOT = path.resolve(__dirname, "..");
let checks = 0, failures = 0; const ok = (c, m) => { checks++; if (!c) { failures++; console.log("  FAIL  " + m); } };
const MC = fs.readFileSync(path.join(ROOT, "mobile.css"), "utf8"), MJ = fs.readFileSync(path.join(ROOT, "mobile.js"), "utf8");
const B = (MC.split("/* v1.9.105 density part 2 (phones) */")[1] || "");
ok(/^\s*@media \(max-width:760px\)\{/.test(B), "phone-only block");
const has = (re, m) => ok(re.test(B), m);
has(/\.home-pop-lab\{ white-space:nowrap !important; \}/, "Jump to on one line");
has(/\.mini-mapwrap:not\(\.mm-expanded\)\{ max-height:130px !important; \}/, "collapsed map 130px");
has(/\.mpc-latest\{ display:grid !important; grid-template-columns:1fr 1fr;/, "MPC card is a 2 x 2 grid");
has(/\.mpc-latest > :not\(\.mpc-stat\)\{ grid-column:1 \/ -1; \}/, "vote bar and legend span the card");
has(/\.mpc-legend\{ flex-direction:row !important;/, "MPC legend on one row");
has(/body\.cmp-m \.tpm-rankrow \.tpm-rankvalue \.per\{ display:inline !important;/, "Compare year sits beside the value");
has(/body\.cmp-m \.cmp-rk-bar\{ height:4px !important; \}/, "slim Compare bars");
has(/#dashMainWrap\{ padding-left:0 !important; padding-right:0 !important; \}/, "Dashboard on the shared 16px edge");
has(/body\.dash-m #saveBar\{[^}]*flex-wrap:nowrap !important;/, "Dashboard banner on one line");
has(/body\.dash-m #saveBar \.savebar-icon\{ display:none !important; \}/, "banner icon hidden");
has(/#addMetricTile\{ grid-column:1 \/ -1 !important; min-height:64px !important;/, "Add a metric full width and short");
ok(!/Swipe left or right for other sections/.test(MJ), "swipe hint stays short");
ok(/var CMP_SHORT_LEDE = "Rank 62 economies side by side\.";/.test(MJ), "Compare phone intro one line");
ok(/Up to date<\/span><span><span class="led orange" aria-hidden="true"><\/span>Awaiting update<\/span>/.test(MJ) && !/>Latest data</.test(MJ), "Compare phone key uses the site wording");
ok(/safeCall\(densityTwo\);\n  \}\n/.test(MJ) && /alignCountryMapWithSearch\(\); safeCall\(densityTwo\);/.test(MJ), "runs on load and on resize");
// run densityTwo for real
const fn = (MJ.match(/\n  function densityTwo\(\)\{[\s\S]*?\n  \}\n/) || [""])[0];
ok(fn, "densityTwo found");
const dom = new JSDOM(`<h1 class="hero-h1">T</h1><p>Long home intro.</p>
  <div id="dashMainWrap"><div id="saveBar"><p>Everything you pin here resets.</p></div>
  <footer class="dash-foot">\n Every figure long footer text.\n <div class="lnk-row"><a>Privacy</a></div></footer></div>`);
const w = dom.window; let phone = true; w.matchMedia = q => ({ matches: phone && q === "(max-width:760px)" });
new w.Function("document", "window", fn + "\ndensityTwo(); this.dt = densityTwo;").call(w, w.document, w);
const d = w.document, intro = d.querySelector(".hero-h1").nextElementSibling, sb = d.querySelector("#saveBar p"), ft = d.querySelector("footer");
ok(intro.textContent === "Official data for 62 economies.", "phone home intro: " + intro.textContent);
ok(sb.textContent === "Sign up free to keep this dashboard.", "phone banner text");
ok(/Figures are read live from each country's own data\. Signed in, your tiles are saved\./.test(ft.textContent) && ft.querySelector(".lnk-row"), "phone footer short, buttons kept");
phone = false; w.dt();
ok(intro.textContent === "Long home intro." && sb.textContent === "Everything you pin here resets." && /Every figure long footer text\./.test(ft.textContent), "desktop text restored");
phone = true; w.dt(); w.dt();
ok(intro.textContent === "Official data for 62 economies." && (ft.textContent.match(/Figures are read live/g) || []).length === 1, "idempotent");
console.log(`test_v19105: ${checks} checks, ${failures} failures`);
process.exit(failures ? 1 : 0);
