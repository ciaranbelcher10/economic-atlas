#!/usr/bin/env node
/* v1.9.100: Methodology "On this page" on phones: numbered rows with arrows, short labels, Hide/Show.
 * Desktop keeps the full titles and no fold button. jsdom has no layout, so CSS is checked statically.
 * Run: NODE_PATH=/tmp/node_modules node tools/test_methodology_toc.js */
const fs = require("fs"), path = require("path");
const ROOT = path.resolve(__dirname, ".."), NM = (process.env.NODE_PATH || "/tmp/node_modules").split(path.delimiter)[0] + "/";
const { JSDOM, VirtualConsole } = require(NM + "jsdom");
let checks = 0, failures = 0; const ok = (c, m) => { checks++; if (!c) { failures++; console.log("  FAIL  " + m); } };
const HTML = fs.readFileSync(path.join(ROOT, "methodology.html"), "utf8");
const dom = new JSDOM(HTML, { runScripts: "dangerously", virtualConsole: new VirtualConsole(), url: "https://theeconomicatlas.com/methodology",
  beforeParse(w){ w.matchMedia = () => ({ matches: false, addListener(){}, removeListener(){}, addEventListener(){}, removeEventListener(){} });
    w.IntersectionObserver = class { observe(){} unobserve(){} disconnect(){} }; w.scrollTo = () => {}; } });
const d = dom.window.document;
const nav = d.querySelector('nav.doc-toc[data-toc="num"]');
ok(nav, "contents list marked for the numbered phone layout");
const links = [...d.querySelectorAll("#docTocList a")];
const secs = [...d.querySelectorAll("section.doc-sec[id]")].map(s => s.id);
ok(links.length === 8 && links.map(a => a.getAttribute("href").slice(1)).join() === secs.join(), "8 rows link the 8 sections in order");
ok(links.every(a => a.querySelector(".doc-toc-full") && a.querySelector(".doc-toc-short")), "every row has a full and a short label");
ok(links.every(a => { const h = d.getElementById(a.getAttribute("href").slice(1)).querySelector("h2"); return h && a.querySelector(".doc-toc-full").textContent === h.textContent; }), "full labels match the section headings");
ok(links.every(a => a.querySelector(".doc-toc-short").textContent.length <= 26), "short labels fit one line (26 chars max)");
ok(links.every(a => a.querySelector(".doc-toc-short").getAttribute("aria-hidden") === "true"), "short labels hidden from screen readers (full title is read)");
ok(/· 8 sections/.test(nav.querySelector(".doc-toc-n").textContent), "header shows the section count");
const b = nav.querySelector(".doc-toc-fold"), ul = d.getElementById("docTocList");
ok(b && b.getAttribute("aria-controls") === "docTocList" && b.textContent === "Hide" && !ul.hidden, "starts open with a Hide button");
b.click(); ok(ul.hidden && b.textContent === "Show" && b.getAttribute("aria-expanded") === "false", "Hide folds the list");
b.click(); ok(!ul.hidden && b.textContent === "Hide" && b.getAttribute("aria-expanded") === "true", "Show opens it again");
// static CSS guards
const CSS = (HTML.match(/<style>\s*\/\* v1\.9\.100[\s\S]*?<\/style>/) || [""])[0];
const PH = (CSS.match(/@media \(max-width:640px\)\{([\s\S]*)\}\s*<\/style>/) || [])[1] || "";
ok(/\.doc-toc-n, \.doc-toc-short, \.doc-toc-fold\{display:none;\}/.test(CSS.split("@media")[0]), "desktop hides the count, short labels and fold button");
ok(/a::before\{content:counter\(toc\);/.test(PH) && /li\{counter-increment:toc;/.test(PH), "phone rows are numbered");
ok(/a::after\{content:"\\203A";/.test(PH), "phone rows end in an arrow");
ok(/li\{counter-increment:toc; border-top:1px solid var\(--hair\);\}/.test(PH), "phone rows have dividers");
ok(/a\.is-active, \.doc-toc\[data-toc="num"\] a:hover\{[^}]*background:none;/.test(PH), "phone drops the dark active-row band");
ok(/a, [^{]*\{[^}]*min-height:48px;/.test(PH) && /\.doc-toc-fold\{[^}]*min-height:44px;/.test(PH), "phone rows 48px, fold button 44px");
ok(/\.doc-toc-full\{display:none;\}/.test(PH) && /\.doc-toc-short\{display:inline;\}/.test(PH), "phone swaps in the short labels");
console.log(`test_methodology_toc: ${checks} checks, ${failures} failures`);
process.exit(failures ? 1 : 0);
