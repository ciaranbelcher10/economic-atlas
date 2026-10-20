#!/usr/bin/env node
/*
 * No-invented-data gate (v1.9.2). Until v1.9.1 this file checked that every country page's
 * sampleData() fallback ran; that fallback drew invented figures under real series codes when
 * the data file failed to load, so it was removed and this gate now enforces the opposite:
 * nothing on a page may stand in for published data.
 *
 * Every country page (any page that loads data-XX.json and has the #loadFail notice):
 *   - no sampleData(), no "sample:true", no data.sample badge code;
 *   - exactly one #loadFail notice, hidden by default, and the data fetch's .catch reveals it;
 *   - BEHAVIOUR (jsdom): with every data-*.json fetch failing, the notice is shown;
 *   - no "illustrative" wording anywhere (v1.9.3: the last four UK modules were cleaned up).
 * uk.html's MPC votes, age grid, inactivity reasons and spending modules: no fallback lists, and
 *   BEHAVIOUR (jsdom): with their data files unavailable, each shows its own "couldn't be loaded" line.
 * Every page with a trade-partner module:
 *   - FALLBACK_PARTNERS is empty, the old placeholder banner and captions are gone,
 *     the block is wrapped in #tpmBlock and falls back to "Not yet available for <name>.";
 *   - the radial hub shows this page's own code and the map's home code (UK_ID) is this
 *     country's ISO numeric code.
 *
 * Run: node tools/sampledata_gate.js    (needs jsdom: NODE_PATH=/tmp/node_modules)
 * Other tree (mutation checks): ATLAS_ROOT=/path node tools/sampledata_gate.js
 */
const fs = require("fs"), path = require("path");
const ROOT = process.env.ATLAS_ROOT ? path.resolve(process.env.ATLAS_ROOT) : path.resolve(__dirname, "..");
const {JSDOM, VirtualConsole} = require("jsdom");
let checks = 0, failures = 0;
const ok = (c, m) => { checks++; if (!c) { failures++; console.log("  FAIL  " + m); } };
const read = f => fs.readFileSync(path.join(ROOT, f), "utf8");
const ISO = {ar:32,au:36,at:40,be:56,br:76,bg:100,ca:124,cl:152,cn:156,co:170,hr:191,cy:196,cz:203,dk:208,eg:818,ee:233,fi:246,fr:250,de:276,gr:300,hk:344,hu:348,is:352,in:356,id:360,ie:372,il:376,it:380,jp:392,lv:428,lt:440,lu:442,my:458,mt:470,mx:484,ma:504,nl:528,nz:554,ng:566,no:578,pk:586,pe:604,ph:608,pl:616,pt:620,ro:642,sa:682,sg:702,sk:703,si:705,za:710,kr:410,es:724,se:752,ch:756,tw:158,th:764,tr:792,uk:826,us:840,vn:704};
const UK_MODULES = {mpcLatest: "The MPC vote record", ageGrid: "The age breakdown",
  reasonLegend: "The breakdown of reasons for inactivity", cofogSecnote: "The spending breakdown"};

