// Markets page gate (v1.6.36; visuals v1.6.37; links and copy v1.6.38): runs markets.html in jsdom against the real
// data files and checks every table renders and no table mixes measures.
//   npm install jsdom --no-save; export NODE_PATH=$(pwd)/node_modules
//   node tools/test_markets.js        -> "N checks, 0 failures"
const fs = require("fs"), path = require("path");
const { JSDOM } = require("jsdom");
const root = path.join(__dirname, "..");
const html = fs.readFileSync(path.join(root, "markets.html"), "utf8");
let checks = 0, fails = 0;
function check(name, ok, detail){ checks++; if(!ok){ fails++; console.log("FAIL", name, detail || ""); } }
const dom = new JSDOM(html, { runScripts: "dangerously", url: "https://theeconomicatlas.com/markets",
  beforeParse(w){
    w.fetch = (u) => { const f = path.join(root, u.split("?")[0]);
      return Promise.resolve(fs.existsSync(f) ? { ok: true, json: () => Promise.resolve(JSON.parse(fs.readFileSync(f, "utf8"))) } : { ok: false, json: () => Promise.resolve(null) }); };
    w.matchMedia = () => ({ matches: false, addListener(){}, removeListener(){} });
    w.supabase = { createClient: () => ({ auth: { getSession: () => Promise.resolve({ data: { session: null } }), onAuthStateChange(){ return { data: { subscription: { unsubscribe(){} } } }; } } }) };
  } });
