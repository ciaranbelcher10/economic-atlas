/* percapita.js (v1.9.116): the one place per capita is worked out, shared by Chartmaker,
   Compare, Dashboard, the country pages and the indicator pages, so every surface gives the
   same number.

   Rule (decided 9 Nov 2026): each period is divided by THAT YEAR's population and nothing else.
   A period whose year has no published population is left out, never divided by another year's
   figure, and the note names it ("2026 not shown: population for 2026 not yet published").

   Population comes from the "population" series in each economy's data file (World Bank
   SP.POP.TOTL, merged by merge_population.py), as [[year, people], ...].

   Pure functions, no DOM: window.EA_PC in the browser, module.exports under Node (tests). */
(function(root){
  "use strict";

  // Currency amounts only: per person makes no sense for rates, indices or percentages.
  // v1.9.122: deficit (government borrowing) added, decided 10 Nov 2026.
  var ELIGIBLE = ["gdp_level", "gdp_real", "exports", "imports", "trade_balance", "net_debt", "debt_interest", "deficit"];

  function eligible(metric){ return ELIGIBLE.indexOf(metric) !== -1; }

  // "£m" -> 1e6, "$bn" -> 1e9, "€tn" -> 1e12, "CNYm" -> 1e6, "¥" -> 1. Same suffixes as the
  // site's scale_of(); "people" or anything unrecognised -> 1.
  function scaleOf(unit){
    var u = String(unit || "").replace(/\s*\(.*\)\s*$/, "").trim();   // "$m (2021 prices)" -> "$m"
    var m = /(tn|bn|m|k)$/.exec(u);
    if(!m) return 1;
    return { tn: 1e12, bn: 1e9, m: 1e6, k: 1e3 }[m[1]];
  }

  // The currency part of a unit: "£m" -> "£", "US$bn" -> "US$", "CNYm" -> "CNY".
  function currencyOf(unit){
    return String(unit || "").replace(/\s*\(.*\)\s*$/, "").trim().replace(/(tn|bn|m|k)$/, "");
  }

  // "£m" -> "£ per person". The value is then in whole currency units per person.
  function unitLabel(unit){
    var c = currencyOf(unit);
    return (c ? c + " " : "") + "per person";
  }

  // { "2024": 69281000, ... } from [[year, people], ...]; keeps only positive whole numbers.
  function popIndex(popPoints){
    var idx = {};
    (popPoints || []).forEach(function(p){
      var y = String(p && p[0]).slice(0, 4), v = p && Number(p[1]);
      if(/^\d{4}$/.test(y) && isFinite(v) && v > 0) idx[y] = v;
    });
    return idx;
  }

  function yearOf(period){ return String(period).slice(0, 4); }

  /* Divide each point by its own year's population.
       pts:       [{x: period, y: value}, ...] in `unit` (e.g. "£m")
       popPoints: [[year, people], ...]
     Returns { pts, unit, droppedYears (sorted, unique), droppedCount, ok }.
     ok is false when there is no population at all for this economy (e.g. Taiwan). */
  function divide(pts, unit, popPoints){
    var idx = popIndex(popPoints), scale = scaleOf(unit);
    var out = [], dropped = {}, n = 0;
    var have = Object.keys(idx).length > 0;
    (pts || []).forEach(function(p){
      if(p == null || p.y == null || !isFinite(p.y)) return;
      var y = yearOf(p.x), pop = idx[y];
      if(!pop){ dropped[y] = true; n++; return; }
      out.push({ x: p.x, y: p.y * scale / pop });
    });
    return { pts: out, unit: unitLabel(unit), droppedYears: Object.keys(dropped).sort(),
             droppedCount: n, ok: have };
  }

  // "2026" / "2025 and 2026" / "2024, 2025 and 2026"
  // v1.9.121: a run of three or more consecutive years reads "1955 to 1959"; every missing year is still named.
  function listYears(ys){
    var parts = [], i = 0;
    while(i < ys.length){
      var j = i;
      while(j + 1 < ys.length && Number(ys[j + 1]) === Number(ys[j]) + 1) j++;
      if(j - i >= 2) parts.push(ys[i] + " to " + ys[j]);
      else for(var k = i; k <= j; k++) parts.push(ys[k]);
      i = j + 1;
    }
    if(parts.length <= 1) return parts.join("");
    return parts.slice(0, -1).join(", ") + " and " + parts[parts.length - 1];
  }

  /* The note shown under a chart or table when per capita is on.
       droppedYears: from divide(); latestPopYear: newest year with a population figure. */
  function note(droppedYears, latestPopYear, noPopulation){
    if(noPopulation) return "Per capita: not available for this economy (no population figure covering the same area as its GDP is published).";
    var s = "Per capita: each value divided by that year\u2019s population (World Bank; Eurostat for Cyprus, covering the same area as its GDP).";   // v1.9.125
    var ys = (droppedYears || []).filter(function(y){ return !latestPopYear || y > latestPopYear; });
    var early = (droppedYears || []).filter(function(y){ return latestPopYear && y <= latestPopYear; });
    if(ys.length) s += " " + listYears(ys) + " not shown: population for " + listYears(ys) + " not yet published.";
    if(early.length) s += " " + listYears(early) + " not shown: no population figure for " + (early.length > 1 ? "those years" : "that year") + ".";
    return s;
  }

  function latestYear(popPoints){
    var ks = Object.keys(popIndex(popPoints)).sort();
    return ks.length ? ks[ks.length - 1] : null;
  }

  var api = { listYears: listYears, ELIGIBLE: ELIGIBLE, eligible: eligible, scaleOf: scaleOf, unitLabel: unitLabel,
              popIndex: popIndex, divide: divide, note: note, latestYear: latestYear };
  if(typeof module !== "undefined" && module.exports) module.exports = api;
  else root.EA_PC = api;
})(typeof window !== "undefined" ? window : this);
