#!/usr/bin/env node
/* v1.9.104: desktop titles 40px under the menu (size unchanged), account initial for any character,
 * Compare one-line intro and click/tap wording, Dashboard explanation behind (i), Markets short title,
 * Rankings one-line intro, ticker fade. jsdom has no layout: CSS is checked statically (the 40px was
 * measured in a real browser when built); the account and Compare wording code runs for real.
 * Run after tools/migrate_v19104.py:  NODE_PATH=/tmp/node_modules node tools/test_v19104.js */
const fs = require("fs"), path = require("path"), vm = require("vm");
const ROOT = path.resolve(__dirname, "..");
let checks = 0, failures = 0; const ok = (c, m) => { checks++; if (!c) { failures++; console.log("  FAIL  " + m); } };
const rd = f => fs.readFileSync(path.join(ROOT, f), "utf8");
const ST = rd("style.css"), V = ST.split("/* v1.9.104 one page top on desktop")[1] || "";
ok(V, "style.css carries the v1.9.104 block");
const D = (V.match(/@media \(min-width:901px\)\{([\s\S]*?)\n\}/) || [])[1] || "";
ok(/header\.page\{padding-top:24px;\}/.test(D), "page headers start 24px under the banner strip (16px + 24px = 40px)");
ok(/header\.page h1, \.ind-head h1, \.wrap > h1, #dashMainWrap h1\{margin-top:0;\}/.test(D), "titles carry no extra top margin");
ok(/#homeQuickNav\{margin-top:24px !important;\}/.test(D), "Home and country search box at the same 40px");
ok(/\.ind-wrap\.doc-wrap\{padding-top:24px;\}/.test(D) && /\.ind-wrap:not\(\.doc-wrap\)\{padding-top:40px;\}/.test(D), "About, Methodology, Rankings and indicator pages at 40px");
ok(/header\.mk-hero\{margin-top:24px;\}/.test(D), "Markets hero card at 40px");
ok(/\.dash-sidebar\[hidden\] ~ #dashMainWrap\{padding-left:0 !important; padding-right:0 !important;\}/.test(D), "signed-out Dashboard title on the shared edge");
ok(!/font-size/.test(D), "desktop block changes no title size");
ok(/\.mk-hero h1\{font-weight:600 !important;\}/.test(V), "Markets title same weight as the rest");
ok(/\.mk-hero h1 \.mk-dt\{display:none;\}/.test(V), "Markets title drops ', economy by economy'");
ok(/\.rk-wrap \.ind-lede\{max-width:none;\}/.test(V), "Rankings intro may run one line");
ok(/@media \(min-width:761px\)\{ body \.ht-viewport\{-webkit-mask-image:linear-gradient\(to right, transparent 0, #000 56px/.test(V), "ticker fades over 56px on desktop");
ok(/\.wrap\[style\*="padding:30px 24px 60px"\]\{padding-top:24px !important;\}/.test(D) && /id="dashMainWrap" style="padding:30px 24px 60px;"/.test(rd("dashboard.html")), "Compare and Dashboard tops match on desktop, phone rule still keyed");
// Compare
const C = rd("compare.html");
ok((C.match(/Rank and compare 62 economies on GDP, inflation, jobs, debt, trade and rates, for one year or over the last 10\./g) || []).length === 1 && !/Looking for a single ranking/.test(C), "Compare has a one-line intro");
const lab = (C.match(/var label = n === 0 \? "Choose countries" : [^\n]*/) || [""])[0];
const run = (n, hover) => { const c = { window:{ matchMedia:q => ({ matches: q === "(hover:none)" ? !hover : false }) }, n }; vm.createContext(c); vm.runInContext(lab.replace("var label", "label") , c); return c.label; };
ok(run(4, true) === "4 countries selected, click to change", "desktop says click: " + run(4, true));
ok(run(4, false) === "4 countries selected, tap to change", "touch says tap");
ok(run(1, true) === "1 country selected, click to change", "singular kept");
// Dashboard
const DB = rd("dashboard.html");
ok(/<button type="button" class="dash-d-info" id="dashInfoBtn" aria-label="What these switches do" aria-expanded="false" aria-controls="dashToggleNote">i<\/button>\n <span class="mtoggle-note" id="dashToggleNote">/.test(DB), "Dashboard has an (i) before the explanation");
ok(/#dashMainWrap \.metric-toggles \.mtoggle-note\{display:none;\}/.test(V) && /#dashMainWrap \.metric-toggles\.note-open \.mtoggle-note\{display:block;/.test(V), "explanation hidden until (i) is pressed");
ok(/@media \(max-width:760px\)\{ \.dash-d-info\{display:none !important;\} \}/.test(V), "phones keep their own (i)");
const js = (DB.match(/<script>\n\/\* v1\.9\.104: on desktop[\s\S]*?<\/script>/) || [""])[0].replace(/<\/?script>/g, "");
const tg = { cls:new Set(), classList:{ contains:c => tg.cls.has(c), toggle:(c, on) => on ? tg.cls.add(c) : tg.cls.delete(c) } };
const btn = { parentNode:tg, attrs:{}, h:null, addEventListener(e, f){ this.h = f; }, setAttribute(k, v){ this.attrs[k] = v; } };
const c2 = { document:{ getElementById:id => id === "dashInfoBtn" ? btn : null } }; vm.createContext(c2); vm.runInContext(js, c2);
btn.h(); ok(tg.cls.has("note-open") && btn.attrs["aria-expanded"] === "true", "(i) opens the explanation");
btn.h(); ok(!tg.cls.has("note-open") && btn.attrs["aria-expanded"] === "false", "(i) closes it again");
// Rankings intro
const G = rd("generate_indicator_pages.py");
ok(/<span class="ind-dt">Every economy we track, ranked on like-for-like measures and updated automatically from official sources\.<\/span>/.test(G), "Rankings index has a one-line intro");
// Account initial on every page, and it runs
const GEN = new Set(["methodology-by-economy.html","gdp-by-country.html","inflation-by-country.html","unemployment-by-country.html","data-status.html"]);
const pages = fs.readdirSync(ROOT).filter(f => f.endsWith(".html") && !GEN.has(f) && /function updateAuthUI\(session\)/.test(rd(f)));
ok(pages.length >= 70 && pages.every(f => /String\.fromCharCode\(92\)/.test(rd(f)) && !/\.replace\(\/\[\^A-Z0-9\]\/, "\?"\)/.test(rd(f))), "every sign-in page uses the any-character initial (" + pages.length + ")");
ok(/String\.fromCharCode\(92\)/.test(G), "generator template matches");
const IX = rd("index.html"), a = IX.indexOf("function updateAuthUI(session){");
const body = IX.slice(a, IX.indexOf("\n  }\n", a) + 4);
const b = { attrs:{}, cls:new Set(), innerHTML:"", textContent:"", title:"", setAttribute(k, v){ this.attrs[k] = v; }, removeAttribute(k){ delete this.attrs[k]; } };
b.classList = { add:c => b.cls.add(c), remove:c => b.cls.delete(c) };
const c3 = { authBtn:b, window:{} }; vm.createContext(c3); vm.runInContext(body, c3);
const ini = em => { c3.updateAuthUI({ user:{ email:em, id:"u" } }); const m = b.innerHTML.match(/^<span class="acct-i" aria-hidden="true">(.*)<\/span>Account$/); return m ? m[1] : "BAD " + b.innerHTML; };
const want = { "ciaran@x.com":"C", "9am@x":"9", "élodie@x":"É", "ödön@x":"Ö", "ßen@x":"ß", "Ωmega@x":"Ω", "李雷@x":"李", "ابن@x":"ا", "_a@x":"?", "+n@x":"?", "<b>@x":"?", "😀@x":"?", "\u0301a@x":"?", "":"?" };
for (const [em, w] of Object.entries(want)) ok(ini(em) === w, `initial for ${JSON.stringify(em)} is ${w}, got ${ini(em)}`);
console.log(`test_v19104: ${checks} checks, ${failures} failures`);
process.exit(failures ? 1 : 0);
