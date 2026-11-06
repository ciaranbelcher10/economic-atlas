#!/usr/bin/env node
/* v1.9.70/71 phone calendar: calendar-app month grid with a labelled chip per release + full agenda rows.
 * Every event in the viewed month must appear in the grid and the agenda (no "+N more", no
 * "full list on desktop"), chips match events, tap targets >= 44px, phone-scoped.
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
  // v1.9.90: logged out tracks 3 countries; these checks want the full calendar, so stand in a logged-in account
  win.EATLAS_PREFS = Object.assign({}, win.EATLAS_PREFS, { isLoggedIn: () => true, get: (k, d) => d, set(){} });
  win.EA_CAL.reloadTracked();
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
    const mm = doc.querySelectorAll("#calMiniMonth .cal-mm-day:not(.is-other)");
    ok(mm.length === days.length, `month ${step}: grid has one cell per day of the month`);
    const allCells = doc.querySelectorAll("#calMiniMonth .cal-mm-grid > .cal-mm-day").length;
    ok(allCells % 7 === 0, `month ${step}: grid fills whole weeks (${allCells} cells)`);
    ok(doc.querySelectorAll("#calMiniMonth .cal-mm-day.is-other .cal-mm-chip").length === 0, `month ${step}: no chips on other-month days`);
    days.forEach((d, i) => {
      const cell = mm[i]; if(!cell) return;
      ok(+cell.dataset.day === d.day, `month ${step}: cell ${i} is day ${d.day}`);
      const chips = [...cell.querySelectorAll(".cal-mm-chip")];
      ok(chips.length === d.events.length, `month ${step} day ${d.day}: chips ${chips.length} vs ${d.events.length} events`);
      chips.forEach((c, j) => {
        const e = d.events[j];
        ok(c.textContent.endsWith(" " + e.label) && /^[A-Z]{2,3} /.test(c.textContent), `month ${step} day ${d.day}: chip "${c.textContent}" = code + label`);
        ok(c.style.background !== "", `month ${step} day ${d.day}: chip coloured`);
      });
      ok(cell.classList.contains("is-sun") === (d.dow === 0), `month ${step} day ${d.day}: Sunday marking`);
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
  if(btn) ok(btn.getAttribute("role") === "button" && btn.tabIndex === 0, "event days are keyboard-reachable buttons");
  if(btn){
    btn.click();
    const sec = doc.getElementById("calAgDay" + btn.dataset.day);
    ok(sec && sec.classList.contains("is-picked"), "tapping a day highlights its agenda section");
    ok(btn.classList.contains("is-picked"), "tapped day is marked");
  }
  // Tap a row: event modal opens.
  const row = doc.querySelector("#calAgenda .cal-ag-row");
  if(row){ row.click(); const m = doc.getElementById("calEventModal"); ok(m && !m.hidden, "tapping a row opens event detail"); }
  // Every row opens its own event (check the last row, which an index slip would miss).
  const rowsNow = [...doc.querySelectorAll("#calAgenda .cal-ag-row")];
  const last = rowsNow[rowsNow.length - 1];
  if(last){
    last.click();
    const country = last.querySelector(".c").textContent;
    const shown = doc.querySelector("#calEventDetailBody .cal-detail-country");
    ok(shown && shown.textContent.indexOf(country) === 0, `last row opens its own event (${country})`);
  }
  const empty = doc.querySelector("#calMiniMonth .cal-mm-day:not(.has-ev):not(.is-other)");
  if(empty) ok(!empty.hasAttribute("role"), "empty days are not tappable");

  // CSS: phone-scoped, 44px targets, no fixed widths.
  const start = MOBILE_CSS.indexOf("@media (max-width:760px){", 140);
  const idx = MOBILE_CSS.indexOf("#calMiniMonth{");
  ok(start !== -1 && idx > start, "calendar rules inside the phone media block");
  const rule = sel => { const m = MOBILE_CSS.match(new RegExp(sel.replace(/[.#]/g, "\\$&") + "\\{([^}]*)\\}")); return m ? m[1] : ""; };
  ok(/min-height:\s*(4[4-9]|[5-9]\d)px/.test(rule(".cal-mm-day")), ".cal-mm-day min-height >= 44px");
  ok(/pointer-events:\s*none/.test(rule(".cal-mm-chip")), "chips are labels, the whole day cell is the tap target");
  ok(!/\+\d|more/.test([...doc.querySelectorAll("#calMiniMonth .cal-mm-chip")].map(c=>c.textContent).join("|")), "no '+N more' chips");
  ok(/min-height:\s*44px/.test(rule(".cal-ag-row")), ".cal-ag-row min-height 44px");
  ok(/minmax\(0,1fr\)/.test(rule(".cal-mm-dow, .cal-mm-grid")), "mini grid columns can shrink (no overflow)");
  ok(!/width:\s*\d{3,}px/.test(MOBILE_CSS.slice(idx, MOBILE_CSS.indexOf("7. CHARTMAKER"))), "no fixed widths >= 100px in calendar rules");
  ok(!/full list on desktop/.test(MOBILE_JS), "mobile.js has no 'full list on desktop' copy");
  { const cv = +(CAL.match(/mobile\.css\?v=(\d+)/) || [0, 0])[1], jv = +(CAL.match(/mobile\.js\?v=(\d+)/) || [0, 0])[1];
    ok(cv >= 19 && jv >= 21, `calendar.html on mobile.css >= v19 / mobile.js >= v21 (v${cv} / v${jv})`); }

  console.log(`test_calendar_agenda: ${checks - failures} ok, ${failures} failed`);
  process.exit(failures ? 1 : 0);
})();
