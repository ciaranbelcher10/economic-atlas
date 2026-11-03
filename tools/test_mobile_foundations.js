// v1.9.68: mobile foundations. Five-tab bottom bar (Calendar in, Chartmaker to the menu in v1.9.68 part 2),
// slim header that hides on scroll down and returns on scroll up, never while the menu is open.
// Run: NODE_PATH=/tmp/node_modules node tools/test_mobile_foundations.js
const fs = require("fs"), path = require("path");
const { JSDOM } = require("jsdom");
const ROOT = path.join(__dirname, "..");
const src = fs.readFileSync(path.join(ROOT, "mobile.js"), "utf8");
const css = fs.readFileSync(path.join(ROOT, "mobile.css"), "utf8");
let ok = 0, fails = [];
const check = (c, m) => { if (c) ok++; else fails.push(m); };

function boot(url, mobile) {
  const html = `<!doctype html><html><body><nav class="top"><div class="wrap"><a class="brand" href="index">EA</a>
    <button id="navToggle" aria-expanded="false"></button><div class="navlinks" id="navLinks"><a class="item" href="about">About</a></div></div></nav>
    ${/\/uk$/.test(url) ? "<nav class=\"cat\"><button>Headline</button><button>GDP</button><button class=\"active\">Trade</button></nav>" : ""}<main style="height:5000px"></main></body></html>`;
  const dom = new JSDOM(html, { url, runScripts: "outside-only", pretendToBeVisual: true });
  const w = dom.window;
  w.matchMedia = q => ({ matches: mobile && /max-width/.test(q), addListener(){}, removeListener(){}, addEventListener(){}, removeEventListener(){} });
  w.fetch = () => Promise.reject(new Error("no network"));
  w.eval(src);
  w.document.dispatchEvent(new w.Event("DOMContentLoaded"));
  return w;
}
function scrollTo(w, y) {
  Object.defineProperty(w, "scrollY", { value: y, configurable: true });
  w.dispatchEvent(new w.Event("scroll"));
  return new Promise(r => setTimeout(r, 40));
}

(async () => {
  const w = boot("https://theeconomicatlas.com/uk", true);
  const d = w.document;
  const bar = d.getElementById("mobToolbar");
  check(bar, "tab bar injected on phones");
  const labels = bar ? [...bar.querySelectorAll("a")].map(a => a.lastChild.textContent.trim()) : [];
  check(JSON.stringify(labels) === JSON.stringify(["Countries", "Compare", "Rankings", "Dashboard", "Calendar"]), "exactly the five tabs, in order: " + labels.join(","));
  check(bar && bar.querySelector("a.active") && bar.querySelector("a.active").lastChild.textContent.trim() === "Countries", "country page marks Countries active");
  check(d.body.classList.contains("mob-tabbar"), "body reserves space for the bar");
  const extra = [...d.querySelectorAll("#navLinks [data-mob-extra]")].map(a => a.textContent + ">" + a.getAttribute("href"));
  check(JSON.stringify(extra) === JSON.stringify(["Chartmaker>chartmaker", "Markets>markets"]), "Chartmaker and Markets added to the top of the menu: " + extra.join(","));
  d.dispatchEvent(new w.Event("DOMContentLoaded"));
  check(d.querySelectorAll("#mobToolbar").length === 1 && d.querySelectorAll("#navLinks [data-mob-extra]").length === 2, "running init again adds nothing twice");

  const nav = d.querySelector("nav.top");
  await scrollTo(w, 0);
  await scrollTo(w, 400);
  check(nav.classList.contains("mob-hidden") && d.body.classList.contains("mob-head-hidden"), "header hides on scroll down");
  await scrollTo(w, 360);
  check(!nav.classList.contains("mob-hidden"), "header returns on scroll up");
  await scrollTo(w, 800);
  check(nav.classList.contains("mob-hidden"), "hides again further down");
  await scrollTo(w, 30);
  check(!nav.classList.contains("mob-hidden"), "always shown near the top");
  d.getElementById("navToggle").setAttribute("aria-expanded", "true");
  await scrollTo(w, 900);
  check(!nav.classList.contains("mob-hidden"), "never hides while the menu is open");

  const sub = boot("https://theeconomicatlas.com/indicators/uk-gdp", true).document;
  check([...sub.querySelectorAll("#mobToolbar a")].every(a => a.getAttribute("href").startsWith("../")), "subfolder pages prefix tab links with ../");
  check([...sub.querySelectorAll("#navLinks [data-mob-extra]")].every(a => a.getAttribute("href").startsWith("../")), "subfolder pages prefix menu extras with ../");
  const cal = boot("https://theeconomicatlas.com/calendar", true).document;
  const ci = cal.querySelector('#mobToolbar a.active'); check(ci && ci.lastChild.textContent.trim() === "Calendar", "Calendar tab is active on the calendar page");
  const cm = boot("https://theeconomicatlas.com/chartmaker", true).document.querySelector('#navLinks [href="chartmaker"]');
  check(cm && cm.classList.contains("active"), "Chartmaker menu item is active on the Chartmaker page");
  check(d.querySelector("nav.cat").getAttribute("data-chipwatch") === "1", "country page chips are watched so the active one stays in view");
  check(!boot("https://theeconomicatlas.com/uk", false).document.querySelector("nav.cat[data-chipwatch]"), "desktop chips are left alone");

  const desk = boot("https://theeconomicatlas.com/uk", false).document;
  check(!desk.getElementById("mobToolbar") && !desk.querySelector("[data-mob-extra]"), "desktop gets no tab bar or menu extras");

  const m = css.match(/#mobToolbar\{([^}]*)\}/);
  const blk = m ? m[1] : "";
  check(/position:fixed/.test(blk) && /bottom:0/.test(blk), "bar is fixed to the bottom");
  check(/repeat\(5,/.test(blk), "five equal columns, nothing cut off");
  check(/safe-area-inset-bottom/.test(blk), "bar clears the iPhone home indicator");
  check(/body\.mob-tabbar\{[^}]*padding-bottom/.test(css), "page content is not hidden behind the bar");
  check(/nav\.top\.mob-hidden\{[^}]*translateY\(-100%\)/.test(css), "hidden header slides fully away");
  const ph = css.slice(css.indexOf("@media (max-width:760px){"));
  check(/nav\.cat\{[^}]*flex-wrap:nowrap !important[^}]*overflow-x:auto !important/.test(ph), "chips are one scrolling row on phones (beats the page's own wrap rule)");
  check(/\.hero, \.hero\.mini\{[^}]*display:grid !important[^}]*repeat\(2, minmax\(0,1fr\)\) !important/.test(ph), "tiles are two equal columns on phones");
  check(/\.hero \.stat, \.hero\.mini \.stat\{[^}]*max-width:none !important[^}]*min-width:0 !important/.test(ph), "tiles fill their column instead of a narrow fixed width");
  const mi = css.indexOf("@media (max-width:760px){");
  check(mi > 0 && css.indexOf("#mobToolbar{") > mi, "tab bar rules are phone-only");

  console.log(`test_mobile_foundations: ${ok} ok, ${fails.length} failed`);
  fails.forEach(f => console.log("FAIL: " + f));
  process.exit(fails.length ? 1 : 0);
})();
