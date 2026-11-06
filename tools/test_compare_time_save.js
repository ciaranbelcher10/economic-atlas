#!/usr/bin/env node
/* v1.9.88 Compare: each card's mode (Point in time / Change over time) and year(s) are saved.
 *  - saved through EATLAS_PREFS key "compareCardTime" (account when logged in, this browser when not)
 *  - a year left on the newest available year saves as "latest" and follows new data
 *  - restored on load, clamped to the valid range; bad data ignored; removing a metric drops its entry
 * Run: NODE_PATH=/tmp/node_modules node tools/test_compare_time_save.js */
const boot = require("./compare_harness");
let checks = 0, failures = 0;
const ok = (c, m) => { checks++; if(!c){ failures++; console.log("  FAIL  " + m); } };
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  for(const desktop of [false, true]){
    const tag = desktop ? "desktop" : "phone";
    // 1. fresh visit: record what gets saved
    const { win, doc, errs } = await boot({ desktop, noMobile: desktop });
    const api = win.EATLAS_COMPARE;
    ok(errs.length === 0, tag + ": no page errors: " + errs.join("; "));
    const saves = [];
    win.EATLAS_PREFS = { isLoggedIn: () => false, set(k, v){ saves.push([k, JSON.parse(JSON.stringify(v))]); }, get(k, d){ return d; }, ready: Promise.resolve() };
    const k = api.getMetrics()[0], card = doc.querySelector('#chartGrid .metric-card');
    const max = api.maxYearFor(k);
    const last = () => { const s = saves.filter(x => x[0] === "compareCardTime"); return s.length ? s[s.length - 1][1] : null; };
    // move the slider back two years
    const snap = card.querySelector(".card-snapshot-slider");
    snap.value = max - 2; snap.dispatchEvent(new win.Event("input"));
    await sleep(150);
    snap.value = max - 3; snap.dispatchEvent(new win.Event("input"));
    await sleep(150);
    ok(!last(), tag + ": saving waits for the drag to settle");
    await sleep(500);
    ok(saves.filter(x => x[0] === "compareCardTime").length === 1, tag + ": one save per drag, not per step");
    ok(last() && last()[k] && last()[k].snapshotYear === max - 3 && last()[k].mode === "snapshot", tag + ": the year saved: " + JSON.stringify(last()));
    // switch to Change over time
    card.querySelector('.card-mode-switch .modebtn[data-mode="change"]').click(); await sleep(500);
    ok(last()[k].mode === "change", tag + ": the mode saved");
    ok(last()[k].changeEndYear === "latest", tag + ": an end year on the newest year saves as latest");
    const st = card.querySelector(".card-change-start-slider");
    st.value = max - 5; st.dispatchEvent(new win.Event("input")); await sleep(500);
    ok(last()[k].changeStartYear === max - 5, tag + ": the start year saved");
    // back to the newest year: saves as latest
    snap.value = max; snap.dispatchEvent(new win.Event("input")); await sleep(500);
    ok(last()[k].snapshotYear === "latest", tag + ": point in time on the newest year saves as latest");
    win.close();

    // 2. restore from a saved state (logged-out browser store)
    const saved = { unemployment: { mode: "change", snapshotYear: 2019, changeStartYear: 2012, changeEndYear: "latest" },
      cpi: { mode: "snapshot", snapshotYear: "latest", changeStartYear: 1800, changeEndYear: 99999 },
      not_a_metric: { mode: "change" }, gdp_growth: "junk" };
    // (the harness has no working prefs store, so load the saved state through the same function the
    //  page's prefs-ready step calls; a static check below pins that wiring)
    const b = await boot({ desktop, noMobile: desktop });
    const a2 = b.win.EATLAS_COMPARE;
    ["unemployment", "cpi", "gdp_growth"].forEach(m => { if(a2.getMetrics().indexOf(m) === -1) a2.addMetric(m); });
    await sleep(300);
    a2.restoreCardTime(saved); await sleep(300);
    ok(b.errs.length === 0, tag + " restore: no page errors: " + b.errs.join("; "));
    const u = a2.getCardTime("unemployment"), um = a2.maxYearFor("unemployment");
    ok(u && u.mode === "change" && u.changeStartYear === 2012 && u.changeEndYear === um && u.snapshotYear === 2019, tag + ": unemployment restored: " + JSON.stringify(u));
    const ucard = [...b.doc.querySelectorAll("#chartGrid .metric-card")].find(c => c.querySelector('.card-change-wrap') && !c.querySelector('.card-change-wrap').hidden);
    ok(!!ucard && +ucard.querySelector(".card-change-start-slider").value === 2012 && ucard.querySelector('.modebtn[data-mode="change"]').classList.contains("active"), tag + ": the restored card shows Change over time from 2012");
    const c = a2.getCardTime("cpi"), cm = a2.maxYearFor("cpi");
    ok(c && c.mode === "snapshot" && c.snapshotYear === cm && c.changeEndYear <= cm && c.changeStartYear > 1800, tag + ": latest resolves and silly years are clamped: " + JSON.stringify(c));
    const g = a2.getCardTime("gdp_growth");
    ok(g && g.mode === "snapshot" && g.snapshotYear === a2.maxYearFor("gdp_growth"), tag + ": a junk entry falls back to the default: " + JSON.stringify(g));
    // removing a metric drops its saved entry
    const saves2 = [];
    b.win.EATLAS_PREFS = { isLoggedIn: () => false, set(k, v){ saves2.push([k, JSON.parse(JSON.stringify(v))]); }, get(k, d){ return d; }, ready: Promise.resolve() };
    a2.removeMetric("cpi"); await sleep(500);
    const s2 = saves2.filter(x => x[0] === "compareCardTime").pop();
    ok(s2 && !("cpi" in s2[1]) && s2[1].unemployment && s2[1].unemployment.mode === "change", tag + ": removing a metric drops it from the saved state");
    b.win.close();
  }
  { const H = require("fs").readFileSync(require("path").resolve(__dirname, "..", "compare.html"), "utf8");
    const i = H.indexOf('restoreCardTimeState(window.EATLAS_PREFS.get("compareCardTime", null));'), r = H.indexOf("renderAll();", i), rd = H.lastIndexOf("EATLAS_PREFS.ready.then", i);
    ok(i > 0 && rd > 0 && i - rd < 4000 && r > i && r - i < 400, "on load the saved state is restored inside prefs-ready, before the first render"); }
  console.log("test_compare_time_save: " + (checks - failures) + " ok, " + failures + " failed");
  process.exit(failures ? 1 : 0);
})();
