#!/usr/bin/env node
/* v1.9.90 free limits with the Compare-style warning (meter, padlocks, sign-up card), no forced log-in:
 *  - Compare desktop: 4 countries logged out; the country picker shows the card instead of the log-in form
 *  - Calendar (desktop and phone, same picker): 3 countries logged out, every country logged in
 * Run: NODE_PATH=/tmp/node_modules node tools/test_free_caps.js */
const fs = require("fs"), path = require("path");
const { JSDOM, VirtualConsole } = require("jsdom");
const ROOT = path.resolve(__dirname, "..");
const bootCompare = require("./compare_harness");
let checks = 0, failures = 0;
const ok = (c, m) => { checks++; if(!c){ failures++; console.log("  FAIL  " + m); } };
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function bootCal(phone, store){
  const vc = new VirtualConsole(); const errs = [];
  vc.on("jsdomError", e => { const m = String(e && e.message || e).split("\n")[0]; if(!/supabase|Not implemented/i.test(m)) errs.push(m); });
  const st = Object.assign({}, store || {});
  const dom = new JSDOM(fs.readFileSync(path.join(ROOT, "calendar.html"), "utf8"), { runScripts: "dangerously", pretendToBeVisual: true, virtualConsole: vc,
    url: "https://theeconomicatlas.com/calendar",
    beforeParse(win){
      win.matchMedia = q => ({ matches: phone ? /max-width/.test(q) : /min-width/.test(q), addListener(){}, removeListener(){}, addEventListener(){}, removeEventListener(){} });
      Object.defineProperty(win, "localStorage", { configurable: true, value: { getItem: k => (k in st ? st[k] : null), setItem: (k, v) => { st[k] = String(v); }, removeItem: k => { delete st[k]; }, clear(){}, key: () => null, get length(){ return 0; } } });
      win.fetch = u => { const p = path.join(ROOT, String(u).split("/").pop().split("?")[0]);
        return fs.existsSync(p) ? Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(JSON.parse(fs.readFileSync(p, "utf8"))) }) : Promise.resolve({ ok: false, status: 404 }); };
    } });
  const win = dom.window;
  await new Promise(r => win.addEventListener("load", r, { once: true }));
  await sleep(900);
  if(phone){ win.eval(fs.readFileSync(path.join(ROOT, "mobile.js"), "utf8")); await sleep(100); }
  return { win, doc: win.document, errs, st };
}

