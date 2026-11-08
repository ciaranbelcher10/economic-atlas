#!/usr/bin/env node
/* v1.9.103 desktop consistency: round theme button and "Account" button in the header, one left
 * edge (About, Methodology, Compare, Chartmaker, key-figures panel, dashboard sidebar), no page
 * kickers, home title not indented, one freshness-key wording site-wide.
 * jsdom has no layout, so CSS is checked statically; the account label code runs for real.
 * Run after tools/migrate_v19103.py:  NODE_PATH=/tmp/node_modules node tools/test_v19103.js */
const fs = require("fs"), path = require("path"), vm = require("vm");
const ROOT = path.resolve(__dirname, "..");
let checks = 0, failures = 0; const ok = (c, m) => { checks++; if (!c) { failures++; console.log("  FAIL  " + m); } };
const rd = f => fs.readFileSync(path.join(ROOT, f), "utf8");
const ST = rd("style.css");
const V = (ST.split("/* v1.9.103 desktop consistency.")[1] || "");
ok(V, "style.css carries the v1.9.103 block");
ok(/@media \(min-width:901px\)\{\s*nav\.top \.theme-toggle\{align-self:center; width:34px; height:34px; padding:0; border-radius:50%;/.test(V), "desktop theme button is a 34px circle centred in the bar");
ok(/nav\.top \.authbtn\.signed-in\{align-self:center;[^}]*border-radius:999px;\}/.test(V), "signed-in account button is a pill");
ok(/\.authbtn \.acct-i\{width:24px; height:24px; border-radius:50%;/.test(V), "initial sits in a 24px circle");
ok(/\.ind-wrap\.doc-wrap\{max-width:1140px;\}/.test(V) && /\.wrap\{max-width:1140px;/.test(ST), "About and Methodology use the site container width");
ok(/\.wrap \.wrap\.kf-wrap\{padding-left:0 !important; padding-right:0 !important;\}/.test(V), "key-figures panel keeps the shared edge");
ok(/\.eyebrow\{display:none !important;\}/.test(V), "page kickers hidden");
ok(/\.hero-h1 \.hero-led:empty\{display:none;\}/.test(V), "home title not pushed in by the empty status span");
ok(/\.dash-sidebar\{margin-left:0;\}/.test(V), "dashboard sidebar starts on the edge");
ok(!/max-width:1080px/.test(rd("compare.html")), "Compare drops its narrower container");
ok(!/\.cm-wrap\{max-width:1520px;\}/.test(rd("chartmaker.html")), "Chartmaker drops its full-bleed container");
// freshness wording and account code on every hand-written page
const GEN = new Set(["methodology-by-economy.html","gdp-by-country.html","inflation-by-country.html","unemployment-by-country.html","data-status.html"]);
const pages = fs.readdirSync(ROOT).filter(f => f.endsWith(".html") && !GEN.has(f));
const OLD = [/&nbsp;matches latest release</, /&nbsp;not refreshed recently</, />Latest version of the data is live</, />Data may be outdated, awaiting next update</, /authBtn\.textContent = session\.user\.email;/];
const stale = pages.filter(f => OLD.some(r => r.test(rd(f))));
ok(stale.length === 0, "no page keeps an old wording or email label: " + stale.slice(0, 5).join(", "));
const uk = rd("uk.html");
ok((uk.match(/&nbsp;Up to date<\/span>/g) || []).length >= 6 && (uk.match(/&nbsp;Awaiting update<\/span>/g) || []).length >= 6, "country page keys read Up to date / Awaiting update");
ok(/<\/span>Up to date<\/span>/.test(rd("compare.html")) && /<\/span>Awaiting update<\/span>/.test(rd("dashboard.html")), "Compare and Dashboard keys match");
const G = rd("generate_indicator_pages.py");
ok(/'Up to date<\/span>/.test(G) && /'Awaiting update<\/span><\/p>'\)/.test(G), "generated pages get the same key");
const withAuth = pages.filter(f => /function updateAuthUI\(session\)/.test(rd(f)));
ok(withAuth.length >= 70 && withAuth.every(f => /<span class="acct-i" aria-hidden="true">' \+ ini \+ '<\/span>Account'/.test(rd(f))), "every page with sign-in shows the account button (" + withAuth.length + ")");
ok(/<span class="acct-i" aria-hidden="true">' \+ ini \+ '<\/span>Account'/.test(G), "generator template matches");
// run the real updateAuthUI from index.html with a stub button
const IX = rd("index.html"), a = IX.indexOf("function updateAuthUI(session){");
const body = IX.slice(a, IX.indexOf("\n  }\n", a) + 4);
const mk = () => ({ attrs:{}, cls:new Set(), innerHTML:"", textContent:"", title:"",
  setAttribute(k,v){ this.attrs[k]=v; }, removeAttribute(k){ delete this.attrs[k]; if(k==="title") this.title=""; },
  classList:null });
const b = mk(); b.classList = { add:c=>b.cls.add(c), remove:c=>b.cls.delete(c) };
const ctx = { authBtn:b, window:{} }; vm.createContext(ctx); vm.runInContext(body, ctx);
ctx.updateAuthUI({ user:{ email:"ciaran@example.com", id:"u1" } });
ok(b.innerHTML === '<span class="acct-i" aria-hidden="true">C</span>Account', "signed in: C + Account, got " + b.innerHTML);
ok(b.title === "Signed in as ciaran@example.com" && /ciaran@example\.com/.test(b.attrs["aria-label"]) && b.cls.has("signed-in"), "email kept in tooltip and label");
ctx.updateAuthUI({ user:{ email:"<b>x@y", id:"u2" } });
ok(b.innerHTML === '<span class="acct-i" aria-hidden="true">?</span>Account', "odd first character becomes ?, nothing injected");
ctx.updateAuthUI(null);
ok(b.textContent === "Sign Up" && !b.attrs["aria-label"] && !b.cls.has("signed-in"), "signed out: Sign Up, label cleared");
console.log(`test_v19103: ${checks} checks, ${failures} failures`);
process.exit(failures ? 1 : 0);
