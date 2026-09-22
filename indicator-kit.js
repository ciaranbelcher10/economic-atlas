/* indicator-kit.js
   Shared runtime for /indicators/ and /rankings/ pages.

   One formatter for every number these pages draw: headline figure, delta,
   chart axis, chart tooltip, ranking cells. It follows the rules the country
   pages already use (curFmt / scaleOf / currencySymbol / NATIVE_SYMBOL_OVERRIDE):
     - "%" units: 1dp, policy rates and bond yields 2dp; deltas in pp
     - "index" units: 1dp; deltas in points
     - currency units ("£m", "$bn", "ARSm", "₪m (2021 prices)"): value folded
       to its true magnitude, then shown as tn / bn / m / k with the right
       symbol. ISO-coded units (ARS, CLP, COP...) keep their code, and the
       five currencies that share the "$" glyph show A$, R$, C$, MX$ or R on
       GDP series unless the figure has been converted to US dollars.
   generate_indicator_pages.py carries a Python port (fmt_num) of this same
   function for the figures baked into the HTML; tools/test_indicator_fmt.js
   checks the two agree. */
(function(){
  "use strict";
  var MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  var MINUS = "\u2212";
  var RATE_KEYS = {boe_rate:1, fed_funds:1, ecb_rate:1, boj_rate:1, overnight_rate:1, policy_rate:1, bond_yield_10y:1};
  var NATIVE_DOLLAR = {Australia:"A$", Brazil:"R$", Canada:"C$", Mexico:"MX$", "South Africa":"R"};
  var NATIVE_KEYS = {gdp_level:1, gdp_real:1};
  var STALE_DAYS = {months:75, quarters:150, years:660};

  function cleanUnit(u){ return String(u || "").replace(/\s*\([^)]*\)\s*$/, "").trim(); }
  function unitKind(u){
    var c = cleanUnit(u);
    if(c.indexOf("%") > -1) return "pct";
    if(c === "index" || c === "") return "index";
    return "cur";
  }
  function scaleOf(u){
    var c = cleanUnit(u);
    if(/tn$/.test(c)) return 1e12;
    if(/bn$/.test(c)) return 1e9;
    if(/m$/.test(c)) return 1e6;
    if(/k$/.test(c)) return 1e3;
    return 1;
  }
  function symbolOf(u, key, country, dollarised){
    var c = cleanUnit(u);
    var m = c.match(/^[^a-zA-Z0-9]+/);
    var sym = m ? m[0] : "";
    if(!m){
      var code = c.match(/^([A-Z]{3})(tn|bn|m|k)?$/);
      sym = code ? code[1] : "";
    }
    if(sym === "$" && !dollarised && NATIVE_KEYS[key] && NATIVE_DOLLAR[country]) sym = NATIVE_DOLLAR[country];
    return sym;
  }
  function trim(s){ return s.replace(/(\.\d*[1-9])0+(?!\d)|\.0+(?!\d)/, function(m, keep){ return keep || ""; }); }

  /* mode: "value" (headline), "cell" (table column: fixed decimals, no trim), "tip" (tooltip), "axis" (tick), "delta" (signed change) */
  function fmtNum(v, o){
    if(v == null || !isFinite(v)) return "n/a";
    o = o || {};
    var mode = o.mode || "value", kind = unitKind(o.unit);
    var neg = v < 0, sign = neg ? MINUS : (mode === "delta" && v > 0 ? "+" : "");
    var a = Math.abs(v), out;
    if(kind === "pct"){
      var dp = RATE_KEYS[o.key] ? 2 : 1;
      if(mode === "axis") return (neg ? MINUS : "") + trim(a.toFixed(2)) + "%";
      if(mode === "delta") return sign + a.toFixed(dp) + "pp";
      return (neg ? MINUS : "") + a.toFixed(dp) + "%";
    }
    if(kind === "index"){
      if(mode === "axis") return (neg ? MINUS : "") + trim(a.toFixed(1));
      if(mode === "delta") return sign + a.toFixed(1) + " pts";
      return (neg ? MINUS : "") + a.toFixed(1);
    }
    var sym = symbolOf(o.unit, o.key, o.country, o.dollarised);
    var abs = a * scaleOf(o.unit);
    var d = mode === "axis" || mode === "delta" ? 1 : 2;
    if(abs >= 1e12) out = (abs/1e12).toFixed(d) + "tn";
    else if(abs >= 1e9) out = (abs/1e9).toFixed(d) + "bn";
    else if(abs >= 1e6) out = (abs/1e6).toFixed(abs >= 1e8 ? 0 : 1) + "m";
    else if(abs >= 1e3) out = (abs/1e3).toFixed(abs >= 1e5 ? 0 : 1) + "k";
    else out = abs.toFixed(0);
    out = mode === "cell" ? out : trim(out);
    // Economies measured in trillions of a small-unit currency (COP, IDR,
    // KRW, ARS) run past 1,000tn; group the digits so they stay readable.
    out = out.replace(/^\d+/, function(n){ return n.replace(/\B(?=(\d{3})+(?!\d))/g, ","); });
    return sign + sym + out;
  }
  function roundedDelta(d, unit, key){
    var k = unitKind(unit), dp = k === "pct" ? (RATE_KEYS[key] ? 2 : 1) : (k === "index" ? 1 : null);
    if(dp === null) return d;
    var f = Math.pow(10, dp);
    return Math.round(d * f) / f;
  }
  function fmtPeriod(p){
    p = String(p || "");
    var m = /^(\d{4})-Q([1-4])$/.exec(p);
    if(m) return "Q" + m[2] + " " + m[1];
    m = /^(\d{4})-(\d{2})$/.exec(p);
    if(m) return MONTHS[+m[2]-1] + " " + m[1];
    return p;
  }
  function periodEnd(p){
    var m = /^(\d{4})-Q([1-4])$/.exec(p);
    if(m) return new Date(Date.UTC(+m[1], (+m[2])*3, 0));
    m = /^(\d{4})-(\d{2})$/.exec(p);
    if(m) return new Date(Date.UTC(+m[1], +m[2], 0));
    m = /^(\d{4})$/.exec(p);
    if(m) return new Date(Date.UTC(+m[1], 12, 0));
    return null;
  }
  function isFresh(p, freq){
    var e = periodEnd(p);
    if(!e) return true;
    return (Date.now() - e.getTime()) / 86400000 <= (STALE_DAYS[freq] || 90);
  }
  /* Same trailing four-quarter sum the country pages use in annualGDP(). */
  function annualise(pts, freq, raw){
    if(raw || freq === "years") return pts;
    var out = [];
    for(var i = 3; i < pts.length; i++){
      var w = pts.slice(i-3, i+1);
      if(w.some(function(p){ return p[1] == null; })) continue;
      out.push([pts[i][0], w[0][1]+w[1][1]+w[2][1]+w[3][1]]);
    }
    return out;
  }
  function monthKey(p){
    var y = /^(\d{4})/.exec(p); if(!y) return null;
    var yr = +y[1], q = /^\d{4}-Q([1-4])$/.exec(p), m = /^\d{4}-(\d{2})$/.exec(p);
    if(q) return yr*12 + (+q[1]-1)*3;
    if(m) return yr*12 + (+m[1]-1);
    return yr*12;
  }
  /* Historical-rate matching, identical to the country pages' rateForPeriod(). */
  function rateForPeriod(p, hist){
    if(!hist || !hist.length) return null;
    var matches;
    if(/^\d{4}$/.test(p)) matches = hist.filter(function(h){ return h[0].indexOf(p + "-") === 0; });
    else if(/^\d{4}-Q[1-4]$/.test(p)){
      var y = p.slice(0,4), s = (+p.slice(6)-1)*3 + 1;
      var want = [s, s+1, s+2].map(function(n){ return y + "-" + String(n).padStart(2, "0"); });
      matches = hist.filter(function(h){ return want.indexOf(h[0]) > -1; });
    } else matches = hist.filter(function(h){ return h[0] === p; });
    if(matches.length) return matches.reduce(function(t, h){ return t + h[1]; }, 0) / matches.length;
    var k = monthKey(p), best = hist[0], bd = Infinity;
    hist.forEach(function(h){ var d = Math.abs(monthKey(h[0]) - k); if(d < bd){ bd = d; best = h; } });
    return best[1];
  }
  function toUSD(pts, fx){
    return pts.map(function(p){
      var r = fx.history ? rateForPeriod(p[0], fx.history) : fx.rate;
      return [p[0], fx.direction === "multiply" ? p[1]*r : p[1]/r];
    });
  }
  function usdUnit(u){
    var s = scaleOf(u);
    return s === 1e12 ? "$tn" : s === 1e9 ? "$bn" : s === 1e6 ? "$m" : s === 1e3 ? "$k" : "$";
  }
  function yearsBack(pts, yrs){
    if(yrs === "max") return pts;
    var end = periodEnd(pts[pts.length-1][0]);
    if(!end) return pts;
    var cut = new Date(end); cut.setUTCFullYear(cut.getUTCFullYear() - yrs);
    var f = pts.filter(function(p){ var e = periodEnd(p[0]); return e && e > cut; });
    return f.length >= 2 ? f : pts.slice(-2);
  }
  function cssVar(n, fb){
    var v = getComputedStyle(document.documentElement).getPropertyValue(n).trim();
    return v || fb;
  }

  window.EATLAS_FMT = {fmtNum: fmtNum, roundedDelta: roundedDelta, fmtPeriod: fmtPeriod, unitKind: unitKind, symbolOf: symbolOf, scaleOf: scaleOf,
    annualise: annualise, rateForPeriod: rateForPeriod, toUSD: toUSD, usdUnit: usdUnit, isFresh: isFresh};

  /* ------------------------------------------------------------------ */
  /* Indicator page                                                      */
  /* ------------------------------------------------------------------ */
  function initIndicator(cfg){
    var state = {nominal: cfg.points, real: cfg.realPoints || null, fx: cfg.fx || null,
                 real_on: false, dollar_on: false, range: "max"};
    var chart = null;

    function current(){
      var pts = state.real_on && state.real ? state.real : state.nominal;
      var unit = state.real_on && state.real ? (cfg.realUnit || cfg.unit) : cfg.unit;
      var dollarised = false;
      if(state.dollar_on && state.fx){ pts = toUSD(pts, state.fx); unit = usdUnit(unit); dollarised = true; }
      return {pts: pts, unit: unit, dollarised: dollarised};
    }
    function fo(unit, dollarised, mode){
      return {unit: unit, key: cfg.key, country: cfg.country, dollarised: dollarised, mode: mode};
    }
    function drawChart(pts, unit, dollarised){
      var canvas = document.getElementById("indChart");
      if(!canvas || typeof Chart === "undefined") return;
      var shown = yearsBack(pts, state.range);
      var INK = cssVar("--ink", "#171B1E"), INK2 = cssVar("--ink2", "#5A6167"), HAIR = cssVar("--hair", "#E4E6E1");
      var PANEL = cssVar("--panel", "#fff"), LINE = cssVar("--mako-3", "#37659E"), NAVY = cssVar("--navy", "#1E4566");
      var FONT = {family: "'Avenir Next','Avenir','Nunito Sans',system-ui,sans-serif", size: 11.5};
      var isBar = cfg.chart === "bar";
      if(chart){ chart.destroy(); chart = null; }
      var ctx = canvas.getContext("2d");
      var grad = ctx.createLinearGradient(0, 0, 0, canvas.clientHeight || 320);
      grad.addColorStop(0, "rgba(55,101,158,.20)");
      grad.addColorStop(1, "rgba(55,101,158,0)");
      var n = shown.length;
      var ds = isBar ? {
        data: shown.map(function(p){ return p[1]; }),
        backgroundColor: shown.map(function(p){ return p[1] < 0 ? "#8FB8D8" : LINE; }),
        borderRadius: 2, maxBarThickness: 14
      } : {
        data: shown.map(function(p){ return p[1]; }),
        borderColor: LINE, borderWidth: 2.2, tension: 0.2, fill: true, backgroundColor: grad,
        pointRadius: shown.map(function(_, i){ return i === n-1 ? 4 : 0; }),
        pointBackgroundColor: NAVY, pointBorderColor: PANEL, pointBorderWidth: 2, pointHitRadius: 8
      };
      chart = new Chart(canvas, {
        type: isBar ? "bar" : "line",
        data: {labels: shown.map(function(p){ return p[0]; }), datasets: [ds]},
        options: {
          responsive: true, maintainAspectRatio: false, animation: {duration: 350},
          interaction: {mode: "index", intersect: false},
          plugins: {
            legend: {display: false},
            tooltip: {backgroundColor: PANEL, titleColor: INK, bodyColor: INK, borderColor: HAIR, borderWidth: 1,
              padding: 10, displayColors: false,
              titleFont: {family: FONT.family, weight: "600"}, bodyFont: {family: FONT.family, size: 13, weight: "700"},
              callbacks: {
                title: function(items){ return fmtPeriod(items[0].label); },
                label: function(c){ return fmtNum(c.parsed.y, fo(unit, dollarised, "tip")); }
              }}
          },
          scales: {
            x: {grid: {display: false}, border: {color: HAIR},
                ticks: {color: INK2, font: FONT, maxTicksLimit: 7, maxRotation: 0, autoSkipPadding: 16,
                  callback: function(v){ var l = this.getLabelForValue(v); return shown.length > 30 ? String(l).slice(0,4) : fmtPeriod(l); }}},
            y: {grid: {color: function(c){ return c.tick && c.tick.value === 0 ? INK2 : HAIR; }}, border: {display: false},
                ticks: {color: INK2, font: FONT, maxTicksLimit: 6,
                  callback: function(v){ return fmtNum(v, fo(unit, dollarised, "axis")); }}}
          }
        }
      });
    }
    function paint(){
      var c = current(), pts = c.pts;
      if(!pts || pts.length < 2) return;
      var last = pts[pts.length-1], prev = pts[pts.length-2];
      var fig = document.getElementById("indFigure");
      if(fig) fig.textContent = fmtNum(last[1], fo(c.unit, c.dollarised, "value"));
      var d = roundedDelta(last[1] - prev[1], c.unit, cfg.key);
      var dEl = document.getElementById("indDelta");
      if(dEl){
        var flat = Math.abs(d) < 1e-9;
        var dir = flat ? "flat" : ((d > 0) === cfg.upIsGood ? "good" : "bad");
        dEl.className = "ind-delta " + dir;
        dEl.innerHTML = '<span aria-hidden="true">' + (flat ? "\u25AC" : (d > 0 ? "\u25B2" : "\u25BC")) + '</span> '
          + (flat ? "No change" : fmtNum(d, fo(c.unit, c.dollarised, "delta"))) + ' <span class="ind-delta-vs">vs ' + fmtPeriod(prev[0]) + '</span>';
      }
      var per = document.getElementById("indPeriod");
      if(per) per.textContent = fmtPeriod(last[0]);
      var rng = document.getElementById("indRange");
      var shown = yearsBack(pts, state.range);
      if(rng) rng.textContent = fmtPeriod(shown[0][0]) + " to " + fmtPeriod(shown[shown.length-1][0]);
      var led = document.getElementById("indLed");
      if(led){
        var fresh = isFresh(last[0], cfg.freq);
        led.className = "led " + (fresh ? "green" : "orange");
        var t = fresh ? "Latest release: " + fmtPeriod(last[0]) : "Awaiting next release. Last data: " + fmtPeriod(last[0]);
        led.title = t; led.setAttribute("aria-label", t);
      }
      drawChart(pts, c.unit, c.dollarised);
    }

    document.querySelectorAll("[data-range]").forEach(function(b){
      b.addEventListener("click", function(){
        document.querySelectorAll("[data-range]").forEach(function(o){ o.classList.remove("active"); o.setAttribute("aria-pressed", "false"); });
        b.classList.add("active"); b.setAttribute("aria-pressed", "true");
        state.range = b.dataset.range === "max" ? "max" : +b.dataset.range;
        paint();
      });
    });
    [["indToggleReal", "real_on"], ["indToggleDollar", "dollar_on"]].forEach(function(t){
      var b = document.getElementById(t[0]);
      if(!b) return;
      b.addEventListener("click", function(){
        state[t[1]] = !state[t[1]];
        b.classList.toggle("on", state[t[1]]);
        b.setAttribute("aria-pressed", state[t[1]] ? "true" : "false");
        paint();
      });
    });
    paint();

    /* Live refresh: the baked figures are a fallback; the data file is the truth. */
    fetch(cfg.dataUrl, {cache: "no-cache"}).then(function(r){ if(!r.ok) throw 0; return r.json(); }).then(function(d){
      var s = d && d.series && d.series[cfg.key];
      if(!s || !s.points) return;
      var pts = s.points.filter(function(p){ return p && p[1] != null; });
      if(cfg.annualise) pts = annualise(pts, s.freq, cfg.gdpRaw);
      if(pts.length < 2) return;
      state.nominal = pts;
      if(s.freq) cfg.freq = s.freq;
      if(cfg.realKey && d.series[cfg.realKey]){
        var rs = d.series[cfg.realKey];
        var rp = rs.points.filter(function(p){ return p && p[1] != null; });
        if(cfg.annualise) rp = annualise(rp, rs.freq, cfg.gdpRaw);
        if(rp.length >= 2) state.real = rp;
      }
      if(cfg.fx && d.fx_to_usd) state.fx = d.fx_to_usd;
      paint();
    }).catch(function(){
      var led = document.getElementById("indLed");
      if(led){ led.className = "led"; led.title = "Showing the last stored figure"; led.setAttribute("aria-label", led.title); }
    });
  }

  /* ------------------------------------------------------------------ */
  /* Ranking page: sortable table                                        */
  /* ------------------------------------------------------------------ */
  function initRanking(){
    var table = document.getElementById("rkTable");
    if(!table) return;
    var tbody = table.tBodies[0];
    var heads = table.querySelectorAll("th[data-sort]");
    function sortBy(th, dir){
      var col = th.dataset.sort, type = th.dataset.type || "num";
      var rows = Array.prototype.slice.call(tbody.rows);
      rows.sort(function(a, b){
        var av = a.dataset[col], bv = b.dataset[col];
        if(type === "text") return av.localeCompare(bv) * dir;
        var an = av === "" ? null : +av, bn = bv === "" ? null : +bv;
        if(an == null && bn == null) return 0;
        if(an == null) return 1;
        if(bn == null) return -1;
        return (an - bn) * dir;
      });
      rows.forEach(function(r){ tbody.appendChild(r); });
      heads.forEach(function(h){ h.classList.remove("sorted", "asc"); h.setAttribute("aria-sort", "none"); });
      th.classList.add("sorted"); if(dir > 0) th.classList.add("asc");
      th.setAttribute("aria-sort", dir > 0 ? "ascending" : "descending");
    }
    heads.forEach(function(th){
      th.tabIndex = 0;
      var go = function(){
        var dir = th.classList.contains("sorted") ? (th.classList.contains("asc") ? -1 : 1) : (th.dataset.type === "text" ? 1 : -1);
        sortBy(th, dir);
      };
      th.addEventListener("click", go);
      th.addEventListener("keydown", function(e){ if(e.key === "Enter" || e.key === " "){ e.preventDefault(); go(); } });
    });
  }

  window.EATLAS_IND = {initIndicator: initIndicator, initRanking: initRanking};
})();