(async () => {
  /* ---------- Compare desktop ---------- */
  { const { win, doc, errs } = await bootCompare({ desktop: true, noMobile: true });
    const api = win.EATLAS_COMPARE, $ = s => doc.querySelector(s);
    ok(errs.length === 0, "compare desktop: no page errors: " + errs.join("; "));
    let asked = 0; win.EATLAS_OPEN_AUTH_MODAL = () => asked++;
    api.setSelected(["UK", "US", "Germany", "Japan"]); await sleep(200);
    api.toggleCountry("France"); await sleep(100);
    ok(asked === 0, "compare desktop: a 5th country no longer jumps to the log-in form");
    ok(!$("#countryModal").hidden && !$("#cmpCapWarn").hidden && $("#cmpCapWarn").classList.contains("flag"), "the country picker opens with the free-limit card flagged");
    ok(api.getSelected().indexOf("France") === -1, "the 5th country is not added");
    ok(/Compare all \d+ countries/.test($("#cmpCapWarn").textContent) && /Sign up free/.test($("#cmpCapWarn .cap-signup").textContent) && /Log in/.test($("#cmpCapWarn .cap-login").textContent), "card: headline, Sign up free, Log in");
    const m = $("#cmpCapMeter");
    ok(!m.hidden && m.classList.contains("full") && /4 of 4 free countries used/.test(m.textContent) && m.querySelectorAll(".cap-slots i.on").length === 4, "meter: 4 of 4, full");
    const items = [...doc.querySelectorAll("#pickerRegions .picker-item")];
    const off = items.filter(i => !i.classList.contains("active"));
    ok(off.length > 0 && off.every(i => i.classList.contains("lk") && i.querySelector(".cap-lock")), "every unpicked country shows a padlock");
    ok(items.filter(i => i.classList.contains("active")).every(i => !i.classList.contains("lk")), "picked countries are not locked");
    // tick a locked one inside the picker
    $("#cmpCapWarn").classList.remove("flag");
    const fr = items.find(i => i.dataset.country === "France"); const inp = fr.querySelector("input"); inp.checked = true; inp.dispatchEvent(new win.Event("change", { bubbles: true })); await sleep(100);
    ok(asked === 0 && api.getSelected().length === 4 && $("#cmpCapWarn").classList.contains("flag"), "ticking a locked country flags the card, adds nothing");
    // Select all keeps the 4 already picked
    $("#pickerSelectAll").click(); await sleep(150);
    ok(asked === 0 && api.getSelected().join() === "UK,US,Germany,Japan", "Select all logged out keeps the 4 already picked: " + api.getSelected());
    // below the cap: card and padlocks go
    $("#pickerClearAll").click(); await sleep(150);
    ok($("#cmpCapWarn").hidden && !doc.querySelector("#pickerRegions .picker-item.lk") && /0 of 4/.test(m.textContent), "below the cap: no card, no padlocks, meter 0 of 4");
    $("#pickerSelectAll").click(); await sleep(150);
    ok(api.getSelected().length === 4 && !$("#cmpCapWarn").hidden, "Select all from empty: 4 picked, card shown");
    $("#cmpCapWarn .cap-signup").click(); await sleep(50);
    ok(asked === 1 && $("#countryModal").hidden, "Sign up free closes the picker and opens sign up");
    api.toggleCountry("France"); await sleep(50);
    $("#cmpCapWarn .cap-login").click(); await sleep(50);
    ok(asked === 2 && $("#countryModal").hidden, "Log in does the same");
    // logged in: no meter, no cap
    win.EATLAS_PREFS = { isLoggedIn: () => true, set(){}, get(k, d){ return d; } };
    api.toggleCountry("France"); await sleep(150);
    ok(api.getSelected().indexOf("France") !== -1 && asked === 2, "logged in: a 5th country just adds");
    doc.querySelector("#countryModal").hidden = false;
    $("#pickerSelectAll").click(); await sleep(150);
    ok(api.getSelected().length === api.allCountries().length && $("#cmpCapMeter").hidden && $("#cmpCapWarn").hidden && !doc.querySelector("#pickerRegions .picker-item.lk"), "logged in: Select all takes every country, no meter or card");
    win.close(); }

  /* ---------- Calendar, desktop then phone ---------- */
  for(const phone of [false, true]){
    const tag = phone ? "calendar phone" : "calendar desktop";
    const { win, doc, errs, st } = await bootCal(phone);
    const $ = s => doc.querySelector(s), cal = win.EA_CAL;
    ok(errs.length === 0, tag + ": no page errors: " + errs.join("; "));
    ok(cal.maxCountries() === 3 && ["UK", "US", "Eurozone"].every(c => cal.tracked().indexOf(c) !== -1) && cal.tracked().length === 3, tag + ": logged out starts on 3 countries: " + cal.tracked());
    ok(/^3 of 3 free$/.test($("#calCountriesCount").textContent), tag + ": the Countries button says 3 of 3 free: " + $("#calCountriesCount").textContent);
    let asked = 0; win.EATLAS_OPEN_AUTH_MODAL = () => asked++;
    $("#calCountriesBtn").click(); await sleep(60);
    const m = $("#calCapMeter"), w = $("#calCapWarn");
    ok(!$("#calCountriesModal").hidden && !m.hidden && m.classList.contains("full") && /3 of 3 free countries used/.test(m.textContent), tag + ": meter 3 of 3, full");
    ok(!w.hidden && /Track all \d+ countries/.test(w.textContent) && /email alerts/.test(w.textContent), tag + ": card shown at the cap");
    const labs = [...doc.querySelectorAll("#ctpCountries label")];
    ok(labs.filter(l => !l.querySelector("input").checked).every(l => l.classList.contains("lk")) && labs.filter(l => l.querySelector("input").checked).every(l => !l.classList.contains("lk")), tag + ": padlocks on every untracked country only");
    // tick a locked one
    const lk = labs.find(l => l.classList.contains("lk")), li = lk.querySelector("input"), name = li.dataset.country;
    li.checked = true; li.dispatchEvent(new win.Event("change", { bubbles: true })); await sleep(60);
    ok(cal.tracked().indexOf(name) === -1 && !$('#ctpCountries input[data-country="' + name + '"]').checked && w.classList.contains("flag") && asked === 0, tag + ": a locked tick is undone, card flagged, no log-in forced");
    // All keeps the 3
    $("#calPickAll").click(); await sleep(60);
    ok(cal.tracked().length === 3 && asked === 0, tag + ": All keeps 3 logged out");
    // a group chip from empty fills the free slots only
    $("#calPickNone").click(); await sleep(60);
    ok(cal.tracked().length === 0 && w.hidden && !doc.querySelector("#ctpCountries label.lk") && /0 of 3/.test(m.textContent), tag + ": None: no card, no padlocks, 0 of 3");
    const g7 = [...doc.querySelectorAll("#ctpGroups button")].find(b => /G7/.test(b.textContent));
    g7.click(); await sleep(60);
    ok(cal.tracked().length === 3 && !w.hidden && w.classList.contains("flag"), tag + ": G7 logged out fills 3 and flags the card");
    ok(JSON.parse(st.eatlas_calendar_tracked_countries || "[]").length === 3, tag + ": saved to this browser as 3");
    w.querySelector(".cap-signup").click(); await sleep(40);
    ok(asked === 1 && $("#calCountriesModal").hidden, tag + ": Sign up free closes the picker and opens sign up");
    // a stored list of more than 3 from before is cut to 3
    win.close();
    const b = await bootCal(phone, { eatlas_calendar_tracked_countries: JSON.stringify(["UK", "US", "Japan", "Canada", "Germany"]) });
    ok(b.win.EA_CAL.tracked().length === 3, tag + ": an older 5-country browser list loads as 3: " + b.win.EA_CAL.tracked());
    // logged in: unlimited, saved selection restored once the account check settles
    b.win.EATLAS_PREFS = Object.assign({}, b.win.EATLAS_PREFS, { isLoggedIn: () => true, get: (k, d) => k === "calendar_tracked_countries" ? ["UK", "US", "Japan", "Canada", "Germany", "France"] : d, set(){} });
    b.win.EA_CAL.reloadTracked();
    ok(b.win.EA_CAL.tracked().length === 6 && b.win.EA_CAL.maxCountries() > 3, tag + ": logged in: the account's 6 countries load, no cap");
    b.doc.querySelector("#calCountriesBtn").click(); await sleep(60);
    ok(b.doc.querySelector("#calCapMeter").hidden && b.doc.querySelector("#calCapWarn").hidden && !b.doc.querySelector("#ctpCountries label.lk"), tag + ": logged in: no meter, card or padlocks");
    b.doc.querySelector("#calPickAll").click(); await sleep(60);
    ok(b.win.EA_CAL.tracked().length > 40, tag + ": logged in: All tracks every country (" + b.win.EA_CAL.tracked().length + ")");
    ok(!/free/.test(b.doc.querySelector("#calCountriesCount").textContent), tag + ": logged in count has no free label");
    b.win.close();
  }
  { const CAL = fs.readFileSync(path.join(ROOT, "calendar.html"), "utf8");
    ok(/EATLAS_PREFS\.onSettled\(reloadTracked\)/.test(CAL), "calendar re-reads the tracked lists once the account check settles"); }
  { const ST = fs.readFileSync(path.join(ROOT, "style.css"), "utf8");
    ok(/\.cap-warn\.flag\{animation:capShake/.test(ST) && /prefers-reduced-motion:reduce\)\{ \.cap-warn\.flag\{animation:capPulse/.test(ST), "card shakes, or pulses for reduced motion"); }
  console.log("test_free_caps: " + (checks - failures) + " ok, " + failures + " failed");
  process.exit(failures ? 1 : 0);
})().catch(e => { console.log("  FAIL  crashed: " + e.stack); console.log("test_free_caps: " + (checks - failures) + " ok, " + (failures + 1) + " failed"); process.exit(1); });
