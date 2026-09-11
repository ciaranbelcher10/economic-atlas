/* ==========================================================================
   The Economic Atlas — mobile.js
   Loaded on every page after the page's own scripts. Almost everything here
   is gated behind an isMobile() check and feature-detects the elements it
   needs, so this file is safe to include sitewide: it does nothing on
   pages/sections it doesn't recognise, and does nothing at all on
   desktop/tablet widths.
   The one deliberate exception is the homepage "Latest:" ticker
   (initHomeTicker) below — it's meant to run on every width, desktop
   included, despite the file name.
   ========================================================================== */
(function(){
  "use strict";
  function isMobile(){ return window.matchMedia("(max-width:760px)").matches; }
  function $(sel, root){ return (root||document).querySelector(sel); }
  function $all(sel, root){ return Array.prototype.slice.call((root||document).querySelectorAll(sel)); }

  /* ------------------------------------------------------------------
     1. PERSISTENT MOBILE TOOL BAR
     ------------------------------------------------------------------ */
  function buildToolbar(){
    if(!isMobile() || document.getElementById("mobToolbar")) return;
    var navTop = document.querySelector("nav.top");
    if(!navTop) return;
    var page = (location.pathname.split("/").pop() || "index").replace(".html","") || "index";
    var isCountryPage = !!document.querySelector("nav.cat");
    var tools = [
      { href:"index",     label:"Countries", ic:"\uD83C\uDF0D", match:function(p){ return p==="index" || isCountryPage; } },
      { href:"compare",   label:"Compare",   ic:"\u2696\uFE0F",  match:function(p){ return p==="compare"; } },
      { href:"dashboard", label:"Dashboard", ic:"\uD83D\uDCCC",  match:function(p){ return p==="dashboard"; } },
      { href:"chartmaker",label:"Chartmaker",ic:"\uD83D\uDCC8",  match:function(p){ return p==="chartmaker"; } },
      { href:"calendar",  label:"Calendar",  ic:"\uD83D\uDDD3\uFE0F", match:function(p){ return p==="calendar"; } }
    ];
    var bar = document.createElement("nav");
    bar.id = "mobToolbar";
    bar.setAttribute("aria-label","Tools");
    tools.forEach(function(t){
      var a = document.createElement("a");
      a.href = t.href;
      if(t.match(page)) a.className = "active";
      a.innerHTML = '<span class="ic" aria-hidden="true">'+t.ic+'</span>'+t.label;
      bar.appendChild(a);
    });
    navTop.insertAdjacentElement("afterend", bar);
  }

  /* ------------------------------------------------------------------
     2. HOMEPAGE MAP — calmer entrance caption
     ------------------------------------------------------------------ */
  function addMapCaption(){
    if(!isMobile()) return;
    var legend = document.querySelector(".mini-legend");
    if(!legend || document.querySelector(".mob-map-cap")) return;
    var cap = document.createElement("p");
    cap.className = "mob-map-cap";
    cap.textContent = "Tap any coloured country to explore its page.";
    legend.parentElement.insertBefore(cap, legend);
  }

  var TICKER_COUNTRIES = [
    { file:"data.json",     slug:"uk",         name:"UK",           flag:"\uD83C\uDDEC\uD83C\uDDE7" },
    { file:"data-de.json",  slug:"germany",    name:"Germany",      flag:"\uD83C\uDDE9\uD83C\uDDEA" },
    { file:"data-jp.json",  slug:"japan",      name:"Japan",        flag:"\uD83C\uDDEF\uD83C\uDDF5" },
    { file:"data-fr.json",  slug:"france",     name:"France",       flag:"\uD83C\uDDEB\uD83C\uDDF7" },
    { file:"data-br.json",  slug:"brazil",     name:"Brazil",       flag:"\uD83C\uDDE7\uD83C\uDDF7" },
    { file:"data-in.json",  slug:"india",      name:"India",        flag:"\uD83C\uDDEE\uD83C\uDDF3" },
    { file:"data-us.json",  slug:"us",         name:"US",           flag:"\uD83C\uDDFA\uD83C\uDDF8" },
    { file:"data-ca.json",  slug:"canada",     name:"Canada",       flag:"\uD83C\uDDE8\uD83C\uDDE6" },
    { file:"data-au.json",  slug:"australia",  name:"Australia",    flag:"\uD83C\uDDE6\uD83C\uDDFA" },
    { file:"data-kr.json",  slug:"southkorea", name:"South Korea",  flag:"\uD83C\uDDF0\uD83C\uDDF7" },
    { file:"data-mx.json",  slug:"mexico",     name:"Mexico",       flag:"\uD83C\uDDF2\uD83C\uDDFD" },
    { file:"data-za.json",  slug:"southafrica",name:"South Africa", flag:"\uD83C\uDDFF\uD83C\uDDE6" }
  ];
  var TICKER_SHOW_COUNT = 10; // always show the N most recently updated metrics

  var METRIC_SHORT_LABELS = {
    gdp_level:"GDP", gdp_real:"Real GDP", gdp_growth:"GDP Growth", productivity:"Productivity",
    cpi:"CPI", cpih:"CPIH", cpi_mom:"CPI (MoM)", unemployment:"Unemployment", employment:"Employment",
    inactivity:"Inactivity", debt_gdp:"Debt/GDP", net_debt:"Net Debt", deficit:"Deficit",
    unemployment_1624:"Youth Unemployment", debt_interest:"Debt Interest", trade_balance:"Trade Balance",
    current_account:"Current Account", bond_yield_10y:"10Y Bond Yield", policy_rate:"Policy Rate",
    business_confidence:"Business Confidence"
  };
  // Trims trailing "(SERIES_CODE)" / "(source)" parentheticals for the rare
  // series not covered by the short-label map above.
  function shortSeriesLabel(label){
    var s = label;
    var stripped = s.replace(/\s*\([^()]*\)\s*$/, "");
    while(stripped !== s){ s = stripped; stripped = s.replace(/\s*\([^()]*\)\s*$/, ""); }
    return s || label;
  }
  function metricShortLabel(key, fallbackLabel){
    return METRIC_SHORT_LABELS[key] || (fallbackLabel ? shortSeriesLabel(fallbackLabel) : key);
  }

  // Generic value formatter: percentages as-is, currency-prefixed units
  // (£/$/€ + m/bn/tn scale) compacted to the largest sensible unit,
  // anything else shown with its unit suffix as given.
  function formatTickerValue(value, unit){
    if(value == null) return null;
    unit = unit || "";
    if(unit.indexOf("%") !== -1) return value.toFixed(1) + "%";
    var symMatch = unit.match(/^([\u00a3$\u20ac\u00a5])/);
    if(symMatch){
      var sym = symMatch[1];
      var scaleSuffix = unit.replace(/^[\u00a3$\u20ac\u00a5]/, "").trim();
      var scaleMultiplier = {m:1e6, bn:1e9, tn:1e12}[scaleSuffix] || 1;
      var sign = value < 0 ? "\u2212" : "";
      var absValue = Math.abs(value) * scaleMultiplier;
      if(absValue >= 1e12) return sign + sym + (absValue/1e12).toFixed(2) + "tn";
      if(absValue >= 1e9) return sign + sym + (absValue/1e9).toFixed(2) + "bn";
      if(absValue >= 1e6) return sign + sym + (absValue/1e6).toFixed(1) + "m";
      return sign + sym + absValue.toFixed(0);
    }
    return value.toFixed(2) + (unit ? " " + unit : "");
  }

  function fetchTickerFacts(cb){
    var allFacts = [];
    var pending = TICKER_COUNTRIES.length;
    var now = Date.now();
    function done(){ pending--; if(pending === 0) cb(allFacts); }
    TICKER_COUNTRIES.forEach(function(c){
      fetch(c.file, {cache:"no-cache"}).then(function(r){
        if(!r.ok) throw new Error("HTTP "+r.status);
        return r.json();
      }).then(function(data){
        var series = data.series || {};
        var meta = data.new_points_meta || {};
        Object.keys(meta).forEach(function(key){
          var m = meta[key], s = series[key];
          if(!s || !m || !m.first_seen || !s.points || !s.points.length) return;
          var ageDays = (now - new Date(m.first_seen).getTime()) / 86400000;
          if(ageDays < 0) return; // ignore clock-skew/future-dated entries only
          var latest = s.points[s.points.length - 1];
          var valueStr = formatTickerValue(latest[1], s.unit);
          if(valueStr == null) return;
          var dt = new Date(m.first_seen);
          var dd = String(dt.getUTCDate()).padStart(2,"0");
          var mm = String(dt.getUTCMonth()+1).padStart(2,"0");
          allFacts.push({
            country:c.name, slug:c.slug, flag:c.flag,
            metricShort:metricShortLabel(key, s.label),
            valueStr:valueStr, dateStr:dd+"/"+mm, firstSeen:m.first_seen
          });
        });
        done();
      }).catch(function(){ done(); });
    });
  }

  function tickerFactHtml(f){
    return '<a class="ht-item" href="'+f.slug+'">'+f.flag+' <b>'+f.country+'</b> '+f.metricShort
      + ' <b class="ht-value">'+f.valueStr+'</b> <span class="ht-date">'+f.dateStr+'</span></a>';
  }

  function initHomeTicker(){
    if(!document.querySelector(".hero-h1")) return;
    if(document.getElementById("homeTicker") || document.getElementById("homeTicker_pending")) return;
    var subline = document.querySelector(".subline");
    if(!subline) return;
    var marker = document.createElement("div");
    marker.id = "homeTicker_pending";
    marker.style.display = "none";
    subline.insertAdjacentElement("afterend", marker);

    fetchTickerFacts(function(allFacts){
      allFacts.sort(function(a,b){ return new Date(b.firstSeen) - new Date(a.firstSeen); });
      // De-dupe on slug+metric, keeping the most recent occurrence, so the
      // same series can't appear twice and read as a copy-paste error.
      var seen = {};
      var deduped = [];
      allFacts.forEach(function(f){
        var k = f.slug + "|" + f.metricShort;
        if(seen[k]) return;
        seen[k] = true;
        deduped.push(f);
      });
      var combined = deduped.slice(0, TICKER_SHOW_COUNT);
      if(!combined.length) return;

      var itemsHtml = combined.map(tickerFactHtml).join("");
      var wrap = document.createElement("div");
      wrap.id = "homeTicker";
      wrap.setAttribute("aria-label", "Recent updates");
      wrap.innerHTML =
        '<span class="ht-prefix"><span class="pulse" aria-hidden="true"></span>Latest:</span>' +
        '<div class="ht-viewport"><div class="ht-track">' + itemsHtml + itemsHtml + '</div></div>';
      marker.insertAdjacentElement("afterend", wrap);

      // Pause the auto-scroll on touch so a tap reliably lands on the
      // item the user meant to hit, rather than one that's mid-slide.
      var track = wrap.querySelector(".ht-track");
      wrap.addEventListener("touchstart", function(){ track.style.animationPlayState = "paused"; }, {passive:true});
      wrap.addEventListener("touchend", function(){ track.style.animationPlayState = "running"; }, {passive:true});
    });
  }


  function initSearchPlaceholderRotation(){
    var input = document.getElementById("hqnSearch");
    if(!input || input._mobRotateAttached) return;
    input._mobRotateAttached = true;
    var examples = [
      "Try \u201cJapan inflation\u201d\u2026",
      "Try \u201cUK unemployment\u201d\u2026",
      "Try \u201cGermany GDP\u201d\u2026",
      "Jump straight to a country\u2026",
      "Try \u201cBrazil\u201d or \u201cIndia\u201d\u2026"
    ];
    var i = 0;
    setInterval(function(){
      if(document.activeElement === input || input.value) return;
      i = (i+1) % examples.length;
      input.setAttribute("placeholder", examples[i]);
    }, 2600);
  }

  function initScrollCatch(){
    if(!document.querySelector(".hero-h1")) return;
    if(localStorage.getItem("eatlas_scrollcatch_seen")) return;
    if(window._mobScrollCatchAttached) return;
    window._mobScrollCatchAttached = true;
    var shown = false;
    window.addEventListener("scroll", function onScroll(){
      if(shown) return;
      if(window.scrollY < window.innerHeight * 0.9) return;
      shown = true;
      window.removeEventListener("scroll", onScroll);

      var links = $all("#macroPanel a[href]").filter(function(a){ return a.getAttribute("href") !== "index"; });

      var bar = document.createElement("div");
      bar.id = "homeScrollCatch";
      bar.innerHTML =
        '<div class="sc-results" id="scrollCatchResults" hidden></div>' +
        '<div class="sc-row">' +
          '<input type="text" id="scrollCatchInput" placeholder="Jump to a country\u2026" autocomplete="off">' +
          '<button type="button" id="scrollCatchClose" aria-label="Dismiss">&times;</button>' +
        '</div>';
      document.body.appendChild(bar);
      requestAnimationFrame(function(){ bar.classList.add("visible"); });

      var input = document.getElementById("scrollCatchInput");
      var results = document.getElementById("scrollCatchResults");
      input.addEventListener("input", function(){
        var q = input.value.trim().toLowerCase();
        if(!q){ results.hidden = true; results.innerHTML = ""; return; }
        var matches = links.filter(function(a){ return a.textContent.toLowerCase().indexOf(q) !== -1; }).slice(0, 6);
        results.innerHTML = matches.length
          ? matches.map(function(a){ return '<a href="'+a.getAttribute("href")+'">'+a.textContent+'</a>'; }).join("")
          : '<p class="sc-none">No matching country.</p>';
        results.hidden = false;
      });

      document.getElementById("scrollCatchClose").addEventListener("click", function(){
        bar.classList.remove("visible");
        setTimeout(function(){ bar.remove(); }, 250);
        localStorage.setItem("eatlas_scrollcatch_seen", "1");
      });
    }, {passive:true});
  }

  /* ------------------------------------------------------------------
     3. COUNTRY PAGES — swipe between sections, dot indicator
     Hooks into the page's own global showSec(name) function rather
     than re-implementing section switching.
     ------------------------------------------------------------------ */
  /* ------------------------------------------------------------------
     3b. COUNTRY PAGES — collapsed map, tap to expand
     ------------------------------------------------------------------ */
  /* ------------------------------------------------------------------
     2. HOMEPAGE — fast paths to a country besides the map
     Scrapes the existing (desktop) mega-menu's country links as the
     data source, so nothing is duplicated or hardcoded — if a country
     is added to the dropdown, it automatically appears here too.
     ------------------------------------------------------------------ */
  // Country pages: the mini-map is absolutely positioned (top:0, relative
  // to its header), so it naturally starts wherever the header itself
  // begins -- which is now well below our search box, since that sits
  // as a separate element before the header. Rather than guessing a
  // fixed pixel offset (fragile against font/zoom/content differences),
  // this measures both elements' real on-screen positions and nudges
  // the map up by exactly the gap between them, matching the site's own
  // existing pattern for this kind of thing (see positionCountriesPanel
  // in compare.html).
  function alignCountryMapWithSearch(){
    var box = document.getElementById("homeQuickNav");
    var mapWrap = document.getElementById("miniMapWrap");
    if(!box || !mapWrap) return;
    var header = mapWrap.closest("header.page");
    if(!header) return;
    var boxRect = box.getBoundingClientRect();
    var headerRect = header.getBoundingClientRect();
    var offset = boxRect.top - headerRect.top;
    mapWrap.style.top = offset + "px";
  }

  function initHomeQuickNav(){
    var header = document.querySelector(".hero-h1") ? document.querySelector("header.page")
               : document.querySelector("header.page.with-map");
    if(!header || document.getElementById("homeQuickNav")) return;
    var currentSlug = (location.pathname.replace(/^\/+|\/+$/g,"").split("/").pop() || "index").replace(/\.html$/,"");
    var links = $all("#macroPanel a[href]").filter(function(a){
      var href = a.getAttribute("href");
      return href !== "index" && href !== currentSlug;
    });
    if(!links.length) return;
    var isCountryPage = !document.querySelector(".hero-h1");

    var placeholder = isCountryPage ? "Jump to another country\u2026" : "Jump straight to a country\u2026";
    var box = document.createElement("div");
    box.id = "homeQuickNav";
    box.innerHTML =
      '<div class="hqn-searchwrap">' +
        '<input type="text" id="hqnSearch" placeholder="'+placeholder+'" autocomplete="off">' +
        '<div class="hqn-results" id="hqnResults" hidden></div>' +
      '</div>';
    header.insertAdjacentElement("beforebegin", box);

    var input = document.getElementById("hqnSearch");
    var results = document.getElementById("hqnResults");
    input.addEventListener("input", function(){
      var q = input.value.trim().toLowerCase();
      if(!q){ results.hidden = true; results.innerHTML = ""; return; }
      var matches = links.filter(function(a){ return a.textContent.toLowerCase().indexOf(q) !== -1; }).slice(0, 8);
      if(!matches.length){
        results.innerHTML = '<p class="hqn-none">No matching country.</p>';
      } else {
        results.innerHTML = matches.map(function(a){
          return '<a href="'+a.getAttribute("href")+'">'+a.textContent+'</a>';
        }).join("");
      }
      results.hidden = false;
    });
  }

  function initMapCollapse(){
    if(!isMobile()) return;
    var wrap = document.getElementById("miniMapWrap");
    if(!wrap || wrap._mobCollapseAttached) return;
    wrap._mobCollapseAttached = true;
    var hint = wrap.querySelector(".minihint");
    wrap.addEventListener("click", function(e){
      if(!wrap.classList.contains("mm-expanded")){
        e.preventDefault();
        e.stopPropagation();
        wrap.classList.add("mm-expanded");
        if(hint) hint.textContent = "Collapse";
      }
      // once expanded, further taps behave normally (e.g. selecting a country)
    }, true);
  }

  function initCountrySwipe(){
    var nav = document.querySelector("nav.cat");
    if(!isMobile() || !nav || typeof window.showSec !== "function") return;
    var btns = $all("button", nav);
    if(!btns.length) return;

    var hint = document.querySelector(".sec-swipehint");
    if(!hint){
      hint = document.createElement("div");
      hint.className = "sec-swipehint";
      btns.forEach(function(){ hint.appendChild(document.createElement("span")); });
      nav.insertAdjacentElement("afterend", hint);
    }

    function syncDots(){
      var activeIdx = btns.findIndex(function(b){ return b.classList.contains("active"); });
      $all("span", hint).forEach(function(dot, i){ dot.classList.toggle("active", i===activeIdx); });
    }
    var mo = new MutationObserver(syncDots);
    btns.forEach(function(b){ mo.observe(b, {attributes:true, attributeFilter:["class"]}); });
    syncDots();

    var startX = null, startY = null;
    var main = document.querySelector("main") || document.body;
    if(!main._mobSwipeAttached){
      main._mobSwipeAttached = true;
      main.addEventListener("touchstart", function(e){
        if(e.touches.length!==1) return;
        startX = e.touches[0].clientX; startY = e.touches[0].clientY;
      }, {passive:true});
      main.addEventListener("touchend", function(e){
        if(startX===null) return;
        var dx = e.changedTouches[0].clientX - startX;
        var dy = e.changedTouches[0].clientY - startY;
        startX = null;
        if(Math.abs(dx) < 60 || Math.abs(dx) < Math.abs(dy)*1.5) return; // not a clean horizontal swipe
        var curBtns = $all("button", nav);
        var idx = curBtns.findIndex(function(b){ return b.classList.contains("active"); });
        var next = dx < 0 ? idx+1 : idx-1;
        if(next < 0 || next >= curBtns.length) return;
        window.showSec(curBtns[next].dataset.sec);
        curBtns[next].scrollIntoView({inline:"center", block:"nearest"});
      }, {passive:true});
    }
  }

  /* ------------------------------------------------------------------
     4. TRADE PARTNER CHART — desktop-feature note
     ------------------------------------------------------------------ */
  function addTradeNote(){
    if(!isMobile()) return;
    $all(".tpm-layout").forEach(function(layout){
      // Note is inserted as the PREVIOUS SIBLING of .tpm-layout (not a
      // descendant), so the dedupe check must look at the sibling, not
      // inside layout itself — checking layout.querySelector() here was
      // the earlier bug that let this note duplicate on every re-init pass.
      var prev = layout.previousElementSibling;
      if(prev && prev.classList && prev.classList.contains("tpm-mobile-note")) return;
      var note = document.createElement("p");
      note.className = "tpm-mobile-note";
      note.textContent = "Showing the ranked list. A geographic map and radial network view of these trade relationships is also available on the desktop and tablet site.";
      layout.insertAdjacentElement("beforebegin", note);
    });
  }

  /* Trade sections — "biggest partner" fact, read straight off the
     already-rendered #1 row of the ranking list (zero new fetches,
     zero re-parsing of raw trade figures). */
  function renderTradePartnerBanner(list){
    var firstRow = list.querySelector(".tpm-rankrow");
    var wrap = list.closest(".tpm-ranking");
    if(!wrap) return;
    var existing = wrap.querySelector(".tpm-partner-banner");
    if(!firstRow){ if(existing) existing.remove(); return; }
    var name = firstRow.querySelector(".tpm-rankname");
    var value = firstRow.querySelector(".tpm-rankvalue");
    if(!name || !value) return;
    var banner = existing;
    if(!banner){
      banner = document.createElement("p");
      banner.className = "tpm-partner-banner";
      var title = wrap.querySelector("h4");
      (title || list).insertAdjacentElement(title ? "afterend" : "beforebegin", banner);
    }
    banner.innerHTML = '<b>Biggest partner:</b> ' + name.textContent.trim() + ' ' + value.textContent.trim();
  }
  function watchTradePartnerLists(){
    $all(".tpm-ranklist").forEach(function(list){
      if(list._mobPartnerWatched) return;
      list._mobPartnerWatched = true;
      renderTradePartnerBanner(list);
      var mo = new MutationObserver(function(){ renderTradePartnerBanner(list); });
      mo.observe(list, {childList:true});
    });
  }

  /* ------------------------------------------------------------------
     5. COMPARE PAGE — stacked cards from the existing rank table,
     search box in the country picker.
     ------------------------------------------------------------------ */
  function tableToCards(){
    if(!isMobile()) return;
    var table = document.getElementById("rankTable");
    if(!table) return;
    var wrap = table.closest("div") || table.parentElement;
    if(!wrap) return;
    var cardsWrap = document.getElementById("cmpCardsWrap");
    if(!cardsWrap){
      cardsWrap = document.createElement("div");
      cardsWrap.id = "cmpCardsWrap";
      wrap.insertAdjacentElement("afterend", cardsWrap);
    }
    var thead = table.querySelector("thead");
    var tbody = table.querySelector("tbody");
    if(!thead || !tbody || !tbody.rows.length){
      // table not populated yet (page still fetching data) — retry shortly
      return;
    }
    var headers = $all("th", thead).map(function(th){ return th.textContent.trim(); });
    cardsWrap.innerHTML = "";
    $all("tr", tbody).forEach(function(tr){
      var cells = $all("td", tr);
      if(!cells.length) return;
      var card = document.createElement("div");
      card.className = "cmp-country-card";
      var h4 = document.createElement("h4");
      var swatch = tr.querySelector(".swatch, [style*='background']");
      var dotColor = swatch ? getComputedStyle(swatch).backgroundColor : "";
      h4.innerHTML = (dotColor ? '<span class="swatch" style="background:'+dotColor+'"></span>' : "") + cells[0].textContent.trim();
      card.appendChild(h4);
      for(var i=1;i<cells.length;i++){
        var row = document.createElement("div");
        row.className = "row";
        var lbl = document.createElement("span"); lbl.className = "lbl"; lbl.textContent = headers[i] || "";
        var val = document.createElement("span"); val.className = "val"; val.innerHTML = cells[i].innerHTML;
        row.appendChild(lbl); row.appendChild(val);
        card.appendChild(row);
      }
      cardsWrap.appendChild(card);
    });
  }
  function simplifyComparePage(){
    if(!isMobile()) return;
    // Hide the second intro paragraph by matching its text — it has no
    // distinguishing class in the markup, so a text match is more robust
    // than a fragile structural selector that could catch the wrong <p>.
    $all("p").forEach(function(p){
      if(/^Looking for a specific ranking/.test(p.textContent.trim())){
        p.classList.add("cmp-lede-hide");
      }
    });
    // Collapse each metric card's Bar/Line + Order-countries-by + Fullscreen
    // controls behind a single toggle, so the card's data is the first
    // thing visible instead of four rows of controls.
    $all(".metric-card").forEach(function(card){
      if(card.querySelector(".card-opts-toggle")) return;
      var anchor = card.querySelector(".charttoggle") || card.querySelector(".card-sort-row");
      if(!anchor) return;
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "card-opts-toggle";
      btn.innerHTML = "Chart options <span class=\"car\" aria-hidden=\"true\">\u25BE</span>";
      btn.addEventListener("click", function(){ card.classList.toggle("opts-open"); });
      anchor.insertAdjacentElement("beforebegin", btn);
    });
  }
  function watchComparePage(){
    var chartGrid = document.getElementById("chartGrid");
    if(!chartGrid) return;
    simplifyComparePage();
    var mo = new MutationObserver(function(){ simplifyComparePage(); });
    mo.observe(chartGrid, {childList:true, subtree:true});
  }

  function watchCompareTable(){
    var table = document.getElementById("rankTable");
    if(!table) return;
    tableToCards();
    var mo = new MutationObserver(function(){ tableToCards(); });
    mo.observe(table, {childList:true, subtree:true});
    window.addEventListener("resize", tableToCards);
  }

  /* Compare — "widest gap" fact banner. Reads the table's own already-
     computed .col-hi/.col-lo markers (never recalculates or re-parses
     formatted numbers itself) for the first metric column that has a
     real spread, and surfaces it as a single plain-fact line above the
     results. Neutral framing only — "widest gap", never "best/worst". */
  function renderCompareGapBanner(){
    var table = document.getElementById("rankTable");
    if(!table) return;
    var thead = table.querySelector("thead"), tbody = table.querySelector("tbody");
    if(!thead || !tbody || !tbody.rows.length) return;
    var headers = $all("th", thead);
    var banner = document.getElementById("cmpGapBanner");

    for(var col=1; col<headers.length; col++){
      var hiCell=null, loCell=null, hiRow=null, loRow=null;
      $all("tr", tbody).forEach(function(tr){
        var cells = $all("td", tr);
        var cell = cells[col];
        if(!cell) return;
        if(cell.classList.contains("col-hi")){ hiCell=cell; hiRow=tr; }
        if(cell.classList.contains("col-lo")){ loCell=cell; loRow=tr; }
      });
      if(hiCell && loCell){
        var metricLabel = headers[col].textContent.trim();
        var hiCountry = hiRow.querySelector("td.country").textContent.trim();
        var loCountry = loRow.querySelector("td.country").textContent.trim();
        var hiVal = hiCell.childNodes[0] ? hiCell.childNodes[0].textContent.trim() : hiCell.textContent.trim();
        var loVal = loCell.childNodes[0] ? loCell.childNodes[0].textContent.trim() : loCell.textContent.trim();
        if(!banner){
          banner = document.createElement("p");
          banner.id = "cmpGapBanner";
          table.insertAdjacentElement("beforebegin", banner);
        }
        banner.innerHTML = '<b>Widest gap</b> on ' + metricLabel + ': '
          + hiCountry + ' ' + hiVal + ' vs ' + loCountry + ' ' + loVal;
        return;
      }
    }
    if(banner) banner.remove();
  }
  function watchCompareGapBanner(){
    var table = document.getElementById("rankTable");
    if(!table) return;
    renderCompareGapBanner();
    var mo = new MutationObserver(renderCompareGapBanner);
    mo.observe(table, {childList:true, subtree:true});
  }

  function addPickerSearch(gridId, wrapId, inputId, placeholder){
    var grid = document.getElementById(gridId);
    if(!grid || document.getElementById(wrapId)) return;
    var wrap = document.createElement("div");
    wrap.id = wrapId;
    wrap.innerHTML = '<input type="text" id="'+inputId+'" placeholder="'+placeholder+'" autocomplete="off">';
    grid.insertAdjacentElement("beforebegin", wrap);
    document.getElementById(inputId).addEventListener("input", function(e){
      var q = e.target.value.trim().toLowerCase();
      $all("button, .dhead, p", grid).forEach(function(el){
        if(el.tagName === "P" || el.classList.contains("dhead")){
          el.style.display = q ? "none" : "";
          return;
        }
        var txt = el.textContent.toLowerCase();
        el.style.display = (!q || txt.indexOf(q) !== -1) ? "" : "none";
      });
    });
  }

  /* ------------------------------------------------------------------
     6. CALENDAR — agenda rebuild
     Reuses the page's own EVENTS map, eventsForDate(), viewYear,
     viewMonth and MONTH_NAMES globals rather than re-fetching data.
     Wraps the existing renderMonth() so both stay in sync.
     ------------------------------------------------------------------ */
  /* ------------------------------------------------------------------
     6. CALENDAR — agenda rebuild
     IMPORTANT: calendar.html's whole script is wrapped in its own IIFE
     ( <script>(function(){ ... })()</script> ), so EVENTS/renderMonth/
     eventsForDate are private closure variables and were NEVER actually
     reachable as window.EVENTS — the earlier version of this function
     checked for exactly that and silently no-op'd on every single page
     load. Rebuilt to read the already-rendered grid DOM instead (each
     .cal-cell's .cal-pill children), which needs no access to the
     page's internal variables at all and works regardless of scoping.
     ------------------------------------------------------------------ */
  var MONTH_NAMES_FULL = ["January","February","March","April","May","June","July","August","September","October","November","December"];
  var MONTH_SHORT = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  var WEEKDAY_SHORT = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"];

  /* Calendar — "Next up" fact, independent of the mobile-only agenda
     rebuild so it can run on desktop too (which keeps its normal grid).
     Shows a real date ("Tue 8 Sep") rather than just the bare day number,
     built from #calMonthLabel's own text ("September 2026") plus the
     day number already on the matched cell. */
  function renderCalendarNextUp(){
    var weeksEl = document.getElementById("calWeeks");
    var monthLabelEl = document.getElementById("calMonthLabel");
    var nextUp = document.getElementById("calNextUp");
    if(!weeksEl){ if(nextUp) nextUp.remove(); return; }
    var cells = $all(".cal-cell", weeksEl).filter(function(c){ return !c.classList.contains("other"); });
    var todayIdx = cells.findIndex(function(c){ return c.classList.contains("today"); });
    var nextCell=null, nextPillText=null;
    if(todayIdx !== -1){
      for(var i=todayIdx; i<cells.length; i++){
        var p = cells[i].querySelector(".cal-pill");
        if(p){ nextCell = cells[i]; nextPillText = p.textContent; break; }
      }
    }
    if(!nextCell){ if(nextUp) nextUp.remove(); return; }

    var isTodayCell = nextCell.classList.contains("today");
    var dateStr = "today";
    if(!isTodayCell){
      var nd = nextCell.querySelector(".cal-daynum");
      var dayNum = nd ? parseInt(nd.textContent.trim(), 10) : null;
      var parts = monthLabelEl ? monthLabelEl.textContent.trim().split(" ") : null;
      if(dayNum && parts && parts.length === 2){
        var monthIdx = MONTH_NAMES_FULL.indexOf(parts[0]);
        var year = parseInt(parts[1], 10);
        if(monthIdx !== -1 && year){
          var d = new Date(year, monthIdx, dayNum);
          dateStr = WEEKDAY_SHORT[d.getDay()] + " " + dayNum + " " + MONTH_SHORT[monthIdx];
        } else {
          dateStr = "day " + dayNum; // fallback if the label ever changes shape
        }
      }
    }
    if(!nextUp){
      nextUp = document.createElement("p");
      nextUp.id = "calNextUp";
      var anchor = monthLabelEl && monthLabelEl.closest(".cal-controls") ? monthLabelEl.closest(".cal-controls") : weeksEl;
      anchor.insertAdjacentElement("afterend", nextUp);
    }
    nextUp.innerHTML = '<b>Next up:</b> ' + nextPillText + ' \u2014 ' + dateStr;
  }
  function watchCalendarNextUp(){
    var weeksEl = document.getElementById("calWeeks");
    if(!weeksEl || weeksEl._mobNextUpWatched) return;
    weeksEl._mobNextUpWatched = true;
    renderCalendarNextUp();
    var mo = new MutationObserver(renderCalendarNextUp);
    mo.observe(weeksEl, {childList:true, subtree:true});
  }

  function initCalendarAgenda(){
    if(!isMobile()) return;
    var weeksEl = document.getElementById("calWeeks");
    if(!weeksEl) return;

    var agenda = document.getElementById("calAgenda");
    var heading = document.getElementById("calAgendaHeading");
    if(!agenda){
      heading = document.createElement("p");
      heading.id = "calAgendaHeading";
      heading.className = "cal-agenda-title";
      agenda = document.createElement("div");
      agenda.id = "calAgenda";
      var dayDetail = document.getElementById("calDayDetail");
      var anchor = dayDetail || weeksEl;
      anchor.insertAdjacentElement("beforebegin", heading);
      anchor.insertAdjacentElement("beforebegin", agenda);
    }

    function renderAgendaFromGrid(){
      var monthLabel = document.getElementById("calMonthLabel");
      heading.textContent = "This month's tracked releases";
      var cells = $all(".cal-cell", weeksEl).filter(function(c){ return !c.classList.contains("other"); });
      var html = "";
      var anyEvents = false;
      cells.forEach(function(cell){
        var pills = $all(".cal-pill", cell);
        var more = cell.querySelector(".cal-more");
        if(!pills.length && !more) return;
        anyEvents = true;
        var dayNum = cell.querySelector(".cal-daynum");
        var isToday = cell.classList.contains("today");
        var dayText = dayNum ? dayNum.textContent.trim() : "";
        html += '<div class="cal-agenda-day'+(isToday?" is-today":"")+'" data-day="'+dayText+'">';
        html += '<div class="d-head"><span class="d-num">'+dayText+'</span>'+(isToday?'<span class="d-dow">Today</span>':'')+'</div>';
        pills.forEach(function(pill, i){
          var bg = pill.style.background || "#37659E";
          html += '<div class="cal-agenda-pill" data-cell-day="'+dayText+'" data-pill-index="'+i+'" style="background:'+bg+'">';
          html += '<span class="dot" aria-hidden="true"></span>' + pill.textContent;
          html += '</div>';
        });
        if(more){
          html += '<div class="cal-agenda-more">'+more.textContent+' — full list on desktop/tablet</div>';
        }
        html += '</div>';
      });
      if(!anyEvents){
        var label = monthLabel ? monthLabel.textContent : "this month";
        html = '<p class="cal-agenda-empty">No tracked releases in '+label+'.</p>';
      }
      agenda.innerHTML = html;

      renderCalendarNextUp();

      // Wire each agenda pill to trigger the real pill's existing click
      // handler (opens the event detail view) rather than reimplementing it.
      $all(".cal-agenda-pill", agenda).forEach(function(agPill){
        agPill.addEventListener("click", function(){
          var day = this.dataset.cellDay;
          var idx = +this.dataset.pillIndex;
          var cell = cells.filter(function(c){
            var dn = c.querySelector(".cal-daynum");
            return dn && dn.textContent.trim() === day;
          })[0];
          if(!cell) return;
          var realPill = $all(".cal-pill", cell)[idx];
          if(realPill) realPill.click();
        });
      });
    }

    renderAgendaFromGrid();

    if(!window._mobCalObserverAttached){
      window._mobCalObserverAttached = true;
      var mo = new MutationObserver(function(){
        if(isMobile()) renderAgendaFromGrid();
      });
      mo.observe(weeksEl, {childList:true, subtree:true});
    }
  }

  // Fix stale "admin preview" copy now the calendar is un-gated for everyone.
  function fixStaleCalendarCopy(){
    var el = document.querySelector(".cal-email-explainer-status");
    if(el && /admin preview/i.test(el.textContent)){
      el.textContent = "This is a newer feature and still being refined — turn it on any time from the Countries panel above.";
    }
  }

  // Shorten the desktop-oriented "click a tile" instruction on mobile —
  // there's no separate explainer tile to click in the agenda view.
  function simplifyCalendarCopy(){
    if(!isMobile()) return;
    $all("p").forEach(function(p){
      if(/^Click a tile for the full explainer/.test(p.textContent.trim())){
        p.textContent = "Tap any release below for more detail.";
      }
    });
  }

  /* ------------------------------------------------------------------
     7. CHARTMAKER — hard mobile gate
     ------------------------------------------------------------------ */
  function chartmakerGate(){
    var layout = document.getElementById("cmLayout");
    if(!layout) return;
    if(!isMobile()){
      var gate = document.getElementById("cmMobileGate");
      if(gate) gate.style.display = "none";
      layout.style.display = "";
      return;
    }
    if(document.getElementById("cmMobileGate")) return;
    var gate = document.createElement("div");
    gate.id = "cmMobileGate";
    gate.innerHTML =
      '<span class="ic" aria-hidden="true">\uD83D\uDCC8</span>' +
      '<h3>Chartmaker needs a bigger screen</h3>' +
      '<p>Building and styling a custom chart — picking metrics, colours, axis titles and exporting as PNG or CSV — needs more room than a phone can comfortably give it. Open this page on a tablet or desktop and it\u2019ll be exactly as you left it.</p>' +
      '<span class="save-hint">Tip: bookmark this page now, then come back to it once you\u2019re on a bigger screen.</span>';
    layout.insertAdjacentElement("beforebegin", gate);
  }

  /* ------------------------------------------------------------------
     8. DASHBOARD — search box for "Add a metric"
     ------------------------------------------------------------------ */
  // Dashboard's "Add a metric" picker already ships with its own native
  // search box (#pickerSearch) and works correctly — no extra search
  // needed there. Only Compare's separate country-picker modal
  // (#pickerRegions) genuinely lacked one.
  function initCompareCountrySearch(){
    if(!isMobile()) return;
    addPickerSearch("pickerRegions", "pickerSearchWrap", "pickerSearch", "Search countries\u2026");
  }

  /* Dashboard — "at a glance" summary read from the already-rendered
     pinned tiles (no re-fetching what's already on the page). */
  function renderDashGlance(){
    var grid = document.getElementById("dashGrid");
    if(!grid) return;
    var tiles = $all(".tile", grid);
    var existing = document.getElementById("dashGlance");
    if(!tiles.length){ if(existing) existing.remove(); return; }
    var countries = {};
    tiles.forEach(function(t){
      var c = t.querySelector(".country");
      if(c) countries[c.textContent.trim()] = true;
    });
    var countryCount = Object.keys(countries).length;
    var glance = existing;
    if(!glance){
      glance = document.createElement("p");
      glance.id = "dashGlance";
      grid.insertAdjacentElement("beforebegin", glance);
    }
    glance.innerHTML = '<b>At a glance:</b> tracking ' + tiles.length + ' metric' + (tiles.length===1?"":"s")
      + ' across ' + countryCount + ' countr' + (countryCount===1?"y":"ies") + '.';
  }
  function watchDashGlance(){
    var grid = document.getElementById("dashGrid");
    if(!grid) return;
    renderDashGlance();
    var mo = new MutationObserver(renderDashGlance);
    mo.observe(grid, {childList:true});
  }

  /* ------------------------------------------------------------------
     init
     ------------------------------------------------------------------ */
  // Every feature in init() runs on every page, but each one only
  // applies to the specific page it targets — so one throwing (e.g. an
  // unexpected markup shape on a page nobody's tested yet) must never
  // block the rest from running. Each call is isolated individually
  // rather than wrapping the whole function, so a failure is traceable
  // to exactly which feature broke.
  function safeCall(fn){
    try { fn(); } catch(e){ if(window.console) console.error("[mobile.js]", fn.name || "anonymous", e); }
  }

  function init(){
    safeCall(buildToolbar);
    safeCall(addMapCaption);
    safeCall(initHomeQuickNav);
    safeCall(alignCountryMapWithSearch);
    safeCall(initHomeTicker);
    safeCall(initSearchPlaceholderRotation);
    safeCall(initScrollCatch);
    safeCall(initCountrySwipe);
    safeCall(initMapCollapse);
    safeCall(addTradeNote);
    safeCall(watchTradePartnerLists);
    safeCall(watchCompareTable);
    safeCall(watchCompareGapBanner);
    safeCall(watchComparePage);
    safeCall(initCompareCountrySearch);
    safeCall(initCalendarAgenda);
    safeCall(watchCalendarNextUp);
    safeCall(fixStaleCalendarCopy);
    safeCall(simplifyCalendarCopy);
    safeCall(watchDashGlance);
    safeCall(chartmakerGate);
  }

  if(document.readyState === "loading"){
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
  // Re-run the cheap, idempotent bits after async page data loads and on resize/orientation change.
  window.addEventListener("resize", function(){
    addTradeNote(); tableToCards(); chartmakerGate(); simplifyComparePage(); simplifyCalendarCopy();
    alignCountryMapWithSearch();
  });
  window.addEventListener("load", function(){
    setTimeout(init, 400); // second pass after country/compare/calendar data fetches resolve
  });
})();
