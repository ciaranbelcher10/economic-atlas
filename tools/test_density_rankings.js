#!/usr/bin/env node
/* v1.9.101 density pass, part 1 (phones): ranking rows, promo cards, rankings index.
 * jsdom has no layout, so CSS is checked statically; markup is checked on a freshly
 * generated ranking page when one is present (the bot regenerates rankings/).
 * Run: NODE_PATH=/tmp/node_modules node tools/test_density_rankings.js */
const fs = require("fs"), path = require("path");
const ROOT = path.resolve(__dirname, "..");
let checks = 0, failures = 0; const ok = (c, m) => { checks++; if (!c) { failures++; console.log("  FAIL  " + m); } };
const CSS = fs.readFileSync(path.join(ROOT, "indicator.css"), "utf8");
const blk = (CSS.split("/* v1.9.101 density pass")[1] || "");
const PH = (blk.match(/@media \(max-width:640px\)\{([\s\S]*)\}\s*$/) || [])[1] || "";
ok(/\.ind-ph\{display:none;\}/.test(blk.split("@media")[0]), "desktop hides phone-only copy");
ok(/\.ind-dt\{display:none;\} \.ind-ph\{display:inline;\}/.test(PH), "phones swap in the short intro");
ok(/\.rk-table\{min-width:0;/.test(PH) && /\.rk-scroll\{overflow-x:visible;/.test(PH), "ranking table fits the phone, no sideways scroll");
ok(/\.rk-table tr > :nth-child\(n\+4\)\{display:none;\}/.test(PH), "phones show rank, country and value only");
ok(/\.rk-table td\{padding:7px 6px;\}/.test(PH), "ranking rows tight (7px padding)");
ok(/td\.country \.rk-region\{display:inline;/.test(PH), "region sits beside the country name");
ok(/\.glow-inner\{padding:10px 12px 10px 14px;/.test(PH) && /\.glow-sub\{[^}]*white-space:nowrap;[^}]*text-overflow:ellipsis;/.test(PH), "promo cards one slim row");
ok(/\.glow-go\{width:32px; height:32px;\}/.test(PH), "promo arrow 32px");
ok(/\.rkx-grid\{grid-template-columns:1fr;\}/.test(PH) && /\.rkx-meta\{display:none;\}/.test(PH) && /\.rkx-card\{[^}]*min-height:52px;/.test(PH), "rankings index rows 52px, one column");
const G = fs.readFileSync(path.join(ROOT, "generate_indicator_pages.py"), "utf8");
ok(/KIT_VERSION = "(\d+)"/.test(G) && +G.match(/KIT_VERSION = "(\d+)"/)[1] >= 10, "generator bumps indicator.css to v10+");
ok(/<span class="ind-ph">Every economy ranked on like-for-like measures\.<\/span>/.test(G), "rankings index carries the one-line phone intro");
// the hidden columns are the right ones (order rank, country, value first)
const th = G.slice(G.indexOf('<table class="rk-table" id="rkTable">'), G.indexOf("</thead>", G.indexOf('<table class="rk-table" id="rkTable">')));
const sorts = [...th.matchAll(/data-sort="([a-z]+)"/g)].map(m => m[1]);
ok(sorts.slice(0, 3).join() === "rank,country,value", "first three ranking columns are rank, country, value (" + sorts.slice(0, 3) + ")");
const rk = path.join(ROOT, "rankings", "unemployment-rate-by-country.html");
if (fs.existsSync(rk)) { const h = fs.readFileSync(rk, "utf8"); const tr = (h.match(/<tr data-rank="1"[\s\S]*?<\/tr>/) || [""])[0];
  const cls = [...tr.matchAll(/<td class="([^"]+)"/g)].map(m => m[1]);
  ok(cls[0] === "rank" && cls[1] === "country" && /val/.test(cls[2]), "generated rows put rank, country, value first (" + cls.slice(0, 3) + ")"); }
console.log(`test_density_rankings: ${checks} checks, ${failures} failures`);
process.exit(failures ? 1 : 0);
