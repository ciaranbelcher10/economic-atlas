#!/usr/bin/env node
/* v2.0.16: Compare PPP button. NODE_PATH=/tmp/node_modules node tools/test_v216_compare_ppp.js */
const boot = require("./compare_harness");
let checks = 0, failures = 0; const ok = (c, m) => { checks++; if(!c){ failures++; console.log("  FAIL  " + m); } };
(async () => {
  const { win, doc, errs } = await boot({ desktop: true, noMobile: true, transform: h => h.replace("function pppOn(concept){", "window.__cE = function(js){ return eval(js); };\nfunction pppOn(concept){") });
  const E = js => win.__cE(js);
  E(`REGISTRY["UK"].ppp = {points: [["2023", 0.672], ["2024", 0.675]]}; REGISTRY["US"].ppp = {points: [["2023", 1], ["2024", 1]]};`);
  E(`selected.length = 0; selected.push("UK", "US"); if(visibleMetrics.indexOf("gdp_level") < 0) visibleMetrics.push("gdp_level");
     ensureCardTimeState("gdp_level").snapshotYear = 2024; renderAll();`);
  const card = [...doc.querySelectorAll(".cmp-card")].find(c => c.querySelector(".card-ppp-btn") && /GDP/.test(c.textContent) && c.querySelector(".card-percap-btn"));
  ok(!!card, "GDP card has a PPP button");
  const cpiCard = [...doc.querySelectorAll(".cmp-card")].find(c => /Inflation/i.test((c.querySelector("h3,.card-title")||{}).textContent || ""));
  ok(!cpiCard || !cpiCard.querySelector(".card-ppp-btn"), "no PPP button on inflation");
  const before = E(`getSnapshotValue("UK", "gdp_level", 2024).value`);
  card.querySelector(".card-ppp-btn").click();
  ok(E(`pppOn("gdp_level")`) === true, "PPP on for the card");
  const v = E(`getSnapshotValue("UK", "gdp_level", 2024)`);
  const lcu = E(`yearAggregate("UK", "gdp_level", 2024)`);
  ok(v && Math.abs(v.value - lcu.value * win.__cE("scaleOf")(lcu.unit) / 1e6 / 0.675) < 0.02, "UK 2024 in Int$m at the 2024 factor (" + (v && v.value) + " vs market " + before + ")");
  ok(E(`cardUnit("gdp_level")`) === "Int$m" && /^Int\$/.test(E(`curFmt(4300000, "Int$m", 1)`)), "card unit and format in Int$: " + E(`curFmt(4300000, "Int$m", 1)`));
  ok(E(`getSnapshotValue("UK", "gdp_level", 2025)`) == null && /PPP conversion factor for 2025/.test(E(`noDataReason("UK", "gdp_level", 2025)`)), "2025 left out and explained: " + E(`noDataReason("UK", "gdp_level", 2025)`));
  card.querySelector(".card-percap-btn").click();
  ok(card.querySelector(".card-ppp-btn").classList.contains("fx-dollar-pc") && card.querySelector(".card-percap-btn").classList.contains("fx-dollar-pc"), "PPP + per capita: both buttons purple");
  const pp = E(`getSnapshotValue("UK", "gdp_level", 2024)`);
  ok(pp && pp.perPerson && pp.value * 1e6 > 40000 && pp.value * 1e6 < 80000, "Int$ per person plausible: " + (pp && pp.value * 1e6));
  ok(/\(PPP\)/.test(card.textContent), "title says PPP");
  ok(!errs.length, "no page errors: " + errs.join(" | "));
  console.log(`test_v216_compare_ppp: ${checks} checks, ${failures} failures`); process.exit(failures ? 1 : 0);
})().catch(e => { console.log("ERROR " + e.stack); process.exit(1); });
