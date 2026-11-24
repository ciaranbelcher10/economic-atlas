/* ppp.js (v2.0.16): the one place purchasing power parity is worked out, shared by every surface
   (Chartmaker, Compare, Dashboard, country pages, indicator pages), so each gives the same number.
   Built the way percapita.js is: pure functions, no DOM; window.EA_PPP in the browser, module.exports under Node.

   Rules (decided for v2.0.16):
   - PPP is a second way to convert to dollars, chosen inside Convert to USD$ ("Market rate" or "PPP").
   - Nominal GDP: each period is divided by THAT YEAR's PPP conversion factor (World Bank PA.NUS.PPP,
     local currency per international $). A year without a published factor is left out and named,
     never converted with another year's factor and never with a forecast.
   - Real GDP: constant international dollars of one anchor year. Real GDP x the anchor year's deflator
     (nominal / real, as for the US$ conversion) / the anchor year's PPP factor. Growth is then exactly
     the published real growth, as the World Bank does for its constant-PPP series.
   - Only the GDP family: GDP, real GDP, GDP per person. PPP factors are built for whole-economy output;
     trade and government money are converted at market rates, so they keep the market-rate conversion.
   - An economy is offered PPP only when merge_population.py has checked our GDP / factor against the
     World Bank's GDP at PPP (within 6%); otherwise the data file has no "ppp" series and the note says why.
   - Per capita combines: divide by population after converting (the order does not change the result). */
(function(root){
  "use strict";

  var ELIGIBLE = ["gdp_level", "gdp_real", "gdp_per_capita"];
  function eligible(metric){ return ELIGIBLE.indexOf(metric) !== -1; }

  function scaleSuffix(unit){
    var m = /(tn|bn|m|k)$/.exec(String(unit || "").replace(/\s*\(.*\)\s*$/, "").trim());
    return m ? m[1] : "";
  }
  // "£m" -> "Int$m"; "€bn (2015 prices)" -> "Int$bn"; "£" (per person) -> "Int$".
  function unitLabel(unit, anchorYear){
    return "Int$" + scaleSuffix(unit) + (anchorYear ? " (" + anchorYear + " prices)" : "");
  }

  // { "2024": 0.675, ... } from [[year, factor], ...]; positive numbers only.
  function factorIndex(points){
    var idx = {};
    (points || []).forEach(function(p){
      var y = String(p && p[0]).slice(0, 4), v = p && Number(p[1]);
      if(/^\d{4}$/.test(y) && isFinite(v) && v > 0) idx[y] = v;
    });
    return idx;
  }
  function latestYear(points){
    var ks = Object.keys(factorIndex(points)).sort();
    return ks.length ? ks[ks.length - 1] : null;
  }
  function yearOf(period){ return String(period).slice(0, 4); }

  /* Nominal: each point divided by its own year's factor.
       pts: [{x, y}] in `unit`; pppPoints: [[year, factor]]
     Returns { pts, unit, droppedYears, droppedCount, ok }. ok false: no factors for this economy. */
  function convert(pts, unit, pppPoints){
    var idx = factorIndex(pppPoints), out = [], dropped = {}, n = 0;
    (pts || []).forEach(function(p){
      if(p == null || p.y == null || !isFinite(p.y)) return;
      var f = idx[yearOf(p.x)];
      if(!f){ dropped[yearOf(p.x)] = true; n++; return; }
      out.push({ x: p.x, y: p.y / f });
    });
    return { pts: out, unit: unitLabel(unit), droppedYears: Object.keys(dropped).sort(),
             droppedCount: n, ok: Object.keys(idx).length > 0 };
  }

  /* Real: one factor for every period (the anchor year's), so growth is unchanged.
       anchor: the series' usd_anchor {year, deflator} from merge_population.py.
     ok false (nothing converted) when there is no anchor or no factor for the anchor year. */
  function convertReal(pts, unit, pppPoints, anchor){
    var idx = factorIndex(pppPoints);
    var f = anchor && idx[String(anchor.year)], d = anchor && Number(anchor.deflator);
    if(!f || !(d > 0)) return { pts: [], unit: unitLabel(unit), droppedYears: [], droppedCount: 0, ok: false,
                                missingAnchor: true };
    var k = d / f;
    var out = (pts || []).filter(function(p){ return p && p.y != null && isFinite(p.y); })
                         .map(function(p){ return { x: p.x, y: p.y * k }; });
    return { pts: out, unit: unitLabel(unit, anchor.year), droppedYears: [], droppedCount: 0, ok: true,
             anchorYear: String(anchor.year) };
  }

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

  /* The note under a chart or table when PPP is on. res: from convert()/convertReal(). */
  function note(res, latest, opts){
    opts = opts || {};
    if(opts.notOffered) return "PPP: not available for this economy" + (opts.reason ? " (" + opts.reason.replace(/\.$/, "") + ")" : "") + ".";
    if(res && res.missingAnchor) return "PPP: not available for real GDP here (no PPP conversion factor for its price base year).";
    if(res && res.anchorYear) return "PPP: real GDP in constant " + res.anchorYear + " international dollars (World Bank PPP conversion factor for " + res.anchorYear + "); growth is unchanged.";
    var s = "PPP: each value converted at that year’s PPP conversion factor (World Bank), in international dollars.";
    var ys = ((res && res.droppedYears) || []).filter(function(y){ return !latest || y > latest; });
    var early = ((res && res.droppedYears) || []).filter(function(y){ return latest && y <= latest; });
    // real GDP is never cut short (one factor for every period), so these lines name current-price figures
    if(ys.length) s += " " + listYears(ys) + " not shown at current prices: PPP factor for " + listYears(ys) + " not yet published.";
    if(early.length) s += " " + listYears(early) + " not shown at current prices: no checked PPP conversion factor for " + (early.length > 1 ? "those years" : "that year") + ".";
    return s;
  }

  /* The (i) popover paragraph. opts: country, on, notOffered. Plain text. */
  var NOUN = { gdp_level: "GDP", gdp_real: "real GDP", gdp_per_capita: "GDP per person" };
  function infoNote(metric, opts){
    opts = opts || {};
    if(!eligible(metric)) return "PPP applies only to GDP, real GDP and GDP per person; other money amounts use market exchange rates.";
    var c = opts.country ? String(opts.country) : "";
    if(opts.notOffered) return "PPP is not available" + (c ? " for " + c : "") + ".";
    var s = "PPP converts " + NOUN[metric] + (c ? " in " + c : "") + " to international dollars, which buy the same amount in every country, using the World Bank’s PPP conversion factor for each year.";
    if(metric === "gdp_real") s = "PPP shows real GDP" + (c ? " in " + c : "") + " in constant international dollars of one year, so growth is unchanged.";
    return (opts.on ? "On now. " : "") + s;
  }

  var api = { ELIGIBLE: ELIGIBLE, eligible: eligible, unitLabel: unitLabel, factorIndex: factorIndex,
              latestYear: latestYear, convert: convert, convertReal: convertReal, note: note,
              infoNote: infoNote, listYears: listYears };
  if(typeof module !== "undefined" && module.exports) module.exports = api;
  else root.EA_PPP = api;
})(typeof window !== "undefined" ? window : this);
