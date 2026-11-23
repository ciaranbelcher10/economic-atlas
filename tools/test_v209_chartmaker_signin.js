#!/usr/bin/env node
/* v2.0.9: signing in on Chartmaker unlocks Download PNG / Download CSV straight away (no reload).
 * Uses the page's real sign-in code with a stub Supabase client. Run: NODE_PATH=/tmp/node_modules node tools/test_v209_chartmaker_signin.js */
const fs = require("fs"), path = require("path");
const ROOT = path.resolve(__dirname, ".."), NM = (process.env.NODE_PATH || "/tmp/node_modules").split(path.delimiter)[0] + "/";
const { JSDOM, VirtualConsole, ResourceLoader } = require(NM + "jsdom");
let checks = 0, failures = 0;
const ok = (c, m) => { checks++; if(!c){ failures++; console.log("  FAIL  " + m); } };
const wait = ms => new Promise(r => setTimeout(r, ms));
const SUPA = `(function(){var cbs=[];var q={select:function(){return q},eq:function(){return q},order:function(){return q},limit:function(){return q},in:function(){return q},
upsert:function(){return Promise.resolve({})},update:function(){return q},insert:function(){return Promise.resolve({})},
single:function(){return Promise.resolve({data:{preferences:{},is_admin:false,plan:"free",credits_balance_pence:0,welcome_shown:true}})},
maybeSingle:function(){return Promise.resolve({data:null})},then:function(r){return Promise.resolve({data:[]}).then(r)}};
var sess=null;window.__signIn=function(){sess={user:{id:"u1",email:"a@b.c"}};cbs.forEach(function(cb){cb("SIGNED_IN",sess)});};
window.supabase={createClient:function(){return {from:function(){return q},rpc:function(){return Promise.resolve({})},functions:{invoke:function(){return Promise.resolve({data:null})}},
auth:{getSession:function(){return Promise.resolve({data:{session:sess}})},onAuthStateChange:function(cb){cbs.push(cb);return {data:{subscription:{unsubscribe:function(){}}}}},
signUp:function(){return Promise.resolve({data:{},error:null})},signInWithPassword:function(){return Promise.resolve({data:{},error:null})},signOut:function(){return Promise.resolve({})}}}}};})();`;
class Loader extends ResourceLoader { fetch(url){ return Promise.resolve(Buffer.from(/supabase/.test(url) ? SUPA : "")); } }
process.on("unhandledRejection", () => {});
(async () => {
  const dom = new JSDOM(fs.readFileSync(path.join(ROOT, "chartmaker.html"), "utf8"), { runScripts: "dangerously", resources: new Loader(), pretendToBeVisual: true,
    url: "https://theeconomicatlas.com/chartmaker", virtualConsole: new VirtualConsole(),
    beforeParse(w){ w.fetch = () => Promise.resolve({ ok: false, status: 404, json: () => Promise.reject(new Error("404")) });
      w.matchMedia = () => ({ matches: false, addListener(){}, removeListener(){}, addEventListener(){}, removeEventListener(){} });
      w.scrollTo = () => {}; w.HTMLCanvasElement.prototype.getContext = () => null;
      w.ResizeObserver = class { observe(){} unobserve(){} disconnect(){} }; w.IntersectionObserver = class { observe(){} unobserve(){} disconnect(){} }; } });
  const w = dom.window, d = w.document; await wait(600);
  const locked = () => ["cmPngBtn", "cmCsvBtn"].map(id => !!d.getElementById(id).querySelector(".lockicon"));
  ok(locked().every(Boolean), "signed out: both export buttons show the padlock");
  ok(typeof w.EATLAS_APPLY_EXPORT_GATE === "function", "the export gate is reachable from the sign-in code");
  w.__signIn(); await wait(50);
  ok(locked().every(x => !x), "straight after signing in: no padlocks (" + locked() + ")");
  console.log(`test_v209_chartmaker_signin: ${checks} checks, ${failures} failures`);
  process.exit(failures ? 1 : 0);
})().catch(e => { console.log("ERROR " + e.stack); process.exit(1); });
