#!/usr/bin/env node
/* v1.9.94 Markets overhaul: jump bar, short charts with "Show all", region chips,
 * notes behind (i), one table at a time, find box, tap-a-row detail, phone columns.
 * Run: NODE_PATH=/tmp/node_modules node tools/test_markets_mobile.js */
const fs = require("fs"), path = require("path");
const { JSDOM, VirtualConsole } = require("jsdom");
const ROOT = path.resolve(__dirname, "..");
const HTML = fs.readFileSync(path.join(ROOT, "markets.html"), "utf8");
let checks = 0, failures = 0;
const ok = (c, m) => { checks++; if(!c){ failures++; console.log("  FAIL  " + m); } };

function boot(phone){
  const state = { phone };
  const dom = new JSDOM(HTML, { runScripts: "dangerously", pretendToBeVisual: true, virtualConsole: new VirtualConsole(), url: "https://theeconomicatlas.com/markets",
    beforeParse(w){
      w.fetch = (u) => { const f = path.join(ROOT, u.split("?")[0]);
        return Promise.resolve(fs.existsSync(f) ? { ok: true, json: () => Promise.resolve(JSON.parse(fs.readFileSync(f, "utf8"))) } : { ok: false, json: () => Promise.resolve(null) }); };
      w.matchMedia = (q) => ({ matches: /max-width:\s*760px/.test(q) ? state.phone : false, addListener(){}, removeListener(){}, addEventListener(){}, removeEventListener(){} });
      w.supabase = { createClient: () => ({ auth: { getSession: () => Promise.resolve({ data: { session: null } }), onAuthStateChange(){ return { data: { subscription: { unsubscribe(){} } } }; } } }) };
      w.HTMLElement.prototype.scrollIntoView = function(){ w.__scrolled = this; };
    } });
  const errors = []; dom.window.addEventListener("error", e => errors.push(e.message));
  return { w: dom.window, state, errors };
}
const wait = ms => new Promise(r => setTimeout(r, ms));