const errors = []; dom.window.addEventListener("error", e => errors.push(e.message));
setTimeout(() => {
  const d = dom.window.document;
  const rows = id => [...d.querySelectorAll("#" + id + " tbody tr")].map(r => [...r.cells].map(c => c.textContent.trim()));
  const load = f => JSON.parse(fs.readFileSync(path.join(root, f), "utf8"));
  const y = rows("tYields"), dl = rows("tDaily"), o = rows("tOther"), fx = rows("tFx"), fa = rows("tFxA");
  check("no script errors", errors.length === 0, errors.join("; "));
  // 1. period-average yields: exactly the countries carrying bond_yield_10y
  const files = fs.readdirSync(root).filter(f => /^data(-[a-z]{2})?\.json$/.test(f));
  const want = files.filter(f => { const s = load(f).series || {}; return s.bond_yield_10y && (s.bond_yield_10y.points || []).length >= 2; }).length;
  check("yields table has every bond_yield_10y country", y.length === want, `${y.length} vs ${want}`);
  check("yields sorted high to low", y.every((r, i) => i === 0 || parseFloat(y[i-1][1].replace("\u2212","-")) >= parseFloat(r[1].replace("\u2212","-"))));
  const ez = y.find(r => r[0] === "Eurozone");
  check("Eurozone end-of-month basis shown", !ez || /end of month/.test(ez[2]), ez && ez[2]);
  // 2. daily table only official daily 10-year series
  const dailyWant = ["uk","us","ca","jp"].filter(c => { try { return load(`data-bond-${c}.json`).key === "bond_yield_10y"; } catch(e){ return false; } }).length;
  check("daily table = daily bond_yield_10y files", dl.length === dailyWant, `${dl.length} vs ${dailyWant}`);
  check("daily rows dated to the day", dl.every(r => /^\d{1,2} [A-Z][a-z]{2} \d{4}$/.test(r[2])));
  // 3. alternative measures never in the 10-year tables
  const altNames = o.map(r => r[0]);
  check("other-measures table has EZ par + SG/MA/TH", ["Eurozone","Singapore","Morocco","Thailand"].every(n => altNames.includes(n)), altNames.join(","));
  check("SG/MA/TH not in 10-year tables", !y.concat(dl).some(r => ["Singapore","Morocco","Thailand"].includes(r[0])));
  check("other rows name their measure", o.every(r => r[1].length > 3));
  // 4. FX: euro shown once, US dollar not a row, daily vs annual kept apart
  check("euro shown once", fx.filter(r => /^Euro\b/.test(r[0])).length === 1);
  check("no euro-member duplicates", !fx.concat(fa).some(r => /\((Austria|France|Germany|Ireland|Italy|Netherlands|Spain)\)/.test(r[0])));
  check("no US dollar row", !fx.concat(fa).some(r => /\(US\)/.test(r[0])));
  check("daily FX rows dated to the day", fx.every(r => /^\d{1,2} [A-Z][a-z]{2} \d{4}$/.test(r[2])));
  check("annual FX rows dated by year", fa.length > 0 && fa.every(r => /^\d{4}$/.test(r[2])));
  check("every FX rate in US$ per home unit", fx.concat(fa).every(r => /^\$[\d.]+ per /.test(r[1])));
  check("FX tables non-empty", fx.length >= 10 && fa.length >= 5, `${fx.length}/${fa.length}`);
  // 5. visuals agree with the tables row for row (v1.6.37)
  const ticks = d.querySelectorAll(".mk-tick");
  check("ticker has at least 5 cards", ticks.length >= 5, ticks.length);
  check("every ticker card dated", [...ticks].every(t => /\d{4}/.test(t.querySelector(".d").textContent)));
  const cy = d.querySelectorAll("#cYields svg rect").length;
  check("yield bars = yield table rows", cy === y.length, `${cy} vs ${y.length}`);
  check("Eurozone bar shows end of month", !ez || /end of month/.test([...d.querySelectorAll("#cYields text")].map(t => t.textContent).join(" ")));
  const fxWith = fx.filter(r => r[5] !== "n/a").length, cf = d.querySelectorAll("#cFx svg rect").length;
  check("currency bars = daily FX rows with a 1-year change", cf === fxWith, `${cf} vs ${fxWith}`);
  check("no annual-only currency in the scoreboard", !fa.some(r => [...d.querySelectorAll("#cFx svg title")].some(t => t.textContent.startsWith(r[0] + ":"))));
  const cl = d.querySelectorAll("#cDaily svg path").length;
  check("one daily line per daily yield row", cl === dl.length, `${cl} vs ${dl.length}`);
  check("charts carry text alternatives", ["cYields","cFx","cDaily"].every(id => { const s = d.querySelector("#" + id + " svg"); return s && s.getAttribute("role") === "img" && (s.getAttribute("aria-label") || "").length > 20; }));
  // 7. every country item links to an existing country page (v1.6.38)
  const pageOk = href => fs.existsSync(path.join(root, href.replace(/^\//, "") + ".html"));
  const linkSets = {
    ticker: [...d.querySelectorAll(".mk-tick")].map(a => a.getAttribute("href")),
    yieldBars: [...d.querySelectorAll("#cYields svg rect")].map(r => r.closest("a") && r.closest("a").getAttribute("href")),
    fxBars: [...d.querySelectorAll("#cFx svg rect")].map(r => r.closest("a") && r.closest("a").getAttribute("href")),
    dailyLabels: [...d.querySelectorAll("#cDaily svg text")].filter(t => /%$/.test(t.textContent)).map(t => t.closest("a") && t.closest("a").getAttribute("href")),
    tableRows: ["tYields","tDaily","tOther","tFx","tFxA"].flatMap(id => [...d.querySelectorAll("#" + id + " tbody tr")].map(tr => { const a = tr.querySelector("td a"); return a && a.getAttribute("href"); }))
  };
  for (const [name, hrefs] of Object.entries(linkSets)) {
    check(name + " all linked", hrefs.length > 0 && hrefs.every(Boolean), hrefs.filter(h => !h).length + " unlinked of " + hrefs.length);
    check(name + " links resolve to pages", hrefs.filter(Boolean).every(pageOk), hrefs.filter(h => h && !pageOk(h)).join(","));
  }
  // 8. plain copy: no stock AI phrasing in what a reader sees
  const seen = [...d.querySelectorAll(".mk-hero, .mk-sec, .mk-card, .mk-intro, .mk-full")].map(e => e.textContent).join(" ");
  const stock = ["straight from", "delve", "landscape", "in today's", "tapestry", "navigate", "unlock", "seamless", "robust", "it's worth noting", "whether you're"];
  check("no stock phrasing", !stock.some(w => seen.toLowerCase().includes(w)), stock.filter(w => seen.toLowerCase().includes(w)).join(","));
  check("no double hyphens in copy", !/ -- /.test(seen));
  // 6. copy rules
  const text = d.querySelector("main, .wrap") ? d.body.textContent : "";
  check("no em dashes in rendered copy", !/\u2014/.test([...d.querySelectorAll(".mk-sec, .mk-intro")].map(e => e.textContent).join(" ")));
  console.log(`${checks} checks, ${fails} failures`);
  process.exit(fails ? 1 : 0);
}, 2500);
