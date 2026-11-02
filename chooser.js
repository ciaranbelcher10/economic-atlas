/* chooser.js (v1.9.62): the metric chooser shared by ChartMaker and My Dashboard.
   One window: tick countries, pick an exact indicator version, then Add (ChartMaker) or Pin (Dashboard).
   The page passes a small adapter to EAChooser.create(); everything else lives here so the two pages
   cannot drift apart. Markup ids (cmz*) and classes (cmz-*) are unchanged from ChartMaker v1.9.37. */
(function(){
  "use strict";
  var ctx = null;   // the page adapter, set by create()

  var GROUPS = [
    { name: "G7", members: ["Canada","France","Germany","Italy","Japan","UK","US"] },
    { name: "G20", members: ["Argentina","Australia","Brazil","Canada","China","France","Germany","India","Indonesia","Italy","Japan","Mexico","Saudi Arabia","South Africa","South Korea","Turkey","UK","US"] },
    { name: "EU", members: ["Austria","Belgium","Bulgaria","Croatia","Cyprus","Czechia","Denmark","Estonia","Finland","France","Germany","Greece","Hungary","Ireland","Italy","Latvia","Lithuania","Luxembourg","Malta","Netherlands","Poland","Portugal","Romania","Slovakia","Slovenia","Spain","Sweden"] },
    { name: "Euro area", members: ["Austria","Belgium","Bulgaria","Croatia","Cyprus","Estonia","Finland","France","Germany","Greece","Ireland","Italy","Latvia","Lithuania","Luxembourg","Malta","Netherlands","Portugal","Slovakia","Slovenia","Spain"] },
    { name: "OECD", members: ["Australia","Austria","Belgium","Canada","Chile","Colombia","Czechia","Denmark","Estonia","Finland","France","Germany","Greece","Hungary","Iceland","Ireland","Israel","Italy","Japan","South Korea","Latvia","Lithuania","Luxembourg","Mexico","Netherlands","New Zealand","Norway","Poland","Portugal","Slovakia","Slovenia","Spain","Sweden","Switzerland","Turkey","UK","US"] },
    { name: "BRICS", members: ["Brazil","China","Egypt","India","Indonesia","South Africa"] }
  ];

  // Inflation measure name from a series label (moved from ChartMaker's measureName).
  function measureFromLabel(label){
    if(!label) return null;
    if(/HICP/.test(label)) return /EZ19/.test(label) ? "HICP, euro area" : "HICP";
    if(/\(D7G7\)|\(D7OE\)/.test(label)) return "CPI, HICP method";
    if(/CPIAUCNS|CPIAUCSL/.test(label)) return "CPI-U";
    if(/CPIH|\(L55O\)|\(L59C\)/.test(label)) return "CPIH";
    return "national CPI";
  }

  // Each indicator lists its exact versions. A version resolves, per country, to the concept key that
  // holds it (null when the country does not publish it).
  function has(c, k){ return !!(ctx && ctx.has(c, k)); }
  function keyIf(k){ return function(c){ return has(c, k) ? k : null; }; }
  function hicpKey(c){
    if(has(c, "cpi_hicp")) return "cpi_hicp";
    var m = ctx.measure(c, "cpi");
    return (m && /^HICP|HICP method/.test(m) && has(c, "cpi")) ? "cpi" : null;
  }
  function nationalCpiKey(c){
    if(has(c, "cpi_national")) return "cpi_national";
    var m = ctx.measure(c, "cpi");
    return (m && !/HICP/.test(m) && has(c, "cpi")) ? "cpi" : null;
  }
  function momKey(c){ return ["cpi_mom", "cpi_mom_sa", "cpih_mom", "cpi_hicp_mom", "cpi_national_mom"].filter(function(k){ return has(c, k); })[0] || null; }
  var CHOOSER = [
    { cat:"GDP & growth", nm:"GDP", ex:"The size of the economy.", v:[
      { k:"Nominal", sub:"current prices", base:"gdp_level", key:keyIf("gdp_level") },
      { k:"Real", sub:"adjusted for inflation", base:"gdp_real", key:keyIf("gdp_real") } ] },
    { cat:"GDP & growth", nm:"GDP growth", ex:"How much the real economy grew compared with a year earlier.", v:[
      { k:"On a year earlier", sub:"real", base:"gdp_growth", key:keyIf("gdp_growth") } ] },
    { cat:"GDP & growth", nm:"Productivity", ex:"How much the economy produces for each hour worked.", v:[
      { k:"Output per hour", sub:"", base:"productivity", key:keyIf("productivity") } ] },
    { cat:"Labour market", nm:"Unemployment rate", ex:"Share of people looking for work who cannot find it.", v:[
      { k:"All ages", sub:"", base:"unemployment", key:keyIf("unemployment") },
      { k:"Young people", sub:"aged 16 to 24 (15 to 24 in some countries)", base:"unemployment_1624", key:keyIf("unemployment_1624") } ] },
    { cat:"Labour market", nm:"Employment", ex:"How many working-age people have a job, or are working or looking.", v:[
      { k:"Employment rate", sub:"", base:"employment", key:keyIf("employment") },
      { k:"Participation", sub:"working or looking", base:"participation", key:keyIf("participation") },
      { k:"Economic inactivity", sub:"neither working nor looking", base:"inactivity", key:keyIf("inactivity") } ] },
    { cat:"Prices", nm:"Inflation", ex:"How fast consumer prices are rising.", v:[
      { k:"Headline", sub:"each country's main measure, on a year earlier", base:"cpi", key:keyIf("cpi") },
      { k:"HICP", sub:"EU harmonised, comparable across Europe", base:"cpi_hicp", key:hicpKey },
      { k:"National CPI", sub:"the country's own method", base:"cpi_national", key:nationalCpiKey },
      { k:"Core", sub:"excluding food and energy", base:"core_cpi", key:keyIf("core_cpi") },
      { k:"CPIH", sub:"including housing costs (UK)", base:"cpih", key:keyIf("cpih") },
      { k:"PCE", sub:"the Federal Reserve's measure (US)", base:"pce", key:keyIf("pce") },
      { k:"Month on month", sub:"headline, on the previous month", base:"cpi_mom", key:momKey } ] },
    { cat:"Prices", nm:"Producer prices", ex:"Prices businesses charge for goods leaving the factory.", v:[
      { k:"PPI", sub:"on a year earlier", base:"ppi", key:keyIf("ppi") } ] },
    { cat:"Public finances", nm:"Government debt", ex:"What the government owes.", v:[
      { k:"Gross", sub:"% of GDP", base:"debt_gdp", key:keyIf("debt_gdp") },
      { k:"Net", sub:"after the government's own financial assets", base:"net_debt", key:keyIf("net_debt") },
      { k:"Interest paid", sub:"on government debt", base:"debt_interest", key:keyIf("debt_interest") } ] },
    { cat:"Public finances", nm:"Government deficit", ex:"How much more the government spends than it raises.", v:[
      { k:"% of GDP", sub:"", base:"deficit", key:keyIf("deficit") } ] },
    { cat:"Public finances", nm:"Current account", ex:"The balance of a country's trade and income with the rest of the world.", v:[
      { k:"% of GDP", sub:"", base:"current_account", key:keyIf("current_account") } ] },
    { cat:"Trade", nm:"Trade", ex:"Goods sold to and bought from other countries.", v:[
      { k:"Trade balance", sub:"exports minus imports", base:"trade_balance", key:keyIf("trade_balance") },
      { k:"Exports", sub:"", base:"exports", key:keyIf("exports") },
      { k:"Imports", sub:"", base:"imports", key:keyIf("imports") } ] },
    { cat:"Business & investment", nm:"Business confidence", ex:"How businesses feel about the economy.", v:[
      { k:"Index", sub:"", base:"business_confidence", key:keyIf("business_confidence") } ] },
    { cat:"Business & investment", nm:"FDI inflows", ex:"Money invested into local businesses from abroad.", v:[
      { k:"% of GDP", sub:"", base:"fdi", key:keyIf("fdi") } ] },
    { cat:"Rates & yields", nm:"Interest rates", ex:"What borrowing costs.", v:[
      { k:"Policy rate", sub:"set by the central bank", base:"policy_rate", key:keyIf("policy_rate") },
      { k:"10-year bond yield", sub:"government borrowing", base:"bond_yield_10y", key:keyIf("bond_yield_10y") } ] },
    { cat:"Exchange rates", nm:"Exchange rate", ex:"What the currency is worth.", v:[
      { k:"Against the US dollar", sub:"", base:"fx_usd", key:keyIf("fx_usd") },
      { k:"Against the euro", sub:"", base:"fx_eur", key:keyIf("fx_eur") },
      { k:"Against the pound", sub:"", base:"fx_gbp", key:keyIf("fx_gbp") } ] }
  ];

  var CSS = [
    ".cmz-back{position:fixed; inset:0; background:rgba(10,14,18,.55); display:flex; align-items:center; justify-content:center; padding:20px; z-index:1200;}",
    ".cmz-back[hidden]{display:none;}",
    ".cmz{background:var(--panel); color:var(--ink); border-radius:16px; width:min(1080px,100%); max-height:min(860px,94vh); display:grid; grid-template-rows:auto auto minmax(0,1fr) auto; overflow:hidden; box-shadow:0 24px 60px rgba(0,0,0,.35);}",
    ".cmz-head{display:flex; align-items:center; gap:12px; padding:18px 22px 10px;}",
    ".cmz-head h2{font-size:20px; flex:1; margin:0;}",
    ".cmz-x{border:none; background:var(--paper); color:var(--ink); width:34px; height:34px; border-radius:50%; cursor:pointer; font-size:18px;}",
    ".cmz-search{padding:0 22px 14px;}",
    ".cmz-search input{width:100%; border:1px solid var(--hair); background:var(--paper); color:var(--ink); border-radius:9px; padding:11px 14px; font:inherit; font-size:15px;}",
    ".cmz-body{display:grid; grid-template-columns:minmax(0,5fr) minmax(0,7fr); min-height:0; border-top:1px solid var(--hair);}",
    ".cmz-col{overflow:auto; padding:16px 22px; min-height:0;}",
    ".cmz-col + .cmz-col{border-left:1px solid var(--hair);}",
    ".cmz-col h3{font-size:13px; color:var(--ink2); font-weight:700; margin:0 0 8px; text-transform:none; letter-spacing:0;}",
    ".cmz-n{font-weight:400;}",
    ".cmz-groups{display:flex; flex-wrap:wrap; gap:6px; margin-bottom:14px;}",
    ".cmz-groups button{border:1px solid var(--navy); background:transparent; color:var(--navy); border-radius:999px; padding:5px 11px; font:700 12px \"Avenir Next\",\"Avenir\",\"Nunito Sans\",sans-serif; cursor:pointer;}",
    "[data-theme=\"dark\"] .cmz-groups button{color:var(--ink); border-color:var(--blue);}",
    ".cmz-groups button.on{background:var(--navy); color:#fff;}",
    ".cmz-countries{display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:2px 10px;}",
    ".cmz-countries label{display:flex; align-items:center; gap:8px; font-size:13.5px; padding:5px 6px; border-radius:7px; cursor:pointer;}",
    ".cmz-countries label:hover{background:var(--paper);}",
    ".cmz-countries label.nd{color:var(--ink2);}",
    ".cmz-countries label small{margin-left:auto; font-size:11px; color:var(--ink2);}",
    ".cmz-countries label small.onc{color:var(--navy); font-weight:700;}",
    "[data-theme=\"dark\"] .cmz-countries label small.onc{color:var(--blue);}",
    ".cmz-cat{margin-bottom:16px;}",
    ".cmz-ind{padding:10px 12px; border:1px solid var(--hair); border-radius:10px; margin-bottom:8px;}",
    ".cmz-ind.sel{border-color:var(--blue); box-shadow:0 0 0 1px var(--blue) inset;}",
    ".cmz-ind .nm{font-weight:700; font-size:14px;}",
    ".cmz-ind .ex{font-size:12.5px; color:var(--ink2); line-height:1.4; margin:2px 0 6px;}",
    ".cmz-vers{display:flex; flex-wrap:wrap; gap:6px;}",
    ".cmz-vers button{border:1px solid var(--hair); background:var(--paper); color:var(--ink); border-radius:8px; padding:6px 10px; font:600 12.5px \"Avenir Next\",\"Avenir\",\"Nunito Sans\",sans-serif; cursor:pointer; text-align:left;}",
    ".cmz-vers button small{display:block; font-weight:400; font-size:11px; color:var(--ink2);}",
    ".cmz-vers button.on{background:var(--navy); border-color:var(--navy); color:#fff;}",
    ".cmz-vers button.on small{color:#D8E4EF;}",
    ".cmz-foot{display:flex; align-items:center; gap:12px; padding:14px 22px; border-top:1px solid var(--hair);}",
    ".cmz-cov{flex:1; font-size:13px; color:var(--ink2); line-height:1.45;}",
    ".cmz-cov b{color:var(--ink);}",
    ".cmz-cov .miss{color:#B5543A;}",
    "[data-theme=\"dark\"] .cmz-cov .miss{color:#E39A84;}",
    ".cmz-btn{border:1px solid var(--hair); background:var(--panel); color:var(--ink); border-radius:9px; padding:9px 16px; font:700 13.5px \"Avenir Next\",\"Avenir\",\"Nunito Sans\",sans-serif; cursor:pointer;}",
    ".cmz-btn.primary{background:var(--navy); border-color:var(--navy); color:#fff;}",
    ".cmz-btn:disabled{opacity:.45; cursor:not-allowed;}",
    ".cmz-x:focus-visible,.cmz-btn:focus-visible,.cmz-vers button:focus-visible,.cmz-groups button:focus-visible{outline:2px solid var(--blue); outline-offset:2px;}",
    "@media (max-width:760px){ .cmz-body{grid-template-columns:1fr; overflow:auto;} .cmz-col{overflow:visible;} .cmz-col + .cmz-col{border-left:none; border-top:1px solid var(--hair);} .cmz-foot{flex-wrap:wrap;} .cmz-cov{flex-basis:100%;} }"
  ].join("\n");

  var MONTHS = ["January","February","March","April","May","June","July","August","September","October","November","December"];
  function esc(s){ return String(s == null ? "" : s).replace(/[&<>"']/g, function(c){ return { "&":"&amp;", "<":"&lt;", ">":"&gt;", "\"":"&quot;", "'":"&#39;" }[c]; }); }
  function fmtLong(p){
    var mm = /^(\d{4})-(\d{2})$/.exec(p || "");
    if(mm) return MONTHS[+mm[2] - 1] + " " + mm[1];
    return ctx && ctx.fmtPeriod ? ctx.fmtPeriod(p) : String(p);
  }

  function create(opts){
    ctx = opts;
    var T = opts.text || {};
    var title = T.title || "Add to chart", verb = T.verb || "Add", dest = T.dest || "to chart";
    var onTag = T.onTag || "On chart", already = T.already || "Already on the chart";
    var missNote = T.missNote || "will show as No data";
    var allowRemove = opts.allowRemove !== false;
    var countries = function(){ return opts.countries(); };

    if(!document.getElementById("cmzStyle")){
      var st = document.createElement("style"); st.id = "cmzStyle"; st.textContent = CSS;
      document.head.appendChild(st);
    }
    var el = document.getElementById("cmChooser");
    if(!el){
      el = document.createElement("div");
      el.className = "cmz-back"; el.id = "cmChooser"; el.hidden = true;
      el.setAttribute("role", "dialog"); el.setAttribute("aria-modal", "true"); el.setAttribute("aria-labelledby", "cmzTitle");
      el.innerHTML = "<div class='cmz'>" +
        "<div class='cmz-head'><h2 id='cmzTitle'>" + esc(title) + "</h2><button type='button' class='cmz-x' id='cmzClose' aria-label='Close'>&times;</button></div>" +
        "<div class='cmz-search'><input type='text' id='cmzSearch' placeholder='Search countries or indicators, for example &quot;HICP Italy&quot; or &quot;unemployment&quot;' aria-label='Search countries or indicators' autocomplete='off'></div>" +
        "<div class='cmz-body'><div class='cmz-col'><h3>Countries <span class='cmz-n' id='cmzCount'></span></h3><div class='cmz-groups' id='cmzGroups'></div><div class='cmz-countries' id='cmzCountries'></div></div>" +
        "<div class='cmz-col'><h3>Indicator</h3><div id='cmzInds'></div></div></div>" +
        "<div class='cmz-foot'><div class='cmz-cov' id='cmzCov' aria-live='polite'>Choose countries and an indicator.</div>" +
        "<button type='button' class='cmz-btn' id='cmzCancel'>Cancel</button><button type='button' class='cmz-btn primary' id='cmzAdd' disabled>" + esc(title) + "</button></div></div>";
      document.body.appendChild(el);
    }
    function $(id){ return document.getElementById(id); }

    var cz = { countries: [], ind: -1, ver: 0, q: "" };
    function version(){ return cz.ind < 0 ? null : CHOOSER[cz.ind].v[cz.ver]; }
    function isOn(c, v){ return !!opts.isOn(c, v); }
    function latest(v, cs){
      var best = null;
      (cs && cs.length ? cs : countries()).forEach(function(c){
        var k = v.key(c), lt = k ? opts.latest(c, k) : null;
        if(lt && (!best || lt > best)) best = lt;
      });
      return best;
    }
    function words(){ return cz.q.toLowerCase().split(/\s+/).filter(Boolean); }
    function isCountryWord(w){ return countries().some(function(c){ return c.toLowerCase().indexOf(w) === 0; }); }
    function renderGroups(){
      $("cmzGroups").innerHTML = GROUPS.map(function(g, i){
        var on = g.members.every(function(c){ return cz.countries.indexOf(c) !== -1; });
        return "<button type='button' data-g='" + i + "' class='" + (on ? "on" : "") + "' aria-pressed='" + on + "'>" + esc(g.name) + " (" + g.members.length + ")</button>";
      }).join("");
    }
    function renderCount(){ $("cmzCount").textContent = cz.countries.length ? cz.countries.length + " chosen" : ""; }
    function renderCountries(){
      var v = version(), ws = words().filter(isCountryWord);
      var list = countries().slice().sort(function(a, b){ return a.localeCompare(b); }).filter(function(c){
        return !ws.length || ws.some(function(w){ return c.toLowerCase().indexOf(w) === 0; });
      });
      $("cmzCountries").innerHTML = list.map(function(c){
        var on = cz.countries.indexOf(c) !== -1, hasIt = !v || !!v.key(c);
        var already = v && isOn(c, v);
        return "<label class='" + (hasIt ? "" : "nd") + "'><input type='checkbox' data-c='" + esc(c) + "'" + (on ? " checked" : "") + "> " + esc(c) + (already ? "<small class='onc'>" + esc(onTag) + "</small>" : (hasIt ? "" : "<small>No data</small>")) + "</label>";
      }).join("") || "<p class='cm-status'>No country matches.</p>";
      renderCount();
    }
    function renderInds(){
      var ws = words().filter(function(w){ return !isCountryWord(w); });
      var html = "", lastCat = "";
      CHOOSER.forEach(function(ind, i){
        var text = (ind.nm + " " + ind.ex + " " + ind.cat + " " + ind.v.map(function(v){ return v.k + " " + v.sub + " " + ((opts.label && opts.label(v.base)) || ""); }).join(" ")).toLowerCase();
        if(ws.length && !ws.every(function(w){ return text.indexOf(w) !== -1; })) return;
        var vers = ind.v.map(function(v, j){ return { v: v, j: j, lt: latest(v, cz.countries) }; }).filter(function(x){ return x.lt || (cz.ind === i && cz.ver === x.j); });   // versions none of the chosen countries publish are left out
        if(!vers.length) return;
        if(ind.cat !== lastCat){ html += (lastCat ? "</div>" : "") + "<div class='cmz-cat'><h3>" + esc(ind.cat) + "</h3>"; lastCat = ind.cat; }
        html += "<div class='cmz-ind" + (cz.ind === i ? " sel" : "") + "'><div class='nm'>" + esc(ind.nm) + "</div><div class='ex'>" + esc(ind.ex) + "</div><div class='cmz-vers'>" +
          vers.map(function(x){
            var on = cz.ind === i && cz.ver === x.j;
            var sub = (x.v.sub ? x.v.sub + ", " : "") + (x.lt ? "latest " + fmtLong(x.lt) : "no data for these countries");
            return "<button type='button' data-i='" + i + "' data-v='" + x.j + "' data-base='" + x.v.base + "' class='" + (on ? "on" : "") + "' aria-pressed='" + on + "'>" + esc(x.v.k) + "<small>" + esc(sub) + "</small></button>";
          }).join("") + "</div></div>";
      });
      $("cmzInds").innerHTML = html ? html + "</div>" : "<p class='cm-status'>No indicator matches. Try a shorter word.</p>";
    }
    function plan(){
      var v = version();
      if(!v) return { adds: [], drops: [] };
      var adds = cz.countries.filter(function(c){ return !isOn(c, v) && (opts.addMissing !== false || !!v.key(c)); });
      var drops = allowRemove ? countries().filter(function(c){ return isOn(c, v) && cz.countries.indexOf(c) === -1; }) : [];
      return { adds: adds, drops: drops };
    }
    function renderCov(){
      var btn = $("cmzAdd"), cov = $("cmzCov"), v = version();
      if(!v || (!cz.countries.length && !(allowRemove && countries().some(function(c){ return isOn(c, v); })))){
        cov.textContent = !cz.countries.length && !v ? "Choose countries and an indicator." : (!cz.countries.length ? "Now choose one or more countries." : "Now choose an indicator.");
        btn.disabled = true; btn.textContent = title; return;
      }
      var miss = cz.countries.filter(function(c){ return !v.key(c); }), n = cz.countries.length, lt = latest(v, cz.countries);
      var p = plan(), adds = p.adds.length, drops = p.drops.length;
      cov.innerHTML = "<b>" + esc(CHOOSER[cz.ind].nm + ", " + v.k) + "</b>: " + (n - miss.length) + " of " + n + " " + (n === 1 ? "has" : "have") + " data" + (lt ? ", latest " + esc(fmtLong(lt)) : "") + "." +
        (miss.length ? " <span class='miss'>No data for " + esc(miss.join(", ")) + "; " + (miss.length === 1 ? "it" : "they") + " " + esc(missNote) + ".</span>" : "");
      var eligible = opts.addMissing === false ? n - miss.length : n;
      btn.disabled = !adds && !drops;
      btn.textContent = !adds && !drops ? (eligible ? already : title)
        : (drops && !adds ? "Remove " + drops + " from " + dest.replace(/^to /, "")
        : (drops ? verb + " " + adds + ", remove " + drops : (adds === eligible ? verb + " " + adds + " " + dest : verb + " " + adds + " more " + dest)));
    }
    function render(){ renderGroups(); renderCountries(); renderInds(); renderCov(); }
    function findVersion(metric){
      for(var i = 0; i < CHOOSER.length; i++){
        for(var j = 0; j < CHOOSER[i].v.length; j++){
          var v = CHOOSER[i].v[j];
          if(v.base === metric || countries().some(function(c){ return v.key(c) === metric; })) return [i, j];
        }
      }
      return null;
    }
    function open(){
      cz = { countries: [], ind: -1, ver: 0, q: "" };
      var on = opts.initial ? opts.initial() : [];
      on.forEach(function(x){ if(cz.countries.indexOf(x.country) === -1) cz.countries.push(x.country); });
      var metrics = on.map(function(x){ return x.metric; }).filter(function(m, i, a){ return a.indexOf(m) === i; });
      var found = metrics.length ? findVersion(metrics[0]) : null;
      if(found && metrics.every(function(m){ var f = findVersion(m); return f && f[0] === found[0] && f[1] === found[1]; })){ cz.ind = found[0]; cz.ver = found[1]; }
      else if(metrics.length > 1){ cz.countries = []; }   // a mix of indicators: start clean, nothing is removed
      $("cmzSearch").value = "";
      render(); el.hidden = false;
      setTimeout(function(){ $("cmzSearch").focus(); }, 30);
    }
    function close(){ el.hidden = true; if(opts.onClose) opts.onClose(); }

    $("cmzClose").addEventListener("click", close);
    $("cmzCancel").addEventListener("click", close);
    el.addEventListener("click", function(e){ if(e.target === el) close(); });
    document.addEventListener("keydown", function(e){ if(e.key === "Escape" && !el.hidden) close(); });
    $("cmzSearch").addEventListener("input", function(e){
      cz.q = e.target.value;
      var ws = words();
      ws.forEach(function(w){   // an exact country name ticks it ("HICP Italy" picks Italy)
        var c = countries().filter(function(x){ return x.toLowerCase() === w; })[0];
        if(c && cz.countries.indexOf(c) === -1) cz.countries.push(c);
      });
      var hits = [];            // a version named exactly selects it when only one matches ("HICP", "PCE")
      CHOOSER.forEach(function(ind, i){ ind.v.forEach(function(v, j){ if(ws.indexOf(v.k.toLowerCase()) !== -1) hits.push([i, j]); }); });
      if(hits.length === 1){ cz.ind = hits[0][0]; cz.ver = hits[0][1]; }
      render();
    });
    $("cmzGroups").addEventListener("click", function(e){
      var b = e.target.closest("button"); if(!b) return;
      var g = GROUPS[+b.dataset.g].members, on = g.every(function(c){ return cz.countries.indexOf(c) !== -1; });
      if(on) cz.countries = cz.countries.filter(function(c){ return g.indexOf(c) === -1; });
      else g.forEach(function(c){ if(cz.countries.indexOf(c) === -1) cz.countries.push(c); });
      render();
    });
    $("cmzCountries").addEventListener("change", function(e){
      var c = e.target.dataset.c; if(!c) return;
      if(e.target.checked){ if(cz.countries.indexOf(c) === -1) cz.countries.push(c); }
      else cz.countries = cz.countries.filter(function(x){ return x !== c; });
      renderGroups(); renderInds(); renderCov(); renderCount();
    });
    $("cmzInds").addEventListener("click", function(e){
      var b = e.target.closest("button[data-i]"); if(!b) return;
      cz.ind = +b.dataset.i; cz.ver = +b.dataset.v;
      render();
    });
    $("cmzAdd").addEventListener("click", function(){
      var v = version(); if(!v) return;
      var p = plan();
      p.adds.sort(function(a, b){ return a.localeCompare(b); });
      opts.commit(v, p.adds, p.drops);
      el.hidden = true;
      if(opts.onClose) opts.onClose();
    });

    return { open: open, close: close, el: el, state: function(){ return cz; }, version: version, findVersion: findVersion };
  }

  window.EAChooser = { CHOOSER: CHOOSER, GROUPS: GROUPS, measureFromLabel: measureFromLabel, create: create };
})();