const pages = fs.readdirSync(ROOT).filter(f => /\.html$/.test(f) && /fetch\("data-[a-z]{2}\.json"/.test(read(f)));
ok(pages.length === 62, `expected 62 country pages, found ${pages.length}`);

for (const p of pages) {
  const s = read(p);
  ok(!/function sampleData\(/.test(s) && !/sample:true/.test(s) && !/data\.sample/.test(s), `${p}: still carries the illustrative sampleData fallback`);
  ok((s.match(/id="loadFail"/g) || []).length === 1, `${p}: needs exactly one #loadFail notice`);
  ok(/<div id="loadFail" role="alert" hidden /.test(s), `${p}: #loadFail must be hidden until a failure`);
  ok(/\.catch\(err=>\{[\s\S]{0,200}getElementById\("loadFail"\)[\s\S]{0,40}hidden=false/.test(s), `${p}: the data fetch's .catch must reveal #loadFail`);
  const ill = (s.match(/illustrative/gi) || []).length;
  ok(ill === 0, `${p}: ${ill} "illustrative" mention(s)`);
  if (p === "uk.html") for (const v of ["FALLBACK_MEETINGS", "REASON_FALLBACK", "COFOG_FALLBACK", "AGE_BANDS", "renderAgeGrid("])
    ok(!s.includes(v), `uk.html: ${v} is back (the UK modules must not carry stand-in figures)`);

  if (s.includes("FALLBACK_PARTNERS")) {
    const code = (s.match(/fetch\("data-([a-z]+)-trade-partners\.json"/) || [])[1];
    const name = (s.match(/<div class="tpm-head"><h3>([^<]*) goods trade: top partners<\/h3><\/div>/) || [])[1];
    ok(code && name, `${p}: trade module not recognised`);
    ok(/var FALLBACK_PARTNERS = \[\];\n/.test(s) && (s.match(/var FALLBACK_PARTNERS = /g) || []).length === 1, `${p}: FALLBACK_PARTNERS must be empty`);
    ok(!/id="tpmBanner"/.test(s), `${p}: placeholder trade banner still in the page`);
    ok(/<p class="tpm-ranksubtitle" id="tpmRankSubtitle"><\/p>/.test(s) && /<p class="tpm-covnote" id="tpmCovnote"><\/p>/.test(s), `${p}: static trade captions must be empty until live data fills them`);
    ok((s.match(/<div id="tpmBlock">/g) || []).length === 1, `${p}: trade block must be wrapped in #tpmBlock once`);
    ok(s.includes(`Not yet available for ${name}.</p>`) && /if\(!applyLivePartners\(livePayload\)\)\{/.test(s), `${p}: no "Not yet available for ${name}" branch`);
    const hub = (s.match(/hub\.append\("text"\)\.attr\("x", cx\)\.attr\("y", cy \+ 5\)\.text\("([A-Z]+)"\);/) || [])[1];
    ok(hub === (code === "uk" ? "UK" : (code || "").toUpperCase()), `${p}: trade hub labelled ${hub}, expected ${code === "uk" ? "UK" : (code || "").toUpperCase()}`);
    const uid = (s.match(/var UK_ID = "(\d+)";/) || [])[1];
    ok(ISO[code] !== undefined && Number(uid) === ISO[code], `${p}: map home code UK_ID ${uid}, expected ISO ${ISO[code]}`);
  }
}

// behaviour: data files fail -> the notice shows (all country pages, sequentially).
// A page that rethrows inside its own promise chain must fail its check, not kill the run.
process.on("unhandledRejection", () => {});
(async () => {
  for (const p of pages) {
    const vc = new VirtualConsole();
    const dom = new JSDOM(read(p), {runScripts: "dangerously", url: "https://example.test/" + p, virtualConsole: vc, pretendToBeVisual: true,
      beforeParse(w){
        w.fetch = (u) => /data-[a-z-]+\.json/.test(String(u)) ? Promise.reject(new Error("offline")) : new Promise(() => {});
        w.matchMedia = () => ({matches: false, addListener(){}, removeListener(){}, addEventListener(){}, removeEventListener(){}});
        w.scrollTo = () => {}; w.HTMLCanvasElement.prototype.getContext = () => null;
      }});
    await new Promise(r => setTimeout(r, 400));
    const lf = dom.window.document.getElementById("loadFail");
    ok(lf && !lf.hidden, `${p}: with the data file unavailable, the "couldn't load" notice does not appear`);
    ok(!/illustrative figures/i.test(dom.window.document.body.textContent), `${p}: shows illustrative figures when the data file is unavailable`);
    if (p === "uk.html") for (const [id, what] of Object.entries(UK_MODULES)) {
      const t = ((dom.window.document.getElementById(id) || {}).textContent || "");
      ok(t.includes(what + " couldn\u2019t be loaded"), `uk.html: with its data file unavailable, #${id} does not say "${what} couldn't be loaded"`);
    }
    dom.window.close();
  }
  console.log(`${pages.length} country pages, ${checks} checks, ${failures} failures`);
  process.exit(failures ? 1 : 0);
})();
