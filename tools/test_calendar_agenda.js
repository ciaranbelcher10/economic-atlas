#!/usr/bin/env node
/* v1.9.70 phone calendar: compact month grid with dots + full agenda rows.
 * Every event in the viewed month must appear (no "+N more" capping, no
 * "full list on desktop"), dots match events, tap targets >= 44px, phone-scoped.
 * Run: NODE_PATH=/tmp/node_modules node tools/test_calendar_agenda.js */
const fs = require("fs"), path = require("path");
const ROOT = path.resolve(__dirname, "..");
let checks = 0, failures = 0;
const ok = (c, m) => { checks++; if(!c){ failures++; console.log("  FAIL  " + m); } };
const { JSDOM, VirtualConsole } = require("jsdom");
const MOBILE_JS = fs.readFileSync(path.join(ROOT, "mobile.js"), "utf8");
const MOBILE_CSS = fs.readFileSync(path.join(ROOT, "mobile.css"), "utf8");
const CAL = fs.readFileSync(path.join(ROOT, "calendar.html"), "utf8");

async function boot(){
  const vc = new VirtualConsole();
  const dom = new JSDOM(CAL, { runScripts: "dangerously", pretendToBeVisual: true, virtualConsole: vc,
    url: "https://theeconomicatlas.com/calendar",
    beforeParse(win){
      win.matchMedia = () => ({ matches: true, addListener(){}, removeListener(){}, addEventListener(){}, removeEventListener(){} });
      win.fetch = u => { const p = path.join(ROOT, String(u).split("/").pop().split("?")[0]);
        return fs.existsSync(p) ? Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(JSON.parse(fs.readFileSync(p, "utf8"))) }) : Promise.resolve({ ok: false, status: 404 }); };
    } });
  const win = dom.window;
  await new Promise(r => win.addEventListener("load", r, { once: true }));
  await new Promise(r => setTimeout(r, 900));
  win.eval(MOBILE_JS);
  await new Promise(r => setTimeout(r, 100));
  return win;
}

(async () => {
  const win = await boot(), doc = win.document;
  ok(win.EA_CAL && typeof win.EA_CAL.monthDays === "function", "calendar.html exposes EA_CAL.monthDays");
  if(!win.EA_CAL){ console.log(`test_calendar_agenda: ${checks - failures} ok, ${failures} failed`); process.exit(1); }
  // Visit several months so at least one has a busy day (> 3 events, the old desktop cap).
  let busySeen = false, monthsWithEvents = 0;
  for(let step = 0; step < 4; step++){
    if(step) { doc.getElementById("calNextMonth").click(); await new Promise(r => setTimeout(r, 30)); }
    const days = win.EA_CAL.monthDays();
    const total = days.reduce((a, d) => a + d.events.length, 0);
    if(total) monthsWithEvents++;
    const rows = doc.querySelectorAll("#calAgenda .cal-ag-row");
    ok(rows.length === total, `month ${step}: agenda rows (${rows.length}) == events (${total})`);
    const mm = doc.querySelectorAll("#calMiniMonth .cal-mm-day");
    ok(mm.length === days.length, `month ${step}: mini grid has one cell per day`);
    days.forEach((d, i) => {
      const cell = mm[i]; if(!cell) return;
      const dots = cell.querySelectorAll(".dots i").length, plus = !!cell.querySelector(".dots b");
      ok(dots === Math.min(4, d.events.length), `month ${step} day ${d.day}: dots ${dots} vs ${d.events.length} events`);
      ok(plus === d.events.length > 4, `month ${step} day ${d.day}: "+" marker iff more than 4`);
      if(d.events.length > 3) busySeen = true;
      if(d.events.length){
        const sec = doc.getElementById("calAgDay" + d.day);
        ok(sec && sec.querySelectorAll(".cal-ag-row").length === d.events.length, `month ${step} day ${d.day}: agenda section lists all events`);
      }
    });
    ok(!/full list on desktop|\+\d+ more/i.test(doc.getElementById("calAgenda").textContent), `month ${step}: no hiding text in agenda`);
  }
  ok(monthsWithEvents > 0, "fixture has events in at least one month");
  if(!busySeen) console.log("  note: no day with more than 3 events in the 4 months scanned");

  // Tap a day with events: agenda section gets picked.
  doc.getElementById("calTodayBtn") && doc.getElementById("calTodayBtn").click();
  await new Promise(r => setTimeout(r, 30));
  const btn = doc.querySelector("#calMiniMonth .cal-mm-day.has-ev");
  if(btn){
    btn.click();
    const sec = doc.getElementById("calAgDay" + btn.dataset.day);
    ok(sec && sec.classList.contains("is-picked"), "tapping a day highlights its agenda section");
    ok(btn.classList.contains("is-picked"), "tapped day is marked");
  }
  // Tap a row: event modal opens.
  const row = doc.querySelector("#calAgenda .cal-ag-row");
  if(row){ row.click(); const m = doc.getElementById("calEventModal"); ok(m && !m.hidden, "tapping a row opens event detail"); }
  const empty = doc.querySelector("#calMiniMonth .cal-mm-day:not(.has-ev)");
  if(empty) ok(empty.disabled, "empty days are not tappable");

  // CSS: phone-scoped, 44px targets, no fixed widths.
  const start = MOBILE_CSS.indexOf("@media (max-width:760px){", 140);
  const idx = MOBILE_CSS.indexOf("#calMiniMonth{");
  ok(start !== -1 && idx > start, "calendar rules inside the phone media block");
  const rule = sel => { const m = MOBILE_CSS.match(new RegExp(sel.replace(/[.#]/g, "\\$&") + "\\{([^}]*)\\}")); return m ? m[1] : ""; };
  ok(/min-height:\s*44px/.test(rule(".cal-mm-day")), ".cal-mm-day min-height 44px");
  ok(/min-height:\s*44px/.test(rule(".cal-ag-row")), ".cal-ag-row min-height 44px");
  ok(/minmax\(0,1fr\)/.test(rule(".cal-mm-dow, .cal-mm-grid")), "mini grid columns can shrink (no overflow)");
  ok(!/width:\s*\d{3,}px/.test(MOBILE_CSS.slice(idx, MOBILE_CSS.indexOf("7. CHARTMAKER"))), "no fixed widths >= 100px in calendar rules");
  ok(!/full list on desktop/.test(MOBILE_JS), "mobile.js has no 'full list on desktop' copy");
  ok(/mobile\.css\?v=18/.test(CAL) && /mobile\.js\?v=20/.test(CAL), "calendar.html on mobile.css v18 / mobile.js v20");

  console.log(`test_calendar_agenda: ${checks - failures} ok, ${failures} failed`);
  process.exit(failures ? 1 : 0);
})();
