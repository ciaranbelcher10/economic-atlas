/* percapita.js (v1.9.116; v1.9.128 relabel + infoNote for the (i) popovers): the one place per capita is worked out, shared by Chartmaker,
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


  /* v1.9.128: the (i) popovers. Notes in data-metric-sources.json still use the toggles' old names
     ("Make it real", "Dollarise"); relabel() shows the current names, and infoNote() is the Per capita
     paragraph every (i) now carries, so the popover explains all three switches. */
  function relabel(t){
    return String(t == null ? "" : t)
      .replace(/Dollari[sz]ed/g, "converted to US$").replace(/Dollari[sz]ing/g, "converting to US$")
      .replace(/Dollari[sz]e/g, "Convert to USD$").replace(/Make it real/g, "Adjust for inflation");
  }
  var GDP_KEYS = ["gdp_level", "gdp_real"];
  /* metric: series key. opts.noPopulation: the economy has no population figure (Taiwan).
     opts.on: Per capita is switched on now. opts.unit: the series unit, when known. Returns plain text (no HTML). */
  function infoNote(metric, opts){
    opts = opts || {};
    if(metric === "gdp_per_capita") return "This is already a per person figure, so Per capita has no further effect on it.";
    if(metric === "population") return "This is the population itself, the figure Per capita divides by; the switch has no effect on it.";
    if(!eligible(metric)) return "Per capita applies only to GDP, trade and government debt, interest and borrowing amounts, so it has no effect on this figure.";
    if(opts.unit != null && !/(m|bn|tn)$/.test(String(opts.unit).replace(/\s*\(.*\)\s*$/, "").trim()))
      return "This is not a currency amount here (for example a share of GDP), so Per capita has no effect on it.";
    if(opts.noPopulation) return "Not available for this economy: no population figure covering the same area as its GDP is published, so the switch is turned off.";
    var s = "Divides each value by that year\u2019s population (World Bank; Eurostat for Cyprus, covering the same area as its GDP), giving a figure per person. A year with no published population is left out and named under the chart, never divided by another year\u2019s figure.";
    if(GDP_KEYS.indexOf(metric) !== -1) s += " GDP per person uses the latest complete calendar year, not a rolling four quarters.";
    if(opts.on) s = "On now: the figures shown are per person. " + s;
    return s;
  }

/* EA_axisTick (v1.9.128): y-axis labels that differ. Chart.js asks for one tick label at a time;
     when the page's formatter gives two ticks the same label (China's population, 1.40bn to 1.41bn,
     read "1.4bn" five times), this adds decimals to every label on that axis until they all differ.
     Works with any formatter of the form prefix + number + suffix ("$1.4bn", "−2.5%", "£43k").
     The same function sits in percapita.js and indicator-kit.js (test_v19128 checks they match). */
  function EA_axisTick(fmt, v, i, ticks){
    if(!ticks || ticks.length < 2 || typeof i !== "number") return fmt(v);
    if(ticks.__eaFmt === fmt && ticks.__eaLabels) return ticks.__eaLabels[i];
    var base = ticks.map(function(t){ return fmt(t.value); });
    function uniq(ls){ var seen = {}; for(var k = 0; k < ls.length; k++){ if(seen[ls[k]]) return false; seen[ls[k]] = 1; } return true; }
    function refine(label, val, extra, power){
      var m = /^(.*?)(\d[\d,]*(?:\.\d+)?)(.*)$/.exec(String(label));
      if(!m || !isFinite(val) || val === 0) return label;
      var num = Number(m[2].replace(/,/g, ""));
      var p = num ? Math.round(Math.log10(Math.abs(val) / num)) : power;
      var dp = ((m[2].split(".")[1] || "").length) + extra;
      var s = (Math.abs(val) / Math.pow(10, p)).toFixed(dp);
      s = s.replace(/^\d+/, function(n){ return n.replace(/\B(?=(\d{3})+(?!\d))/g, ","); });
      return m[1] + s + m[3];
    }
    // a label that rounds to "0" cannot show its own scale, so it borrows its neighbours' ("bn", "%")
    var power = 0;
    for(var q = 0; q < ticks.length; q++){
      var mm = /(\d[\d,]*(?:\.\d+)?)/.exec(String(base[q])), nn = mm && Number(mm[1].replace(/,/g, ""));
      if(nn && ticks[q].value){ power = Math.round(Math.log10(Math.abs(ticks[q].value) / nn)); break; }
    }
    var out = base;
    for(var extra = 1; extra <= 6 && !uniq(out); extra++){
      out = ticks.map(function(t, k){ return refine(base[k], t.value, extra, power); });
    }
    ticks.__eaFmt = fmt; ticks.__eaLabels = out;
    return out[i];
  }
  if(typeof window !== "undefined") window.EA_axisTick = EA_axisTick;

  var api = { axisTick: EA_axisTick, relabel: relabel, infoNote: infoNote, listYears: listYears, ELIGIBLE: ELIGIBLE, eligible: eligible, scaleOf: scaleOf, unitLabel: unitLabel,
              popIndex: popIndex, divide: divide, note: note, latestYear: latestYear };
  if(typeof module !== "undefined" && module.exports) module.exports = api;
  else root.EA_PC = api;
})(typeof window !== "undefined" ? window : this);
