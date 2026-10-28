/* doc.js (v1.9.16): behaviour for the reference pages, /methodology and /methodology-by-economy.
   Progressive enhancement only: every page is complete and navigable without it (the contents list, the
   economy index and every accordion work as plain links and <details>). No dependencies. */
(function () {
  "use strict";
  var doc = document;
  function all(sel, root) { return Array.prototype.slice.call((root || doc).querySelectorAll(sel)); }

  // 1. A link to every section (shown on hover or keyboard focus)
  all(".doc-sec[id] > h2, .doc-sec[id] .ind-panelhead > h2").forEach(function (h) {
    if (h.querySelector(".doc-anchor")) return;
    var sec = h.closest(".doc-sec[id]");
    var a = doc.createElement("a");
    a.className = "doc-anchor"; a.href = "#" + sec.id;
    a.setAttribute("aria-label", "Link to this section"); a.textContent = "#";
    h.appendChild(a);
  });

  // 2. Open the accordion a link points at, and scroll to it
  function openTarget() {
    var id = decodeURIComponent((location.hash || "").slice(1));
    if (!id) return;
    var el = doc.getElementById(id);
    if (!el) return;
    var d = el.tagName === "DETAILS" ? el : el.closest("details");
    if (d) d.open = true;
    if (el.hidden) { clearFilters(); }
  }

  // 3. Highlight where you are in the contents list
  var tocLinks = all(".doc-toc a[href^='#']");
  if (tocLinks.length && "IntersectionObserver" in window) {
    var byId = {};
    tocLinks.forEach(function (a) { byId[a.getAttribute("href").slice(1)] = a; });
    var current = null;
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (!e.isIntersecting) return;
        var a = byId[e.target.id];
        if (!a || a === current) return;
        if (current) current.classList.remove("is-active");
        a.classList.add("is-active"); current = a;
      });
    }, { rootMargin: "-20% 0px -70% 0px" });
    Object.keys(byId).forEach(function (id) { var s = doc.getElementById(id); if (s) io.observe(s); });
  }

  // 4. Find an economy (by-economy page only)
  var input = doc.getElementById("docFilter");
  var sections = all(".mb-econ");
  var chips = all(".doc-chip");
  var countEl = doc.getElementById("docCount");
  var emptyEl = doc.getElementById("docEmpty");
  var state = { q: "", region: "" };
  function applyFilters() {
    var shown = 0, q = state.q.trim().toLowerCase();
    sections.forEach(function (s) {
      var ok = (!q || (s.getAttribute("data-name") || "").toLowerCase().indexOf(q) !== -1) &&
               (!state.region || s.getAttribute("data-region") === state.region);
      s.hidden = !ok;
      var link = doc.querySelector(".mb-index a[data-for='" + s.id + "']");
      if (link) link.hidden = !ok;
      if (ok) shown++;
    });
    if (countEl) countEl.textContent = (q || state.region) ? shown + " of " + sections.length + " economies" : "";
    if (emptyEl) emptyEl.hidden = shown !== 0;
  }
  function clearFilters() {
    state = { q: "", region: "" };
    if (input) input.value = "";
    chips.forEach(function (c) { c.classList.toggle("current", c.getAttribute("data-region") === ""); });
    applyFilters();
  }
  if (input && sections.length) {
    input.addEventListener("input", function () { state.q = input.value; applyFilters(); });
    chips.forEach(function (c) {
      c.addEventListener("click", function () {
        state.region = c.getAttribute("data-region") || "";
        chips.forEach(function (x) { x.classList.toggle("current", x === c); x.setAttribute("aria-pressed", x === c ? "true" : "false"); });
        applyFilters();
      });
    });
  }

  // 5. Back to top
  var top = doc.createElement("button");
  top.type = "button"; top.className = "doc-top"; top.setAttribute("aria-label", "Back to top"); top.textContent = "\u2191";
  top.addEventListener("click", function () {
    var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    window.scrollTo({ top: 0, behavior: reduce ? "auto" : "smooth" });
  });
  doc.body.appendChild(top);
  function onScroll() { top.classList.toggle("is-on", (window.pageYOffset || doc.documentElement.scrollTop) > 700); }
  window.addEventListener("scroll", onScroll, { passive: true });
  onScroll();

  window.addEventListener("hashchange", openTarget);
  openTarget();
})();
