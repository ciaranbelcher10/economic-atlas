// v2.0.21: a plain wheel over a map scrolls the page (no zoom, hint shown); Ctrl/Cmd + wheel zooms.
// Runs the helper exactly as migrate_v221.py injects it, against real d3 in jsdom, on every page.
// NODE_PATH=/tmp/node_modules node tools/test_v221_wheel.js
const fs = require("fs"), path = require("path"), { JSDOM } = require("jsdom");
const ROOT = path.resolve(__dirname, "..");
const d3src = fs.readFileSync(path.join(path.dirname(require.resolve("d3")), "..", "dist", "d3.min.js"), "utf8");
let fail = 0, n = 0;
const ok = (c, m) => { n++; if (!c) { fail++; console.log("  FAIL " + m); } };
const pages = fs.readdirSync(ROOT).filter(f => f.endsWith(".html") && fs.readFileSync(path.join(ROOT, f), "utf8").includes("d3.zoom("));
for (const f of pages) {
  const html = fs.readFileSync(path.join(ROOT, f), "utf8");
  const helper = (html.match(/<script>\n\/\* v2\.0\.21 wheel \*\/[\s\S]*?<\/script>/) || [""])[0];
  ok(helper, `${f}: no wheel helper`);
  ok(!/d3\.zoom\(\)(?!\.filter\(eaWheelFilter\))/.test(html), `${f}: a d3.zoom() without the wheel filter`);
  ok(!/wheel:\s?\{\s?enabled:\s?true\s?\}/.test(html), `${f}: a chart zooms on a plain wheel`);
  if (!helper) continue;
  const dom = new JSDOM(`<div id="box"><svg id="m" width="960" height="500"><g></g></svg><span class="zoomhint">x</span></div>`,
                        { runScripts: "outside-only", pretendToBeVisual: true });
  const w = dom.window;
  w.matchMedia = () => ({ matches: false });
  w.eval(d3src);
  w.eval(helper.replace(/^<script>|<\/script>$/g, ""));
  w.document.dispatchEvent(new w.Event("DOMContentLoaded"));
  w.eval(`var k=1; var z=d3.zoom().filter(eaWheelFilter).extent([[0,0],[960,500]]).scaleExtent([1,8]).on("zoom",function(e){k=e.transform.k;});
          d3.select("#m").call(z);`);
  const svg = w.document.getElementById("m");
  const wheel = (o) => { const e = new w.WheelEvent("wheel", Object.assign({ deltaY: -40, bubbles: true, cancelable: true, clientX: 100, clientY: 100 }, o)); svg.dispatchEvent(e); return e; };
  const e1 = wheel({});
  ok(w.eval("k") === 1, `${f}: plain wheel zoomed the map`);
  ok(!e1.defaultPrevented, `${f}: plain wheel was blocked (page would not scroll)`);
  ok(w.document.querySelector(".ea-wheelhint") && w.document.querySelector(".ea-wheelhint").style.opacity === "1", `${f}: no hint on plain wheel`);
  wheel({ ctrlKey: true });
  ok(w.eval("k") > 1, `${f}: Ctrl + wheel (and trackpad pinch) did not zoom`);
  const k2 = w.eval("k"); wheel({ metaKey: true });
  ok(w.eval("k") > k2, `${f}: Command + wheel did not zoom`);
  ok(/Ctrl \+ scroll or pinch to zoom/.test(w.document.querySelector(".zoomhint").textContent), `${f}: map hint text not set`);
}
console.log(`test_v221_wheel: ${pages.length} pages, ${n} checks, ${fail} failures`);
process.exit(fail ? 1 : 0);
