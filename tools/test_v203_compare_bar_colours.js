#!/usr/bin/env node
/* v2.0.3 Compare, Customise & export: the Bar colours choice above 10 countries (One colour or Country colours).
 * Run: NODE_PATH=/tmp/node_modules node tools/test_v203_compare_bar_colours.js */
const boot = require("./compare_harness");
let checks = 0, failures = 0;
const ok = (c, m) => { checks++; if(!c){ failures++; console.log("  FAIL  " + m); } };
(async () => {
  const { win, doc, errs } = await boot({ desktop: true, noMobile: true });
  ok(errs.length === 0, "no page errors: " + errs.join("; "));
  const C = win.EATLAS_COMPARE.getCountryColor;
  const names = ["UK","US","Germany","France","Italy","Spain","Japan","Canada","Australia","India","Colombia","Mexico"];
  const open = n => win.EATLAS_OPEN_CUSTOMIZE_SNAPSHOT(names.slice(0, n).map((c, i) => ({ country: c, value: i + 1, color: C(c) })), "T", "", v => String(v), "bond_yield_10y_snapshot");
  const fills = () => new Set([...doc.getElementById("czPreviewBox").innerHTML.matchAll(/<rect x="(?!0")[^"]+" y="[^"]+" width="[^"]+" height="[^"]+" fill="([^"]+)"\/?>|<rect x='(?!0')[^']+' y='[^']+' width='[^']+' height='[^']+' fill='([^']+)'\/?>/g)].map(m => (m[1] || m[2]).toUpperCase()));
  const field = () => doc.getElementById("czManyBarColourField").style.display;
  open(12);
  ok(field() === "flex", "option shown for 12 countries");
  let f = fills();
  ok(f.size === 12, "default country colours (v2.0.8): " + f.size + " fills");
  ok(doc.getElementById("czCountryColorsPanel").style.display === "", "country colour picker shown");
  const sel = doc.getElementById("czManyBarColourSelect");
  sel.value = "one"; sel.dispatchEvent(new win.Event("change"));
  f = fills();
  ok(f.size === 1 && f.has("#1E4566"), "one colour, navy: " + [...f].join(" "));
  ok(doc.getElementById("czCountryColorsPanel").style.display === "none", "country colour picker hidden in one-colour mode");
  ok(!/ rx=/.test(doc.getElementById("czPreviewBox").innerHTML.match(/<rect x=.(?!0)[^>]*>/g).join("")), "bars are square");
  open(6);
  ok(field() === "none", "option hidden for 6 countries");
  ok(fills().size === 6, "6 countries keep their colours");
  console.log(`test_v203_compare_bar_colours: ${checks} checks, ${failures} failures`);
  process.exit(failures ? 1 : 0);
})().catch(e => { console.log("ERROR " + e.stack); process.exit(1); });
