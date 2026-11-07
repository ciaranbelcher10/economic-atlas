#!/usr/bin/env node
/* v1.9.98: signing up with an email that already has an account switches the modal to Log in,
 * keeps the email and password typed, and says so. Covers both shapes Supabase uses: an
 * "already registered" error, and (with email confirmation on) a user with no identities.
 * Also checks a genuinely new sign-up and a plain error are unchanged, and that every page
 * with the auth script (plus the indicator page generator) carries the same handling.
 * Run: NODE_PATH=/tmp/node_modules node tools/test_signup_existing.js */
const fs = require("fs"), path = require("path");
const ROOT = path.resolve(__dirname, ".."), NM = (process.env.NODE_PATH || "/tmp/node_modules").split(path.delimiter)[0] + "/";
const { JSDOM, VirtualConsole, ResourceLoader } = require(NM + "jsdom");
let checks = 0, failures = 0;
const ok = (c, m) => { checks++; if (!c) { failures++; console.log("  FAIL  " + m); } };
const wait = ms => new Promise(r => setTimeout(r, ms));
const SUPA = `window.supabase={createClient:function(){var q={select:function(){return q},eq:function(){return q},order:function(){return q},upsert:function(){return Promise.resolve({})},maybeSingle:function(){return Promise.resolve({data:null})},then:function(r){return Promise.resolve({data:null}).then(r)}};
return {from:function(){return q},functions:{invoke:function(){return Promise.resolve({data:null})}},auth:{getSession:function(){return Promise.resolve({data:{session:null}})},
onAuthStateChange:function(){return {data:{subscription:{unsubscribe:function(){}}}}},
signUp:function(a){window.__signUpArgs=a;return Promise.resolve(window.__signUpReply)},
signInWithPassword:function(){return Promise.resolve({data:{},error:{message:"Invalid login credentials"}})}}}}};`;
class Loader extends ResourceLoader { fetch(url){ return Promise.resolve(Buffer.from(/supabase/.test(url) ? SUPA : "")); } }
process.on("unhandledRejection", () => {});
async function run(page, reply){
  const vc = new VirtualConsole();
  const dom = new JSDOM(fs.readFileSync(path.join(ROOT, page), "utf8"), { runScripts: "dangerously", resources: new Loader(), pretendToBeVisual: true,
    url: "https://theeconomicatlas.com/" + page, virtualConsole: vc,
    beforeParse(w){ w.__signUpReply = reply; w.fetch = () => Promise.resolve({ ok: false, status: 404, json: () => Promise.reject(new Error("404")) });
      w.matchMedia = () => ({ matches: false, addListener(){}, removeListener(){}, addEventListener(){}, removeEventListener(){} });
      w.scrollTo = () => {}; w.HTMLCanvasElement.prototype.getContext = () => null;
      w.ResizeObserver = class { observe(){} unobserve(){} disconnect(){} }; w.IntersectionObserver = class { observe(){} unobserve(){} disconnect(){} }; } });
  const w = dom.window, d = w.document; await wait(400);
  d.getElementById("authBtn").click(); await wait(50);
  const title0 = d.getElementById("authModalTitle").textContent;
  d.getElementById("authEmail").value = "me@example.com"; d.getElementById("authPassword").value = "secret123";
  d.getElementById("authForm").dispatchEvent(new w.Event("submit", { cancelable: true })); await wait(100);
  const r = { title0, title: d.getElementById("authModalTitle").textContent, submit: d.getElementById("authSubmitBtn").textContent,
    email: d.getElementById("authEmail").value, pw: d.getElementById("authPassword").value,
    msg: d.getElementById("authMsg").textContent, cls: d.getElementById("authMsg").className, args: w.__signUpArgs };
  w.close(); return r;
}
(async () => {
  const PAGES = ["uk.html", "index.html", "compare.html", "calendar.html", "markets.html"].filter(p => fs.existsSync(path.join(ROOT, p)));
  for (const p of PAGES) {
    let r = await run(p, { data: { user: { id: "u", identities: [] }, session: null }, error: null });
    ok(r.title0 === "Sign up", p + ": header button opens Sign up (" + r.title0 + ")");
    ok(r.args && r.args.email === "me@example.com", p + ": sign-up sent the typed email");
    ok(r.title === "Log in" && r.submit === "Log in", p + ": existing account (no identities) switches to Log in (" + r.title + ")");
    ok(r.email === "me@example.com" && r.pw === "secret123", p + ": keeps the email and password typed");
    ok(/already have an account/.test(r.msg) && /show/.test(r.cls), p + ": says they already have an account (" + r.msg + ")");
    r = await run(p, { data: { user: null, session: null }, error: { message: "User already registered" } });
    ok(r.title === "Log in" && /already have an account/.test(r.msg), p + ": 'already registered' error switches to Log in");
    r = await run(p, { data: { user: { id: "u", identities: [{ id: "i" }] }, session: null }, error: null });
    ok(r.title === "Sign up" && /Check your email to confirm/.test(r.msg), p + ": a new account still asks to confirm by email");
    r = await run(p, { data: {}, error: { message: "Password should be at least 6 characters" } });
    ok(r.title === "Sign up" && /at least 6/.test(r.msg) && /error/.test(r.cls), p + ": other errors still show as errors on Sign up");
  }
  // every page with the auth script, and the generator, carries the handling
  const files = fs.readdirSync(ROOT).filter(f => f.endsWith(".html")).concat(["generate_indicator_pages.py"]);
  const withAuth = files.filter(f => fs.readFileSync(path.join(ROOT, f), "utf8").includes("sb.auth.signUp("));
  const missing = withAuth.filter(f => !fs.readFileSync(path.join(ROOT, f), "utf8").includes("res.data.user.identities.length === 0"));
  ok(withAuth.length > 50 && missing.length === 0, "every top-level page with sign-up and the generator handle existing accounts (" + withAuth.length + " files, missing: " + missing.slice(0, 5).join(", ") + ")");
  console.log(`test_signup_existing: ${checks} checks, ${failures} failures`);
  process.exit(failures ? 1 : 0);
})();
