#!/usr/bin/env node
/* v2.0.3-polish: the sign-up form shows a Terms of Service / Privacy notice with two buttons;
 * the log-in form does not. Checks a root page, an indicator page, and that every page
 * carrying the auth modal (plus the indicator page generator) has the notice and toggle.
 * Run: NODE_PATH=/tmp/node_modules node tools/test_signup_terms.js */
const fs = require("fs"), path = require("path");
const ROOT = path.resolve(__dirname, ".."), NM = (process.env.NODE_PATH || "/tmp/node_modules").split(path.delimiter)[0] + "/";
const { JSDOM, VirtualConsole, ResourceLoader } = require(NM + "jsdom");
let checks = 0, failures = 0;
const ok = (c, m) => { checks++; if (!c) { failures++; console.log("  FAIL  " + m); } };
const wait = ms => new Promise(r => setTimeout(r, ms));
const SUPA = `window.supabase={createClient:function(){var q={select:function(){return q},eq:function(){return q},order:function(){return q},upsert:function(){return Promise.resolve({})},maybeSingle:function(){return Promise.resolve({data:null})},then:function(r){return Promise.resolve({data:null}).then(r)}};
return {from:function(){return q},functions:{invoke:function(){return Promise.resolve({data:null})}},auth:{getSession:function(){return Promise.resolve({data:{session:null}})},
onAuthStateChange:function(){return {data:{subscription:{unsubscribe:function(){}}}}},signUp:function(){return Promise.resolve({data:{},error:null})},
signInWithPassword:function(){return Promise.resolve({data:{},error:null})}}}}};`;
class Loader extends ResourceLoader { fetch(url){ return Promise.resolve(Buffer.from(/supabase/.test(url) ? SUPA : "")); } }
process.on("unhandledRejection", () => {});
const fatal = e => { console.log("  FAIL  " + (e && e.stack || e)); process.exit(1); };
async function run(page){
  const dom = new JSDOM(fs.readFileSync(path.join(ROOT, page), "utf8"), { runScripts: "dangerously", resources: new Loader(), pretendToBeVisual: true,
    url: "https://theeconomicatlas.com/" + page.replace(/\.html$/, ""), virtualConsole: new VirtualConsole(),
    beforeParse(w){ w.fetch = () => Promise.resolve({ ok: false, status: 404, json: () => Promise.reject(new Error("404")) });
      w.matchMedia = () => ({ matches: false, addListener(){}, removeListener(){}, addEventListener(){}, removeEventListener(){} });
      w.scrollTo = () => {}; w.HTMLCanvasElement.prototype.getContext = () => null;
      w.ResizeObserver = class { observe(){} unobserve(){} disconnect(){} }; w.IntersectionObserver = class { observe(){} unobserve(){} disconnect(){} }; } });
  const w = dom.window, d = w.document; await wait(400);
  d.getElementById("authBtn").click(); await wait(50);
  const row = () => d.getElementById("authTermsRow"), title = () => d.getElementById("authModalTitle").textContent;
  const states = [[title(), row().hidden]];
  d.querySelector("#authToggleRow button").click(); await wait(30); states.push([title(), row().hidden]);
  const hrefs = [...row().querySelectorAll("a")].map(a => a.getAttribute("href"));
  d.querySelector("#authToggleRow button").click(); await wait(30); states.push([title(), row().hidden]);
  w.close();
  return { states, hrefs };
}
(async () => {
  for (const [page, pre] of [["uk.html", ""], ["compare.html", ""], ["indicators/uk-gdp.html", "../"]]) {
    const r = await run(page);
    const titles = r.states.map(s => s[0]);
    ok(titles.includes("Log in") && titles.includes("Sign up"), `${page}: both modes reached (${titles})`);
    for (const [ti, hid] of r.states) ok(hid === (ti === "Log in"), `${page}: notice ${hid ? "hidden" : "shown"} in ${ti}`);
    ok(JSON.stringify(r.hrefs) === JSON.stringify([pre + "terms", pre + "privacy"]), `${page}: buttons point at Terms and Privacy (${r.hrefs})`);
  }
  const walk = dir => fs.readdirSync(dir, { withFileTypes: true }).flatMap(e => e.name.startsWith(".") || e.name === "_archive" ? [] : e.isDirectory() ? walk(path.join(dir, e.name)) : [path.join(dir, e.name)]);
  let n = 0;
  for (const f of walk(ROOT).filter(f => f.endsWith(".html"))) {
    const t = fs.readFileSync(f, "utf8"); if (!t.includes('id="authSubmitBtn"')) continue; n++;
    const rel = path.relative(ROOT, f), pre = rel.includes(path.sep) ? "../" : "";
    ok(t.includes('id="authTermsRow"') && t.includes(`href="${pre}terms" target="_blank"`) && t.includes('authTermsRow.hidden = (mode === "login")'), `${rel}: notice and toggle present`);
  }
  const g = fs.readFileSync(path.join(ROOT, "generate_indicator_pages.py"), "utf8");
  ok(g.includes('id="authTermsRow"') && g.includes('authTermsRow.hidden = (mode === "login")'), "generator carries the notice");
  console.log(`test_signup_terms: ${checks} checks across ${n} pages, ${failures} failures`);
  process.exit(failures ? 1 : 0);
})().catch(fatal);