(async () => {
  const P = boot(true), D = boot(false);
  await wait(2500);
  for (const [tag, B] of [["phone", P], ["desktop", D]]) {
    const w = B.w, d = w.document, phone = tag === "phone";
    ok(B.errors.length === 0, tag + ": no script errors " + B.errors.join("; "));
    // jump bar
    const jb = [...d.querySelectorAll("#mkJump button")];
    ok(jb.length === 4 && jb.every(b => d.getElementById(b.dataset.to)), tag + ": jump bar has 4 buttons with targets");
    ok(!d.querySelector("#mkJump a"), tag + ": jump bar uses buttons, not links");
    jb[3].click();
    ok(w.__scrolled === d.getElementById("tables") && jb[3].classList.contains("on") && !jb[0].classList.contains("on"), tag + ": jump scrolls and marks its button");
    // scrollspy: section reading area is the top 40% of the screen, last button at page bottom
    { const tops = {"chart-yields": -900, "chart-fx": 300, "chart-daily": 1400, "tables": 2600};
      const orig = w.Element.prototype.getBoundingClientRect;
      w.Element.prototype.getBoundingClientRect = function(){ if(this.id === "mkJump") return {top:56,bottom:110,left:0,right:390,width:390,height:54}; if(tops[this.id] != null) return {top:tops[this.id],bottom:tops[this.id]+500,left:0,right:390,width:390,height:500}; return orig.call(this); };
      Object.defineProperty(d.documentElement, "scrollHeight", {configurable:true, value: 99999});
      w.innerHeight = 844; w.dispatchEvent(new w.Event("scroll")); await wait(60);
      ok(jb[1].classList.contains("on") && !jb[0].classList.contains("on"), tag + ": scrollspy marks Currencies once its card is in the top 40%");
      tops["chart-fx"] = 400; w.dispatchEvent(new w.Event("scroll")); await wait(60);
      ok(jb[0].classList.contains("on"), tag + ": scrollspy keeps Bonds while Currencies is lower down");
      Object.defineProperty(d.documentElement, "scrollHeight", {configurable:true, value: 844 + (w.scrollY || 0)});
      w.dispatchEvent(new w.Event("scroll")); await wait(60);
      ok(jb[3].classList.contains("on"), tag + ": scrollspy marks Tables at the bottom of the page");
      Object.defineProperty(d.documentElement, "scrollHeight", {configurable:true, value: 99999});
      w.Element.prototype.getBoundingClientRect = orig; }
    // yields chart
    const yRows = d.querySelectorAll("#tYields tbody tr").length;
    const vb = () => d.querySelector("#cYields svg").getAttribute("viewBox").split(" ")[2];
    ok(vb() === (phone ? "360" : "900"), tag + ": yields chart width " + vb());
    const rects = () => d.querySelectorAll("#cYields svg rect").length;
    const K = phone ? 5 : 10, N = 2 * K;
    ok(rects() === N, tag + ": yields open at " + N + " bars (" + rects() + ")");
    const gap = d.querySelector("#cYields .mk-gap");
    ok(gap && gap.textContent === (yRows - N) + " more in between", tag + ": gap row counts the hidden bars");
    const names = [...d.querySelectorAll("#cYields svg text")].filter(t => t.getAttribute("text-anchor") === "end").map(t => t.textContent);
    const tRows = [...d.querySelectorAll("#tYields tbody tr")].map(r => r.cells[0].textContent.trim());
    ok(names.slice(0, K).join() === tRows.slice(0, K).join() && names.slice(K).join() === tRows.slice(-K).join(), tag + ": shows the highest and lowest " + K + " in order");
    const tags = d.querySelectorAll("#cYields svg tspan").length;
    ok(phone ? tags < N : tags === N, tag + ": period tags " + (phone ? "only where they differ" : "on every bar") + " (" + tags + ")");
    const ym = d.getElementById("mkYMore");
    ok(!ym.hidden && ym.textContent === "Show all " + yRows && ym.getAttribute("aria-expanded") === "false", tag + ": show all button");
    ym.click();
    ok(rects() === yRows && !d.querySelector("#cYields .mk-gap") && ym.getAttribute("aria-expanded") === "true" && /^Show highest/.test(ym.textContent), tag + ": show all draws every bar");
    ym.click();
    ok(rects() === N, tag + ": show fewer returns to " + N);
    // region chips
    const chips = [...d.querySelectorAll("#mkYRegions button")];
    const REG = w.__mkRegion;
    ok(chips.length >= 4 && chips[0].textContent === "All " + yRows, tag + ": All chip counts every bar");
    const sum = chips.slice(1).reduce((a, c) => a + parseInt(c.textContent.match(/\d+$/)[0]), 0);
    ok(sum === yRows, tag + ": region counts add up (" + sum + "/" + yRows + ")");
    const eu = chips.find(c => c.dataset.region === "Europe"), euN = parseInt(eu.textContent.match(/\d+$/)[0]);
    eu.click();
    const shownNames = [...d.querySelectorAll("#cYields svg a title")].map(t => t.textContent.split(":")[0]);
    const nameToCc = {}; Object.keys(REG).forEach(cc => { const m = HTML.match(new RegExp("[{,]" + cc + ':\\["([^"]+)"')); if(m) nameToCc[m[1]] = cc; });
    ok(shownNames.length === (euN > N + 4 ? N : euN) && shownNames.every(n => REG[nameToCc[n]] === "Europe"), tag + ": Europe chip shows only Europe (" + shownNames.length + ")");
    ok(eu.getAttribute("aria-pressed") === "true" && chips[0].getAttribute("aria-pressed") === "false", tag + ": chip pressed state");
    const am = chips.find(c => c.dataset.region === "Americas"); am.click();
    ok(d.getElementById("mkYMore").hidden === (parseInt(am.textContent.match(/\d+$/)[0]) <= N + 4), tag + ": show all hidden for a short region");
    // v1.9.99: palette runs from darkest (highest) to lightest (lowest) within whichever countries are shown
    for (const c of chips) {
      c.click(); const fills = [...d.querySelectorAll("#cYields svg rect")].map(r => r.getAttribute("fill"));
      if (fills.length < 2) continue;
      ok(fills[0] === "#2E1E3B" && fills[fills.length - 1] === "#8AD9B1", tag + ": " + c.dataset.region + " palette spans darkest to lightest (" + fills[0] + " .. " + fills[fills.length - 1] + ")");
    }
    chips[0].click();
    const vlab = [...d.querySelectorAll("#cYields svg text")].find(t => /%$/.test(t.firstChild && t.firstChild.nodeValue || "") && t.getAttribute("font-weight") === "700");
    ok(vlab && vlab.getAttribute("paint-order") === "stroke" && vlab.getAttribute("stroke") === "var(--panel)", tag + ": yield value labels sit on the card colour");
    const flab = [...d.querySelectorAll("#cFx svg text")].find(t => /%$/.test(t.textContent) && t.getAttribute("font-weight") === "700");
    ok(flab && flab.getAttribute("paint-order") === "stroke", tag + ": currency value labels sit on the card colour");
    // fade class follows scroll position
    { const box = d.getElementById("mkYRegions");
      Object.defineProperty(box, "scrollWidth", {configurable: true, value: 600}); Object.defineProperty(box, "clientWidth", {configurable: true, value: 300});
      box.scrollLeft = 0; w.__mkEdge(box); const atStart = box.classList.contains("mk-end");
      box.scrollLeft = 300; w.__mkEdge(box); const atEnd = box.classList.contains("mk-end");
      ok(!atStart && atEnd, tag + ": chip row fade shows until scrolled to the end"); }
    // fx chart
    const fxRows = [...d.querySelectorAll("#tFx tbody tr")].filter(r => r.cells[5] && r.cells[5].textContent.trim() !== "n/a").length;
    const frects = () => d.querySelectorAll("#cFx svg rect").length;
    ok(frects() === 12 && d.querySelector("#cFx .mk-gap").textContent === (fxRows - 12) + " more in between", tag + ": currencies open at 6 gains and 6 falls");
    d.getElementById("mkFMore").click();
    ok(frects() === fxRows, tag + ": currencies show all");
    d.getElementById("mkFMore").click();
    ok(d.querySelector("#cDaily svg").getAttribute("viewBox").split(" ")[2] === (phone ? "360" : "520"), tag + ": daily chart sized");
    // notes behind (i)
    const notes = [...d.querySelectorAll(".mk-card .mk-note, .mk-sec .mk-note")];
    const ibs = [...d.querySelectorAll(".mk-i")];
    ok(notes.length === 9 && ibs.length === 9 && notes.every(n => n.hidden), tag + ": 9 notes start hidden behind 9 (i) buttons");
    ibs[0].click();
    ok(!d.getElementById(ibs[0].getAttribute("aria-controls")).hidden && ibs[0].getAttribute("aria-expanded") === "true", tag + ": (i) opens its note");
    ibs[0].click();
    ok(d.getElementById(ibs[0].getAttribute("aria-controls")).hidden, tag + ": (i) closes its note");
    // one table at a time
    const secs = ["yields","policy","yields-daily","yields-other","fx","fx-annual"];
    const visible = () => secs.filter(id => !d.getElementById(id).classList.contains("mk-off"));
    ok(visible().join() === "yields", tag + ": only 10-year yields shown at first");
    const tabs = [...d.querySelectorAll("#mkTabs button")];
    tabs[4].click();
    ok(visible().join() === "fx" && tabs[4].getAttribute("aria-pressed") === "true" && tabs[0].getAttribute("aria-pressed") === "false", tag + ": tab switches table");
    tabs[0].click();
    // find
    const find = d.getElementById("mkFind");
    const shownRows = () => [...d.querySelectorAll("#tYields tbody tr:not(.mk-det)")].filter(r => !r.classList.contains("mk-hide"));
    find.value = "ger"; find.dispatchEvent(new w.Event("input"));
    ok(shownRows().length >= 1 && shownRows().every(r => r.cells[0].textContent.toLowerCase().includes("ger")) && d.getElementById("mkNone").hidden, tag + ": find filters rows");
    d.querySelector("#tYields th").click();
    ok(shownRows().length >= 1 && shownRows().every(r => r.cells[0].textContent.toLowerCase().includes("ger")), tag + ": filter survives a sort");
    find.value = "zzzz"; find.dispatchEvent(new w.Event("input"));
    ok(shownRows().length === 0 && !d.getElementById("mkNone").hidden, tag + ": no-match message");
    find.value = ""; find.dispatchEvent(new w.Event("input"));
    ok(shownRows().length === yRows && d.getElementById("mkNone").hidden, tag + ": clearing find shows every row");
    // tap a row
    const tr = d.querySelector("#tYields tbody tr");
    tr.cells[1].click();
    const det = tr.nextElementSibling;
    ok(det && det.classList.contains("mk-det") && tr.getAttribute("aria-expanded") === "true", tag + ": tap opens a detail row");
    const heads = [...d.querySelectorAll("#tYields thead th")].map(t => t.textContent);
    const want = phone ? [2, 4, 5] : [5];
    const got = [...det.querySelectorAll("b")].map(b => b.textContent.replace(/:$/, ""));
    ok(got.join("|") === want.map(i => heads[i]).join("|"), tag + ": detail lists the hidden columns: " + got.join("|"));
    ok(det.textContent.includes(tr.cells[5].textContent.trim()), tag + ": detail carries the source");
    tr.cells[1].click();
    ok(!tr.nextElementSibling || !tr.nextElementSibling.classList.contains("mk-det"), tag + ": second tap closes it");
    tr.querySelector("a").dispatchEvent(new w.MouseEvent("click", { bubbles: true, cancelable: true }));
    ok(!tr.nextElementSibling || !tr.nextElementSibling.classList.contains("mk-det"), tag + ": tapping the country link does not open detail");
    tr.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    ok(tr.nextElementSibling && tr.nextElementSibling.classList.contains("mk-det") && tr.tabIndex === 0, tag + ": Enter opens detail");
    // column css
    const css = d.getElementById("mkColCss").textContent, PC = w.__mkPhoneCols;
    const [deskCss, phoneCss] = css.split("@media (max-width:760px){");
    const allOk = Object.keys(PC).every(id => { const n = d.querySelectorAll("#" + id + " thead th").length;
      const ph = [...Array(n).keys()].every(i => phoneCss.includes("#" + id + " th:nth-child(" + (i + 1) + ")") === !PC[id].includes(i));
      return ph && deskCss.includes("#" + id + " th:nth-child(" + n + ")") && (deskCss.match(new RegExp("#" + id + " th:nth-child", "g")) || []).length === 1; });
    ok(allOk, tag + ": column CSS hides source on desktop and the right columns on phones");
    ok(Object.keys(PC).every(id => PC[id][0] === 0 && PC[id].length === 3), tag + ": phones keep country plus two columns");
  }
  // switching phone to desktop redraws and closes detail rows
  { const w = P.w, d = w.document; P.state.phone = false; w.dispatchEvent(new w.Event("resize"));
    ok(d.querySelector("#cYields svg").getAttribute("viewBox").split(" ")[2] === "900" && !d.querySelector("tr.mk-det"), "resize: phone to desktop redraws and closes detail rows"); }
  // v1.9.95: jsdom has no layout, so guard the CSS that keeps the page one screen wide on phones
  // (a 1fr grid track grew to the chip rows' full width and the whole page zoomed out).
  ok(/\.mk-grid\{display:grid; grid-template-columns:minmax\(0,1fr\) minmax\(0,1fr\)/.test(HTML) && /max-width:820px\)\{\.mk-grid\{grid-template-columns:minmax\(0,1fr\);/.test(HTML), "grid tracks are minmax(0,1fr)");
  ok(/\.mk-grid > \*\{min-width:0;\}/.test(HTML), "grid items can shrink");
  ok(/html, body\{overflow-x:clip;\}/.test(HTML), "phones clip any stray horizontal overflow");
  ok(!/\.mk-scroll\{overflow:visible;\}/.test(HTML), "wide tables scroll inside their card");
  // copy rules
  const nd = HTML.slice(HTML.indexOf('<header class="mk-hero">'), HTML.indexOf('<section class="mk-sec" id="yields">'));
  ok(!/\u2014/.test(nd), "no em dashes in new copy");
  ok(!/<a [^>]*>[^<]*<\/a>/.test(nd.replace(/<script[\s\S]*?<\/script>/g, "")), "no text links in hero, jump bar or table bar");
    // v1.9.99 static phone guards (jsdom has no layout)
  { const PH = (HTML.match(/@media \(max-width:760px\)\{([\s\S]*?)\n\}/) || [])[1] || "";
    ok(/\.mk-tick svg\{display:none;\}/.test(PH), "phone: hero tiles drop the sparkline");
    ok(/\.mk-tick\{flex:0 0 112px;/.test(PH), "phone: hero tiles 112px wide");
    ok(/\.mk-hero h1\{font-size:19px;/.test(PH) && /\.mk-dt\{display:none;\} \.mk-ph\{display:inline;\}/.test(PH), "phone: short hero title and intro");
    ok(/\.mk-chips button\{min-height:34px;/.test(PH) && /\.mk-jump button\{min-height:36px;/.test(PH), "phone: shorter chips");
    ok(/mask-image:linear-gradient\(90deg,#000 calc\(100% - 28px\),transparent\)/.test(PH) && /\.mk-end\{-webkit-mask-image:none; mask-image:none;\}/.test(PH), "phone: chip rows fade at the right edge");
    ok(/\.mk-ph\{display:none;\}/.test(HTML.split("@media (max-width:760px)")[0]), "desktop: phone-only copy hidden");
    ok(/<h1>Bond yields and exchange rates<span class="mk-dt">, economy by economy<\/span><\/h1>/.test(HTML), "desktop keeps the full hero title"); }
console.log(checks + " checks, " + failures + " failures");
  process.exit(failures ? 1 : 0);
})();
