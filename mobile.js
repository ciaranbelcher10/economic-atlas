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

  /* ---- country search: names people actually type -------------------------
     The search boxes used to match only a link's exact visible text, so the
     US link, which reads "U.S.", could not be found by typing "US" (the full
     stops) or "United States" (a different name entirely). The same was true
     of "United Kingdom" for the UK, "Euro area" for the Eurozone, "Holland"
     for the Netherlands and "Türkiye" for Turkey.
     Matching now ignores case, punctuation and accents, and checks each
     country's other names as well as the one shown. Exposed on window so
     Dashboard's picker searches with exactly the same rules. */
  var COUNTRY_ALIASES = {
    "us": ["usa", "united states", "united states of america", "america", "u s a"],
    "uk": ["united kingdom", "britain", "great britain", "gb", "england"],
    "eurozone": ["euro area", "euro zone", "ea", "ez", "europe"],
    "south korea": ["korea", "republic of korea", "rok"],
    "netherlands": ["holland", "the netherlands", "nl"],
    "turkey": ["turkiye", "tuerkiye"],
    "switzerland": ["swiss", "confederation"],
    "germany": ["deutschland"],
    "spain": ["espana"],
    "south africa": ["rsa"],
    "czechia": ["czech republic"]
  };
  function normaliseName(t){
    var s = String(t || "").toLowerCase();
    // strip accents where the browser supports it: "türkiye" -> "turkiye"
    if(s.normalize) s = s.normalize("NFD").replace(/[\u0300-\u036f]/g, "");
    // "u.s." -> "us", "côte d'ivoire" -> "cote divoire", then collapse spacing
    return s.replace(/[.\u2019']/g, "").replace(/[^a-z0-9]+/g, " ").trim();
  }

  // True when what someone typed identifies this country. Two letters or
  // fewer must match the START of a word in a name or alias -- so "us" finds
  // the United States (via "usa") and "sw" finds Sweden and Switzerland as
  // you type, but "us" does not find Australia or Austria, which contain it
  // mid-word. Longer queries match anywhere, so "united st" still works.
  function countryMatches(displayName, query){
    var q = normaliseName(query);
    if(!q) return false;
    var name = normaliseName(displayName);
    var names = [name].concat(COUNTRY_ALIASES[name] || []);
    for(var i = 0; i < names.length; i++){
      var n = names[i];
      if(q.length <= 2){
        var words = n.split(" ");
        for(var w = 0; w < words.length; w++) if(words[w].indexOf(q) === 0) return true;
      } else if(n.indexOf(q) !== -1) return true;
    }
    return false;
  }
  window.EATLAS_countryMatches = countryMatches;

  /* ------------------------------------------------------------------
     1. PERSISTENT MOBILE TOOL BAR
     ------------------------------------------------------------------ */
  function buildToolbar(){
    if(!isMobile() || document.getElementById("mobToolbar")) return;
    var navTop = document.querySelector("nav.top");
    if(!navTop) return;
    var page = (location.pathname.split("/").pop() || "index").replace(".html","") || "index";
    var isCountryPage = !!document.querySelector("nav.cat");
    // Indicator and ranking pages live one level down (/indicators/, /rankings/),
    // so every link in this bar needs "../" there or it resolves inside that
    // folder (v1.6.3 fix).
    var inSubfolder = /\/(indicators|rankings)\//.test(location.pathname);
    var prefix = inSubfolder ? "../" : "";
    var onRankings = /\/rankings(\/|$)/.test(location.pathname);
    var onIndicator = /\/indicators\//.test(location.pathname);
    var tools = [
      { href:"index",     label:"Countries", ic:"\uD83C\uDF0D", match:function(p){ return (p==="index" || isCountryPage || onIndicator) && !onRankings; } },
      { href:"compare",   label:"Compare",   ic:"\u2696\uFE0F",  match:function(p){ return p==="compare"; } },
      { href:"rankings",  label:"Rankings",  ic:"\uD83C\uDFC5",  match:function(){ return onRankings; } },
      { href:"dashboard", label:"Dashboard", ic:"\uD83D\uDCCC",  match:function(p){ return p==="dashboard"; } },
      { href:"calendar",  label:"Calendar",  ic:"\uD83D\uDDD3\uFE0F", match:function(p){ return p==="calendar"; } }
    ];
    // v1.9.68: five tabs at the bottom of the screen; Chartmaker and Markets live in the menu
    var bar = document.createElement("nav");
    bar.id = "mobToolbar";
    bar.setAttribute("aria-label","Tools");
    tools.forEach(function(t){
      var a = document.createElement("a");
      a.href = prefix + t.href;
      if(t.match(page)) a.className = "active";
      a.innerHTML = '<span class="ic" aria-hidden="true">'+t.ic+'</span>'+t.label;
      bar.appendChild(a);
    });
    navTop.insertAdjacentElement("afterend", bar);
    document.body.classList.add("mob-tabbar");
    addMenuTools(prefix, page);
  }

  /* v1.9.68: tools that are not in the five-tab bar are added to the top of the menu on phones */
  function addMenuTools(prefix, page){
    var links = document.getElementById("navLinks");
    if(!links || links.querySelector("[data-mob-extra]")) return;
    [["markets","Markets"],["chartmaker","Chartmaker"]].forEach(function(t){
      var a = document.createElement("a");
      a.className = "item" + (page === t[0] ? " active" : "");
      a.href = prefix + t[0];
      a.textContent = t[1];
      a.setAttribute("data-mob-extra", "1");
      links.insertBefore(a, links.firstChild);
    });
  }

  /* v1.9.68: slim header that slides away while reading and comes back on the first scroll up */
  function initSlimHeader(){
    if(!isMobile()) return;
    var nav = document.querySelector("nav.top");
    if(!nav || nav.getAttribute("data-slim")) return;
    nav.setAttribute("data-slim", "1");
    var toggle = document.getElementById("navToggle");
    var last = window.scrollY || 0, ticking = false;
    function setHidden(h){
      if(h && toggle && toggle.getAttribute("aria-expanded") === "true") h = false;   // never hide an open menu
      nav.classList.toggle("mob-hidden", h);
      document.body.classList.toggle("mob-head-hidden", h);
    }
    function onScroll(){
      var y = window.scrollY || 0, d = y - last;
      if(y < 64) setHidden(false);
      else if(d > 6) setHidden(true);
      else if(d < -6) setHidden(false);
      last = y; ticking = false;
    }
    window.addEventListener("scroll", function(){
      if(ticking) return;
      ticking = true;
      (window.requestAnimationFrame || setTimeout)(onScroll);
    }, {passive:true});
    document.documentElement.style.setProperty("--m-head-h", (nav.offsetHeight || 52) + "px");
  }
  window.EATLAS_initSlimHeader = initSlimHeader;

  /* v1.9.68: the section chips are one sideways-scrolling row on phones; keep the active one in view
     as the reader taps or swipes between sections */
  function keepActiveChipInView(){
    if(!isMobile()) return;
    var cat = document.querySelector("nav.cat");
    if(!cat || cat.getAttribute("data-chipwatch")) return;
    cat.setAttribute("data-chipwatch", "1");
    function centre(){
      var b = cat.querySelector("button.active");
      if(!b) return;
      var target = b.offsetLeft - (cat.clientWidth - b.offsetWidth) / 2;
      if(cat.scrollTo) cat.scrollTo({left: Math.max(0, target), behavior: "smooth"}); else cat.scrollLeft = Math.max(0, target);
    }
    new MutationObserver(centre).observe(cat, {subtree:true, attributes:true, attributeFilter:["class"]});
    centre();
  }
  window.EATLAS_keepActiveChipInView = keepActiveChipInView;

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
    { file:"data-uk.json",  slug:"uk",         name:"UK",           flag:"\uD83C\uDDEC\uD83C\uDDE7" },
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
        var matches = links.filter(function(a){ return countryMatches(a.textContent, q); }).slice(0, 6);
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
      var matches = links.filter(function(a){ return countryMatches(a.textContent, q); }).slice(0, 8);
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

    var prog = document.querySelector(".sec-progress");
    if(!prog){
      prog = document.createElement("p");
      prog.className = "sec-progress";
      prog.setAttribute("aria-live", "polite");
      hint.insertAdjacentElement("afterend", prog);
      var seen = false;
      try { seen = localStorage.getItem("ea_swipe_hint_seen") === "1"; } catch(e){}
      if(!seen){
        prog.classList.add("first-visit");
        try { localStorage.setItem("ea_swipe_hint_seen", "1"); } catch(e){}
        setTimeout(function(){ prog.classList.remove("first-visit"); syncDots(); }, 6000);
      }
    }
    function syncDots(){
      var activeIdx = btns.findIndex(function(b){ return b.classList.contains("active"); });
      $all("span", hint).forEach(function(dot, i){ dot.classList.toggle("active", i===activeIdx); });
      if(activeIdx === -1) return;
      var name = btns[activeIdx].textContent.trim();
      var txt = (activeIdx + 1) + " of " + btns.length + ": " + name;
      if(prog.classList.contains("first-visit")) txt += ". Swipe left or right for other sections";
      prog.innerHTML = '<span class="ar' + (activeIdx > 0 ? "" : " off") + '" aria-hidden="true">\u2039</span><span class="t"></span><span class="ar' + (activeIdx < btns.length - 1 ? "" : " off") + '" aria-hidden="true">\u203A</span>';
      prog.querySelector(".t").textContent = txt;
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
      if(layout.closest(".metric-card")) return; // Compare reuses the layout; the trade note is wrong there (v1.9.76)
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
      // Only the country pages' genuine trade-partner list, which carries
      // id="tpmRankList" on all 31 of them. compare.html reuses the whole
      // .tpm-* class family for its own metric ranking panel and creates
      // those lists with a class and no id, so matching on .tpm-ranklist
      // alone put a "Biggest partner: US $32.49tn2026" line above every
      // metric on Compare: the #1 row of a country ranking, read as though
      // it were a trade partner, with the value and its period span
      // concatenated by textContent. dashboard.html and chartmaker.html
      // use none of these classes and were never affected.
      if(list.id !== "tpmRankList") return;
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
  /* v1.9.76: Compare summary on phones is one card per metric (rows =
     countries) instead of one card per country, with the table's own
     highest / lowest markers shown as small labels. */
  function tableToCards(){
    if(!isMobile()) return;
    var table = document.getElementById("rankTable");
    if(!table) return;
    var wrap = table.closest("div") || table.parentElement;
    if(!wrap) return;
    var thead = table.querySelector("thead"), tbody = table.querySelector("tbody");
    if(!thead || !tbody || !tbody.rows.length) return;
    var cardsWrap = document.getElementById("cmpCardsWrap");
    if(!cardsWrap){
      cardsWrap = document.createElement("div");
      cardsWrap.id = "cmpCardsWrap";
      wrap.insertAdjacentElement("afterend", cardsWrap);
    }
    var ths = $all("th", thead), rows = $all("tr", tbody);
    var html = "";
    for(var col = 1; col < ths.length; col++){
      html += '<div class="cmp-metric-sum" data-k="' + escAttr(ths[col].getAttribute("data-k") || "") + '"><h4></h4>';
      rows.forEach(function(tr){
        var cells = $all("td", tr), cell = cells[col], name = cells[0];
        if(!cell || !name) return;
        var sw = name.querySelector(".swatch");
        var first = cell.childNodes[0];
        var val = first && first.nodeType === 3 ? first.textContent.trim() : (cell.textContent || "").trim();
        var per = cell.querySelector(".cellperiod"), tag = cell.querySelector(".measuretag");
        var mark = cell.classList.contains("col-hi") ? "hi" : (cell.classList.contains("col-lo") ? "lo" : "");
        html += '<div class="sr' + (mark ? " is-" + mark : "") + '">'
          + '<span class="sw" style="background:' + escAttr(sw ? sw.style.background : "var(--hair)") + '"></span>'
          + '<span class="c"><span class="cn"></span>' + (tag ? '<small class="tg"></small>' : "") + "</span>"
          + '<span class="v"><b></b>' + (per ? '<small class="pr"></small>' : "") + "</span>"
          + (mark ? '<span class="mk">' + (mark === "hi" ? "Highest" : "Lowest") + "</span>" : "")
          + "</div>";
      });
      html += "</div>";
    }
    cardsWrap.innerHTML = html;
    // fill text safely (no HTML from cells)
    var cardsEls = $all(".cmp-metric-sum", cardsWrap);
    for(var c = 1; c < ths.length; c++){
      var card = cardsEls[c - 1];
      card.querySelector("h4").textContent = ths[c].textContent.trim();
      var srs = $all(".sr", card), k = 0;
      rows.forEach(function(tr){
        var cells = $all("td", tr), cell = cells[c], name = cells[0];
        if(!cell || !name) return;
        var sr = srs[k++];
        var first = cell.childNodes[0];
        sr.querySelector(".cn").textContent = name.textContent.trim();
        sr.querySelector("b").textContent = first && first.nodeType === 3 ? first.textContent.trim() : cell.textContent.trim();
        var per = cell.querySelector(".cellperiod"), tag = cell.querySelector(".measuretag");
        if(per) sr.querySelector(".pr").textContent = per.textContent.trim();
        if(tag) sr.querySelector(".tg").textContent = tag.textContent.trim();
      });
    }
  }
  function escAttr(t){ return String(t).replace(/[&<>"]/g, function(ch){ return {"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;"}[ch]; }); }

  function simplifyComparePage(){
    if(!isMobile()) return;
    // Hide the second intro paragraph by matching its text — it has no
    // distinguishing class in the markup, so a text match is more robust
    // than a fragile structural selector that could catch the wrong <p>.
    $all("p").forEach(function(p){
      if(/^Looking for a (specific|single) ranking/.test(p.textContent.trim())){
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
      btn.innerHTML = "<span aria-hidden=\"true\">\u22EF</span> More options <span class=\"car\" aria-hidden=\"true\">\u25BE</span>";
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
        el.style.display = (!q || countryMatches(el.textContent, q)) ? "" : "none";
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
    nextUp.innerHTML = '<b>Next up:</b> ' + nextPillText + ' \u00b7 ' + dateStr;
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

    var mini = document.getElementById("calMiniMonth");
    if(!mini){
      mini = document.createElement("div");
      mini.id = "calMiniMonth";
      heading.insertAdjacentElement("beforebegin", mini);
    }
    function esc(t){ return String(t).replace(/[&<>"]/g, function(c){ return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]; }); }
    var DOW = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"];
    // Short country tags for the month-grid chips (cells are ~50px wide on a phone).
    var CC = {"Argentina":"AR","Australia":"AU","Austria":"AT","Belgium":"BE","Brazil":"BR","Bulgaria":"BG","Canada":"CA",
      "Chile":"CL","China":"CN","Colombia":"CO","Croatia":"HR","Cyprus":"CY","Czechia":"CZ","Denmark":"DK","Egypt":"EG",
      "Estonia":"EE","Eurozone":"EZ","Finland":"FI","France":"FR","Germany":"DE","Greece":"GR","Hong Kong":"HK","Hungary":"HU",
      "Iceland":"IS","India":"IN","Indonesia":"ID","Ireland":"IE","Israel":"IL","Italy":"IT","Japan":"JP","Latvia":"LV",
      "Lithuania":"LT","Luxembourg":"LU","Malaysia":"MY","Malta":"MT","Mexico":"MX","Morocco":"MA","Netherlands":"NL",
      "New Zealand":"NZ","Nigeria":"NG","Norway":"NO","Pakistan":"PK","Peru":"PE","Philippines":"PH","Poland":"PL",
      "Portugal":"PT","Romania":"RO","Saudi Arabia":"SA","Singapore":"SG","Slovakia":"SK","Slovenia":"SI","South Africa":"ZA",
      "South Korea":"KR","Spain":"ES","Sweden":"SE","Switzerland":"CH","Taiwan":"TW","Thailand":"TH","Turkey":"TR",
      "UAE":"AE","UK":"UK","US":"US","Vietnam":"VN"};
    function cc(name){ return CC[name] || String(name).replace(/[^A-Za-z]/g, "").slice(0, 3).toUpperCase(); }

    function renderAgendaFromGrid(){
      var cal = window.EA_CAL;
      if(!cal) return;
      var days = cal.monthDays();
      var ym = cal.ym();
      var monthLabel = document.getElementById("calMonthLabel");
      var label = monthLabel ? monthLabel.textContent : "this month";
      var flat = [];
      days.forEach(function(d){ d.events.forEach(function(e){ e._i = flat.length; flat.push(e); }); });

      // Full month grid, calendar-app style: every release is a labelled chip
      // in its day; week rows grow to fit, so nothing is clipped or counted away.
      var g = '<div class="cal-mm-dow">' + DOW.map(function(d){ return "<span>"+d.toUpperCase()+"</span>"; }).join("") + '</div><div class="cal-mm-grid">';
      var lead = cal.firstDow();
      var prevLast = new Date(ym[0], ym[1], 0).getDate();
      for(var i = lead; i > 0; i--){
        g += '<div class="cal-mm-day is-other" aria-hidden="true"><span class="n">'+(prevLast - i + 1)+"</span></div>";
      }
      days.forEach(function(d){
        var n = d.events.length;
        g += '<div class="cal-mm-day'+(d.isToday?" is-today":"")+(n?" has-ev":"")+(d.dow===0?" is-sun":"")+'" data-day="'+d.day+'"' +
          (n ? ' role="button" tabindex="0" aria-label="'+d.day+", "+n+(n===1?" release":" releases")+'"' : "") + ">";
        g += '<span class="n">'+d.day+"</span>";
        d.events.forEach(function(e){
          g += '<span class="cal-mm-chip" style="background:'+esc(e.color)+'" title="'+esc(e.country+", "+e.label)+'">'+esc(cc(e.country)+" "+e.label)+"</span>";
        });
        g += "</div>";
      });
      var tail = (7 - (lead + days.length) % 7) % 7;
      for(var t = 1; t <= tail; t++) g += '<div class="cal-mm-day is-other" aria-hidden="true"><span class="n">'+t+"</span></div>";
      mini.innerHTML = g + "</div>";

      // Agenda: every event, one compact row each. Empty days are skipped.
      heading.textContent = label + ": all tracked releases";
      var html = "";
      days.forEach(function(d){
        if(!d.events.length) return;
        html += '<div class="cal-agenda-day'+(d.isToday?" is-today":"")+'" id="calAgDay'+d.day+'" data-day="'+d.day+'">';
        html += '<div class="d-head"><span class="d-num">'+d.day+'</span><span class="d-dow">'+(d.isToday?"Today":DOW[d.dow])+"</span></div>";
        d.events.forEach(function(e){
          html += '<button type="button" class="cal-ag-row" data-i="'+e._i+'">' +
            '<i class="dot" style="background:'+esc(e.color)+'"></i>' +
            '<span class="c">'+esc(e.country)+'</span>' +
            '<span class="r">'+esc(e.label)+'</span>' +
            '<span class="t">'+esc(e.time || "Time tbc")+"</span></button>";
        });
        html += "</div>";
      });
      if(!flat.length) html = '<p class="cal-agenda-empty">No tracked releases in '+esc(label)+".</p>";
      agenda.innerHTML = html;

      renderCalendarNextUp();

      $all(".cal-ag-row", agenda).forEach(function(row){
        row.addEventListener("click", function(){ cal.open(flat[+this.getAttribute("data-i")].ev); });
      });
      $all(".cal-mm-day.has-ev", mini).forEach(function(btn){
        btn.addEventListener("keydown", function(ev){ if(ev.key === "Enter" || ev.key === " "){ ev.preventDefault(); this.click(); } });
        btn.addEventListener("click", function(){
          var target = document.getElementById("calAgDay" + this.getAttribute("data-day"));
          if(!target) return;
          $all(".cal-agenda-day.is-picked", agenda).forEach(function(x){ x.classList.remove("is-picked"); });
          $all(".cal-mm-day.is-picked", mini).forEach(function(x){ x.classList.remove("is-picked"); });
          target.classList.add("is-picked");
          this.classList.add("is-picked");
          if(target.scrollIntoView) target.scrollIntoView({behavior:"smooth", block:"start"});
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
      el.textContent = "Not switched on for this view yet. You can turn it on any time from the Countries panel above.";
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
  /* v1.9.80 Chartmaker on phones: no more "needs a bigger screen" dead end.
     The live chart shows with a gallery of example charts above it; the
     editing panels stay hidden. "Send to my desktop" shares (or copies) a
     link that opens the same example on a big screen. Signed-in people can
     open their saved charts read-only through the page's own Open list. */
  function chartmakerGate(){
    var layout = document.getElementById("cmLayout");
    if(!layout) return;
    var gate = document.getElementById("cmMobileGate");
    if(!isMobile()){
      document.body.classList.remove("cm-m");
      if(gate) gate.style.display = "none";
      layout.style.display = "";
      return;
    }
    document.body.classList.add("cm-m");
    if(gate){ gate.style.display = ""; syncCmGate(); return; }
    gate = document.createElement("div");
    gate.id = "cmMobileGate";
    gate.innerHTML =
      '<p class="cm-m-lead">Browse example charts here. Building and styling your own works best on a bigger screen.</p>' +
      '<div class="cm-m-ex" role="group" aria-label="Example charts"></div>' +
      '<div class="cm-m-actions">' +
        '<button type="button" class="cm-m-send">Send this to my desktop</button>' +
        '<button type="button" class="cm-m-saved" hidden>Your saved charts</button>' +
      '</div>' +
      '<p class="cm-m-msg" aria-live="polite"></p>';
    layout.insertAdjacentElement("beforebegin", gate);
    var send = gate.querySelector(".cm-m-send"), msg = gate.querySelector(".cm-m-msg");
    send.addEventListener("click", function(){
      var cm = window.EA_CM || {};
      var url = location.origin + location.pathname + (cm.current ? "?ex=" + encodeURIComponent(cm.current) : "");
      var title = "Chartmaker, The Economic Atlas";
      function copied(){ msg.textContent = "Link copied. Open it on your computer to edit this chart."; }
      function failed(){ msg.textContent = "Open " + url + " on your computer."; }
      if(navigator.share){
        navigator.share({ title: title, url: url }).catch(function(e){
          if(e && e.name === "AbortError") return;
          if(navigator.clipboard) navigator.clipboard.writeText(url).then(copied, failed); else failed();
        });
      } else if(navigator.clipboard){
        navigator.clipboard.writeText(url).then(copied, failed);
      } else failed();
    });
    gate.querySelector(".cm-m-saved").addEventListener("click", function(){
      var o = document.getElementById("cmOpenBtn"); if(o) o.click();
    });
    document.addEventListener("ea:cm-ready", syncCmGate);
    document.addEventListener("ea:cm-example", syncCmGate);
    syncCmGate();
  }
  function syncCmGate(){
    var gate = document.getElementById("cmMobileGate"), cm = window.EA_CM;
    if(!gate) return;
    var host = gate.querySelector(".cm-m-ex");
    if(cm && cm.examples && !host.children.length){
      cm.examples.forEach(function(e){
        var b = document.createElement("button");
        b.type = "button"; b.className = "cm-m-chip"; b.dataset.key = e.key; b.textContent = e.title;
        b.addEventListener("click", function(){ if(window.EA_CM) window.EA_CM.show(this.dataset.key); });
        host.appendChild(b);
      });
    }
    host.hidden = !(cm && cm.examples && cm.examples.length > 1);   // v1.9.82: no chip row for a single example
    $all(".cm-m-chip", host).forEach(function(b){
      b.setAttribute("aria-pressed", cm && cm.current === b.dataset.key ? "true" : "false");
    });
    var saved = gate.querySelector(".cm-m-saved");
    var inn = !!(window.EATLAS_PREFS && window.EATLAS_PREFS.isLoggedIn && window.EATLAS_PREFS.isLoggedIn());
    if(saved.hidden === inn) saved.hidden = !inn;
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
     v1.9.76 COMPARE on phones: one sticky bar with country chips and a
     tab per metric; one metric card on screen at a time, answer (ranked
     bars) first, controls after; countries panel and Add a metric as
     bottom sheets, the latter with search and + / tick rows.
     ------------------------------------------------------------------ */
  var cmpActive = null, cmpKnown = null;
  function cmpCards(){ return $all("#chartGrid .metric-card"); }
  function parseShownNumber(t){
    t = String(t).replace(/\u2212/g, "-").replace(/,/g, "").trim();
    var m = t.match(/(-?)[^0-9\-]*([0-9]*\.?[0-9]+)\s*(tn|bn|m|k|%)?/i);
    if(!m) return null;
    var v = parseFloat(m[2]); if(isNaN(v)) return null;
    var mult = {tn:1e12, bn:1e9, m:1e6, k:1e3}[(m[3] || "").toLowerCase()] || 1;
    return (m[1] === "-" ? -1 : 1) * v * mult;
  }
  function addRankBars(card){
    $all(".tpm-ranklist", card).forEach(function(ol){
      var rows = $all(".tpm-rankrow", ol);
      var vals = rows.map(function(li){
        var v = li.querySelector(".tpm-rankvalue");
        if(!v) return null;
        var txt = ""; v.childNodes.forEach(function(n){ if(n.nodeType === 3) txt += n.textContent; });
        return parseShownNumber(txt);
      });
      var ok = vals.length && vals.every(function(v){ return v != null; });
      var max = ok ? Math.max.apply(null, vals.map(Math.abs)) : 0;
      rows.forEach(function(li, i){
        var bar = li.querySelector(".cmp-rk-bar");
        if(!ok || !max){ if(bar) bar.remove(); return; }
        if(!bar){ bar = document.createElement("span"); bar.className = "cmp-rk-bar"; bar.appendChild(document.createElement("i")); li.appendChild(bar); }
        var sw = li.querySelector(".tpm-rankswatch");
        var w = Math.max(2, Math.round(Math.abs(vals[i]) / max * 100));
        var fill = bar.firstChild;
        if(fill.style.width !== w + "%") fill.style.width = w + "%";
        var bg = sw ? sw.style.background : "";
        if(bg && fill.style.background !== bg) fill.style.background = bg;
        bar.classList.toggle("neg", vals[i] < 0);
      });
    });
  }
  /* v1.9.77: a clear, labelled full-screen chart button straight under the
     ranking on each card (the card's own Fullscreen button was tucked away
     inside More options). It just presses the card's own button. */
  function addFullscreenButton(card){
    var real = card.querySelector(".card-fullscreen-btn");
    if(!real || card.querySelector(".cmp-m-fs")) return;
    var b = document.createElement("button");
    b.type = "button";
    b.className = "cmp-m-fs";
    b.innerHTML = '<span aria-hidden="true">\u2922</span> View full-screen chart';
    b.addEventListener("click", function(){ real.click(); });
    card.appendChild(b);
  }
  /* v1.9.78: per card on phones, "Remove this metric" lives in More options
     (the corner x read as "close"), and the freshness key sits as one small
     line at the bottom of the card instead of two lines under the tabs. */
  function addCardExtras(card){
    var real = card.querySelector(".card-remove");
    if(real && !card.querySelector(".cmp-m-remove")){
      var b = document.createElement("button");
      b.type = "button";
      b.className = "cmp-m-remove";
      b.textContent = "Remove this metric";
      b.addEventListener("click", function(){ real.click(); });
      card.appendChild(b);
    }
    if(!card.querySelector(".cmp-m-key")){
      var k = document.createElement("p");
      k.className = "cmp-m-key";
      k.innerHTML = '<span><span class="led green" aria-hidden="true"></span>Latest data</span><span><span class="led orange" aria-hidden="true"></span>Awaiting next update</span>';
      card.appendChild(k);
    }
  }
  var CMP_SHORT_LEDE = "Rank the 62 economies side by side, for one year or over time.";
  var CMP_SHORT_SAVE = "Sign up free to keep this comparison.";
  function compactCompareTop(on){
    var h1 = document.querySelector("h1");
    var lede = h1 && h1.nextElementSibling;
    if(lede && lede.tagName === "P"){
      if(!lede.dataset.full) lede.dataset.full = lede.textContent;
      var want = on ? CMP_SHORT_LEDE : lede.dataset.full;
      if(lede.textContent !== want) lede.textContent = want;
      lede.classList.add("cmp-m-lede");
    }
    var sb = document.querySelector("#saveBar p");
    if(sb){
      if(!sb.dataset.full) sb.dataset.full = sb.textContent;
      var w2 = on ? CMP_SHORT_SAVE : sb.dataset.full;
      if(sb.textContent !== w2) sb.textContent = w2;
    }
  }
  /* ---- v1.9.83: Compare on phones, rebuilt. One metric ranked across a country set; two buttons
     (metric, countries) open one full-screen sheet at a time; rows expand to a trend line. Reads
     compare.html's own data helpers (REGISTRY, getSnapshotValue, displayString...); desktop untouched. */
  var CMPP_KEY = "eatlas_cmp_phone";
  var CMPP_PRESETS = [
    { id:"all", label:"All" },
    { id:"g7", label:"G7", list:["UK","US","Germany","France","Italy","Japan","Canada"] },
    { id:"g20", label:"G20", list:["Argentina","Australia","Brazil","Canada","China","France","Germany","India","Indonesia","Italy","Japan","Mexico","Saudi Arabia","South Africa","South Korea","Turkey","UK","US","Eurozone"] },
    { id:"eu", label:"EU", list:["Germany","France","Italy","Spain","Netherlands","Ireland","Poland","Austria","Sweden","Belgium","Portugal","Finland","Greece","Czechia","Hungary","Romania","Slovakia","Croatia","Bulgaria","Lithuania","Estonia","Latvia","Slovenia","Luxembourg","Cyprus","Malta","Denmark"] },
    { id:"europe", label:"Europe", region:["Europe"] },
    { id:"asiapac", label:"Asia-Pacific", region:["Asia","Oceania"] },
    { id:"americas", label:"Americas", region:["North America","South America"] },
    { id:"emerging", label:"Emerging", list:["China","India","Indonesia","Brazil","Mexico","South Africa","Turkey","Saudi Arabia","Argentina","Chile","Colombia","Peru","Philippines","Thailand","Malaysia","Vietnam","Nigeria","Egypt","Pakistan","Morocco","Poland","Hungary","Romania"] },
    { id:"custom", label:"Custom" }
  ];
  var cmpp = null;   // {metric, preset, custom:[], desc, open:null|country}
  function CD(){ return window.EATLAS_COMPARE_DATA || {}; }
  function cmppReady(){ var mc = document.getElementById("mainContent"); return !!(window.EATLAS_COMPARE_DATA && mc && mc.style.display !== "none" && CD().currentYear() != null); }
  function cmppAll(){ return (CD().ALL_COUNTRIES || []).slice(); }
  function cmppLabel(c){ return (CD().COUNTRY_LABEL && CD().COUNTRY_LABEL[c]) || c; }
  function cmppPresetList(id){
    var p = CMPP_PRESETS.filter(function(x){ return x.id === id; })[0], all = cmppAll();
    if(!p || id === "all") return all;
    if(id === "custom") return (cmpp.custom || []).filter(function(c){ return all.indexOf(c) !== -1; });
    if(p.region) return all.filter(function(c){ return p.region.indexOf(CD().REGION_OF[c]) !== -1; });
    return p.list.filter(function(c){ return all.indexOf(c) !== -1; });
  }
  function cmppLoad(){
    var s = {};
    try{ s = JSON.parse(localStorage.getItem(CMPP_KEY) || "{}") || {}; }catch(e){}
    var q = {}; try{ q = new URLSearchParams(location.search); }catch(e){ q = { get: function(){ return null; } }; }
    var m = q.get("metric") || s.metric || "debt_gdp";
    if(!(CD().CONCEPT_LABEL || {})[m]) m = "debt_gdp";
    var pr = q.get("countries") === "all" ? "all" : (q.get("set") || s.preset || "all");
    if(!CMPP_PRESETS.some(function(x){ return x.id === pr; })) pr = "all";
    cmpp = { metric: m, preset: pr, custom: Array.isArray(s.custom) ? s.custom : [], desc: s.desc !== false, open: null };
  }
  function cmppSave(noUrl){
    try{ localStorage.setItem(CMPP_KEY, JSON.stringify({ metric: cmpp.metric, preset: cmpp.preset, custom: cmpp.custom, desc: cmpp.desc })); }catch(e){}
    if(noUrl) return;
    try{
      var q = new URLSearchParams(location.search);
      q.set("metric", cmpp.metric);
      if(cmpp.preset === "all"){ q.set("countries", "all"); q.delete("set"); }
      else { q.delete("countries"); if(cmpp.preset === "custom") q.delete("set"); else q.set("set", cmpp.preset); }
      history.replaceState(history.state, "", location.pathname + "?" + q.toString());
    }catch(e){}
  }
  function cmppValue(c, k){
    var top = CD().maxYearFor(k);
    for(var y = top; y >= top - 3; y--){
      var dv = null; try{ dv = CD().getSnapshotValue(c, k, y); }catch(e){}
      if(dv && dv.value != null && isFinite(dv.value)) return dv;
    }
    return null;
  }
  function cmppMetrics(){
    var all = cmppAll();
    return Object.keys(CD().CONCEPT_LABEL).filter(function(k){
      var n = 0;
      for(var i = 0; i < all.length && n < 5; i++){ if(cmppValue(all[i], k)) n++; }
      return n >= 5;
    });
  }
  function cmppEsc(s){ return String(s).replace(/[&<>"]/g, function(ch){ return { "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;" }[ch]; }); }
  function cmppBuild(){
    var main = document.getElementById("mainContent");
    var v = document.getElementById("cmpP");
    if(!v){
      v = document.createElement("div");
      v.id = "cmpP";
      v.innerHTML =
        '<div class="cmpp-bar">' +
          '<button type="button" class="cmpp-pick" data-open="metric"><small>Metric</small><span class="cmpp-metric"></span></button>' +
          '<button type="button" class="cmpp-pick" data-open="countries"><small>Countries</small><span class="cmpp-set"></span></button>' +
        '</div>' +
        '<div class="cmpp-sub"><span class="cmpp-avg"></span><button type="button" class="cmpp-order"></button></div>' +
        '<ol class="cmpp-list" aria-live="polite"></ol>' +
        '<p class="cmpp-none" hidden></p>';
      (main ? main.parentNode : document.body).insertBefore(v, main || null);
      $all(".cmpp-pick", v).forEach(function(b){ b.addEventListener("click", function(){ cmppOpen(this.dataset.open); }); });
      $(".cmpp-order", v).addEventListener("click", function(){ cmpp.desc = !cmpp.desc; cmppSave(); cmppRender(); });
      $(".cmpp-list", v).addEventListener("click", function(e){
        var li = e.target.closest ? e.target.closest("li[data-c]") : null;
        if(!li) return;
        cmpp.open = cmpp.open === li.dataset.c ? null : li.dataset.c;
        cmppRender();
      });
    }
    return v;
  }
  function cmppRender(){
    var v = cmppBuild();
    var k = cmpp.metric;
    $(".cmpp-metric", v).textContent = CD().CONCEPT_LABEL[k];
    var set = cmppPresetList(cmpp.preset);
    var pl = CMPP_PRESETS.filter(function(x){ return x.id === cmpp.preset; })[0];
    $(".cmpp-set", v).textContent = cmpp.preset === "all" ? "All " + set.length : cmpp.preset === "custom" ? set.length + " chosen" : pl.label + " (" + set.length + ")";
    var list = $(".cmpp-list", v), none = $(".cmpp-none", v);
    if(!cmppReady()){ list.innerHTML = '<li class="cmpp-loading">Loading data\u2026</li>'; return; }
    var rows = [], missing = [];
    set.forEach(function(c){ var dv = cmppValue(c, k); if(dv) rows.push({ c: c, dv: dv }); else missing.push(c); });
    rows.sort(function(a, b){ return cmpp.desc ? b.dv.value - a.dv.value : a.dv.value - b.dv.value; });
    var yc = {}; rows.forEach(function(r){ yc[r.dv.year] = (yc[r.dv.year] || 0) + 1; });
    var modeY = Object.keys(yc).sort(function(a, b){ return yc[b] - yc[a]; })[0];
    var maxAbs = rows.reduce(function(m, r){ return Math.max(m, Math.abs(r.dv.value)); }, 0) || 1;
    var unit = CD().CONCEPT_UNIT[k];
    var avgTxt = "";
    if(rows.length > 1 && unit !== "currency"){
      var avg = rows.reduce(function(s, r){ return s + r.dv.value; }, 0) / rows.length;
      avgTxt = "Average " + CD().displayString({ value: Math.round(avg * 100) / 100, unit: unit, isDelta: false }) + " \u00b7 ";
    }
    $(".cmpp-avg", v).textContent = avgTxt + (modeY ? "Latest, mostly " + modeY : "");
    $(".cmpp-order", v).textContent = cmpp.desc ? "Highest first \u2193" : "Lowest first \u2191";
    var html = rows.map(function(r, i){
      var w = Math.max(2, Math.round(Math.abs(r.dv.value) / maxAbs * 100));
      var tag = String(r.dv.year) !== modeY ? '<em>' + r.dv.year + '</em>' : "";
      var open = cmpp.open === r.c;
      return '<li data-c="' + cmppEsc(r.c) + '"' + (open ? ' class="open"' : "") + ' role="button" tabindex="0" aria-expanded="' + open + '">' +
        '<span class="r">' + (i + 1) + '</span><span class="n">' + cmppEsc(cmppLabel(r.c)) + tag + '</span>' +
        '<span class="v">' + cmppEsc(CD().displayString(r.dv)) + '</span>' +
        '<span class="b"><i class="' + (r.dv.value < 0 ? "neg" : "") + '" style="width:' + w + '%"></i></span>' +
        (open ? cmppDetail(r.c, k, r.dv) : "") + '</li>';
    }).join("");
    list.innerHTML = html;
    none.hidden = !missing.length;
    none.textContent = missing.length ? "No data: " + missing.map(cmppLabel).join(", ") : "";
    if(!rows.length){ list.innerHTML = '<li class="cmpp-loading">No country in this set has this metric.</li>'; }
  }
  function cmppDetail(c, k, dv){
    var top = dv.year, pts = [];
    for(var y = top - 10; y <= top; y++){
      var p = null; try{ p = CD().getSnapshotValue(c, k, y); }catch(e){}
      if(p && p.value != null && isFinite(p.value)) pts.push([y, p.value]);
    }
    var svg = "";
    if(pts.length >= 2){
      var W = 300, H = 70, x0 = pts[0][0], x1 = pts[pts.length - 1][0];
      var lo = Math.min.apply(null, pts.map(function(p){ return p[1]; })), hi = Math.max.apply(null, pts.map(function(p){ return p[1]; }));
      if(hi === lo){ hi += 1; lo -= 1; }
      var d = pts.map(function(p, i){ var x = (p[0] - x0) / (x1 - x0 || 1) * (W - 8) + 4, y = H - 6 - (p[1] - lo) / (hi - lo) * (H - 12); return (i ? "L" : "M") + x.toFixed(1) + " " + y.toFixed(1); }).join(" ");
      svg = '<svg class="cmpp-spark" viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="none" aria-hidden="true"><path d="' + d + '"/></svg>' +
        '<span class="cmpp-yrs"><span>' + x0 + '</span><span>' + x1 + '</span></span>';
    }
    var src = null; try{ src = CD().shortSourceNote ? CD().shortSourceNote(c, k) : null; }catch(e){}
    return '<div class="cmpp-detail">' + svg + '<p>Latest: ' + cmppEsc(String(dv.year)) + (src ? ' \u00b7 Source: ' + cmppEsc(src) : "") + '</p></div>';
  }
  /* one sheet, reused */
  function cmppSheet(){
    var s = document.getElementById("cmpPSheet");
    if(s) return s;
    s = document.createElement("div");
    s.id = "cmpPSheet"; s.hidden = true;
    s.setAttribute("role", "dialog"); s.setAttribute("aria-modal", "true");
    s.innerHTML = '<div class="cmpp-sh-head"><b></b><button type="button" class="cmpp-done">Done</button></div>' +
      '<input type="search" class="cmpp-q" autocomplete="off">' + '<div class="cmpp-sh-top"></div><div class="cmpp-sh-body"></div>';
    document.body.appendChild(s);
    $(".cmpp-done", s).addEventListener("click", cmppClose);
    $(".cmpp-q", s).addEventListener("input", function(){ cmppFilter(this.value); });
    document.addEventListener("keydown", function(e){ if(e.key === "Escape" && !s.hidden) cmppClose(); });
    window.addEventListener("popstate", function(){
      if(!s.hidden) cmppClose(true);
      else if(s._saveAfterPop){ s._saveAfterPop = false; cmppSave(); }
    });
    return s;
  }
  function cmppFilter(q){
    var s = cmppSheet(); q = String(q || "").trim().toLowerCase();
    $all(".cmpp-item", s).forEach(function(it){ it.hidden = !!q && it.textContent.toLowerCase().indexOf(q) === -1; });
    $all(".cmpp-grp", s).forEach(function(g){ g.hidden = !$all(".cmpp-item", g).some(function(it){ return !it.hidden; }); });
  }
  function cmppOpen(kind){
    if(!cmppReady()) return;
    var s = cmppSheet();
    s.dataset.kind = kind;
    $(".cmpp-q", s).value = "";
    var body = $(".cmpp-sh-body", s), top = $(".cmpp-sh-top", s);
    if(kind === "metric"){
      $("b", s).textContent = "Choose a metric";
      $(".cmpp-q", s).placeholder = "Search metrics";
      top.innerHTML = "";
      var ks = cmppMetrics();
      body.innerHTML = CD().CATEGORY_ORDER.map(function(cat){
        var inCat = ks.filter(function(k){ return CD().CONCEPT_CATEGORY[k] === cat; });
        if(!inCat.length) return "";
        return '<div class="cmpp-grp"><h3>' + cmppEsc(cat) + '</h3>' + inCat.map(function(k){
          return '<button type="button" class="cmpp-item" data-k="' + k + '" aria-pressed="' + (k === cmpp.metric) + '">' + cmppEsc(CD().CONCEPT_LABEL[k]) + '</button>';
        }).join("") + '</div>';
      }).join("");
      $all(".cmpp-item", body).forEach(function(b){ b.addEventListener("click", function(){ cmpp.metric = this.dataset.k; cmpp.open = null; cmppClose(); }); });
    } else {
      $("b", s).textContent = "Choose countries";
      $(".cmpp-q", s).placeholder = "Search countries";
      top.innerHTML = '<div class="cmpp-presets">' + CMPP_PRESETS.filter(function(p){ return p.id !== "custom"; }).map(function(p){
        return '<button type="button" data-p="' + p.id + '">' + p.label + '</button>'; }).join("") +
        '<button type="button" data-p="none">None</button></div><p class="cmpp-count"></p>';
      var groups = CD().REGION_GROUPS || [];
      body.innerHTML = groups.map(function(g){
        return '<div class="cmpp-grp"><h3>' + cmppEsc(g.name) + '</h3>' + g.countries.map(function(c){
          return '<button type="button" class="cmpp-item cmpp-c" data-c="' + cmppEsc(c) + '" aria-pressed="false">' + cmppEsc(cmppLabel(c)) + '</button>';
        }).join("") + '</div>';
      }).join("");
      var cur = cmppPresetList(cmpp.preset);
      s._picked = cur.slice(); s._preset = cmpp.preset;
      $all(".cmpp-presets button", top).forEach(function(b){ b.addEventListener("click", function(){
        var id = this.dataset.p;
        s._preset = id === "none" ? "custom" : id;
        s._picked = id === "none" ? [] : cmppPresetListFor(id);
        cmppSyncTicks();
      }); });
      $all(".cmpp-c", body).forEach(function(b){ b.addEventListener("click", function(){
        var c = this.dataset.c, i = s._picked.indexOf(c);
        if(i === -1) s._picked.push(c); else s._picked.splice(i, 1);
        s._preset = "custom";
        cmppSyncTicks();
      }); });
      cmppSyncTicks();
    }
    s.hidden = false;
    document.body.classList.add("cmpp-sheet-open");
    try{ history.pushState({ cmpp: 1 }, ""); s._pushed = true; }catch(e){ s._pushed = false; }
  }
  function cmppPresetListFor(id){ var keep = cmpp.preset; cmpp.preset = id; var l = cmppPresetList(id); cmpp.preset = keep; return l; }
  function cmppSyncTicks(){
    var s = cmppSheet();
    $all(".cmpp-c", s).forEach(function(b){ b.setAttribute("aria-pressed", s._picked.indexOf(b.dataset.c) !== -1 ? "true" : "false"); });
    $all(".cmpp-presets button", s).forEach(function(b){ b.setAttribute("aria-pressed", b.dataset.p === s._preset ? "true" : "false"); });
    var n = $(".cmpp-count", s); if(n) n.textContent = s._picked.length + " selected";
  }
  function cmppClose(fromPop){
    var s = cmppSheet();
    if(s.hidden) return;
    if(s.dataset.kind === "countries"){
      if(s._preset === "custom"){ cmpp.preset = "custom"; cmpp.custom = s._picked.slice(); }
      else cmpp.preset = s._preset;
      cmpp.open = null;
    }
    s.hidden = true;
    document.body.classList.remove("cmpp-sheet-open");
    // Back closes the sheet: the URL is written once the pushed entry is gone, or it would be undone.
    if(s._pushed && fromPop !== true){
      s._pushed = false; s._saveAfterPop = true; cmppSave(true);
      try{ history.back(); }catch(e){}
      setTimeout(function(){ if(s._saveAfterPop){ s._saveAfterPop = false; cmppSave(); } }, 500);
    } else { s._pushed = false; cmppSave(); }
    cmppRender();
  }
  function initComparePhone(){
    if(!document.getElementById("chartGrid")) return;
    if(!isMobile()){
      document.body.classList.remove("cmp-p");
      var sh = document.getElementById("cmpPSheet"); if(sh && !sh.hidden) cmppClose();
      return;
    }
    document.body.classList.add("cmp-p");
    if(!cmpp) cmppLoad();
    cmppRender();
    if(!cmppReady() && !initComparePhone._poll){
      initComparePhone._poll = setInterval(function(){ if(cmppReady()){ clearInterval(initComparePhone._poll); initComparePhone._poll = null; cmppRender(); } }, 250);
    }
  }
  window.EA_CMPP = { state: function(){ return cmpp; }, render: function(){ cmppRender(); }, presets: CMPP_PRESETS };
  function initCompareMobile(){
    if(document.getElementById("chartGrid") && isMobile()){ document.body.classList.remove("cmp-m"); compactCompareTop(false); initComparePhone(); return; }   // v1.9.83: rebuilt phone view
    initComparePhone();
    var grid = document.getElementById("chartGrid");
    var toggle = document.getElementById("countriesToggleBtn");
    if(!grid || !toggle) return;
    if(!isMobile()){ document.body.classList.remove("cmp-m"); compactCompareTop(false); return; }
    document.body.classList.add("cmp-m");
    compactCompareTop(true);
    var bar = document.getElementById("cmpMBar");
    if(!bar){
      bar = document.createElement("div");
      bar.id = "cmpMBar";
      bar.innerHTML = '<div class="cmp-m-chips" id="cmpMChips"></div><div class="cmp-m-tabs" id="cmpMTabs" role="tablist" aria-label="Metrics"></div>';
      toggle.insertAdjacentElement("afterend", bar);
    }
    renderCompareBar();
    if(!grid._cmpMWatched){
      grid._cmpMWatched = true;
      new MutationObserver(function(){ if(isMobile()) renderCompareBar(); }).observe(grid, {childList:true, subtree:true});
      var chipRow = document.getElementById("chipRow");
      if(chipRow) new MutationObserver(function(){ if(isMobile()) renderCompareChips(); }).observe(chipRow, {childList:true, subtree:true, attributes:true, attributeFilter:["style"]});
      var panel = document.getElementById("countriesPanelBody");
      if(panel){
        var done = document.createElement("button");
        done.type = "button"; done.className = "cmp-m-done"; done.textContent = "Done";
        done.addEventListener("click", function(){ toggle.click(); });
        panel.insertBefore(done, panel.firstChild);
        var back = document.createElement("div");
        back.id = "cmpPanelBackdrop"; back.className = "ea-sheet-backdrop"; back.hidden = true;
        back.addEventListener("click", function(){ toggle.click(); });
        document.body.appendChild(back);
        var sync = function(){ back.hidden = !(isMobile() && panel.style.display === "block"); };
        new MutationObserver(sync).observe(panel, {attributes:true, attributeFilter:["style"]});
        sync();
      }
    }
    initMetricPickerSheet();
  }
  function renderCompareChips(){
    var host = document.getElementById("cmpMChips"), toggle = document.getElementById("countriesToggleBtn");
    var chipRow = document.getElementById("chipRow");
    if(!host || !chipRow) return;
    var chips = $all(".chip[data-country]", chipRow);
    var sig = chips.map(function(c){ return c.dataset.country + "|" + c.style.background; }).join(",");
    if(host._sig === sig) return;
    host._sig = sig;
    host.innerHTML = "";
    chips.forEach(function(c){
      var b = document.createElement("button");
      b.type = "button"; b.className = "cmp-m-chip";
      b.innerHTML = '<i aria-hidden="true"></i><span></span>';
      b.querySelector("i").style.background = c.style.background;
      b.querySelector("span").textContent = c.dataset.country;
      b.setAttribute("aria-label", c.dataset.country + ", change countries");
      b.addEventListener("click", function(){ toggle.click(); });
      host.appendChild(b);
    });
    var add = document.createElement("button");
    add.type = "button"; add.className = "cmp-m-chip cmp-m-add";
    add.textContent = chips.length ? "+ Edit" : "+ Add countries";
    add.addEventListener("click", function(){ toggle.click(); });
    host.appendChild(add);
  }
  function renderCompareBar(){
    renderCompareChips();
    var tabs = document.getElementById("cmpMTabs");
    if(!tabs) return;
    var cards = cmpCards();
    var concepts = cards.map(function(c){ return c.dataset.concept; });
    // newly added metric becomes the active tab; removed active falls back to the first
    if(cmpKnown){
      var fresh = concepts.filter(function(k){ return cmpKnown.indexOf(k) === -1; });
      if(fresh.length) cmpActive = fresh[fresh.length - 1];
    }
    cmpKnown = concepts;
    if(concepts.indexOf(cmpActive) === -1) cmpActive = concepts[0] || null;
    document.body.classList.toggle("cmp-m-empty", !concepts.length);
    cards.forEach(function(c){
      var on = c.dataset.concept === cmpActive;
      if(c.classList.contains("cmp-m-off") === on) c.classList.toggle("cmp-m-off", !on);
      addRankBars(c);
      addFullscreenButton(c);
      addCardExtras(c);
    });
    var sig = concepts.join(",") + "#" + cmpActive + "#" + cards.map(function(c){ var t = c.querySelector(".card-title"); return t ? t.textContent : ""; }).join("|");
    if(tabs._sig === sig) return;
    tabs._sig = sig;
    tabs.innerHTML = "";
    cards.forEach(function(c){
      var t = c.querySelector(".card-title");
      var b = document.createElement("button");
      b.type = "button"; b.className = "cmp-m-tab";
      b.setAttribute("role", "tab");
      var on = c.dataset.concept === cmpActive;
      b.setAttribute("aria-selected", on ? "true" : "false");
      b.tabIndex = on ? 0 : -1;
      b.dataset.concept = c.dataset.concept;
      b.textContent = t && t.textContent.trim() ? t.textContent.trim() : c.dataset.concept;
      b.addEventListener("click", function(){ cmpActive = this.dataset.concept; tabs._sig = null; renderCompareBar(); });
      tabs.appendChild(b);
    });
    var add = document.createElement("button");
    add.type = "button"; add.className = "cmp-m-tab cmp-m-tab-add";
    add.textContent = "+ Add metric";
    add.addEventListener("click", function(){ var t = document.getElementById("addMetricTile"); if(t) t.click(); });
    tabs.appendChild(add);
    var act = tabs.querySelector('[aria-selected="true"]');
    if(act && act.scrollIntoView) act.scrollIntoView({inline:"center", block:"nearest"});
  }
  function initMetricPickerSheet(){
    var modal = document.getElementById("metricPicker"), gridEl = document.getElementById("metricPickerGrid");
    if(!modal || !gridEl || document.getElementById("metricPickerSearch")) return;
    var input = document.createElement("input");
    input.type = "search"; input.id = "metricPickerSearch";
    input.placeholder = "Search metrics, e.g. inflation";
    input.setAttribute("aria-label", "Search metrics");
    gridEl.insertAdjacentElement("beforebegin", input);
    function filter(){
      var q = input.value.trim().toLowerCase();
      var cat = null, catHas = false;
      $all(".pickercat, .pickeritem", gridEl).forEach(function(el){
        if(el.classList.contains("pickercat")){
          if(cat) cat.hidden = !catHas;
          cat = el; catHas = false; return;
        }
        var hit = !q || el.textContent.toLowerCase().indexOf(q) !== -1 || (cat && cat.textContent.toLowerCase().indexOf(q) !== -1);
        el.hidden = !hit;
        if(hit) catHas = true;
      });
      if(cat) cat.hidden = !catHas;
    }
    input.addEventListener("input", filter);
    new MutationObserver(function(){ if(input.value) filter(); }).observe(gridEl, {childList:true});
    new MutationObserver(function(){ if(modal.hidden){ input.value = ""; filter(); } })
      .observe(modal, {attributes:true, attributeFilter:["hidden"]});
  }

  /* ------------------------------------------------------------------
     v1.9.79 RANKINGS on phones: region chips that filter the 62 rows and
     a "Find a country" box that jumps to and highlights a row. Reads the
     region and country already printed on each row; no data of its own.
     ------------------------------------------------------------------ */
  function initRankingsTools(){
    var table = document.getElementById("rkTable");
    var tbody = table && table.tBodies[0];
    if(!tbody) return;
    var bar = document.getElementById("rkMTools");
    if(!isMobile()){
      if(bar) bar.hidden = true;
      $all("tr.rk-m-hide", tbody).forEach(function(tr){ tr.classList.remove("rk-m-hide"); });
      return;
    }
    if(bar){ bar.hidden = false; return; }
    var rows = $all("tr", tbody);
    var counts = {};
    rows.forEach(function(tr){ var r = tr.querySelector(".rk-region"); if(r){ var k = r.textContent.trim(); counts[k] = (counts[k] || 0) + 1; } });
    var regions = Object.keys(counts).sort(function(a, b){ return counts[b] - counts[a] || a.localeCompare(b); });
    if(!regions.length) return;
    bar = document.createElement("div");
    bar.id = "rkMTools";
    bar.innerHTML = '<input type="search" id="rkMFind" placeholder="Find a country" aria-label="Find a country" autocomplete="off">'
      + '<div class="rk-m-chips" role="group" aria-label="Filter by region"></div><p class="rk-m-status" aria-live="polite"></p>';
    var chips = bar.querySelector(".rk-m-chips");
    var region = "";
    function mk(label, val, n){
      var b = document.createElement("button");
      b.type = "button"; b.className = "rk-m-chip"; b.dataset.region = val;
      b.setAttribute("aria-pressed", val === "" ? "true" : "false");
      b.textContent = label + (n != null ? " " + n : "");
      b.addEventListener("click", function(){ setRegion(val); });
      chips.appendChild(b);
    }
    mk("All", "", rows.length);
    regions.forEach(function(r){ mk(r, r, counts[r]); });
    var status = bar.querySelector(".rk-m-status");
    function setRegion(val){
      region = val;
      $all(".rk-m-chip", chips).forEach(function(b){ b.setAttribute("aria-pressed", b.dataset.region === val ? "true" : "false"); });
      var shown = 0;
      $all("tr", tbody).forEach(function(tr){
        var r = tr.querySelector(".rk-region");
        var hide = !!val && (!r || r.textContent.trim() !== val);
        tr.classList.toggle("rk-m-hide", hide);
        if(!hide) shown++;
      });
      status.textContent = val ? shown + " of " + rows.length + " countries in " + val + ". Ranks are out of all " + rows.length + "." : "";
    }
    var find = bar.querySelector("#rkMFind");
    find.addEventListener("input", function(){
      var q = find.value.trim().toLowerCase();
      $all("tr.rk-m-hit", tbody).forEach(function(tr){ tr.classList.remove("rk-m-hit"); });
      if(!q) return;
      var all = $all("tr", tbody);
      var name = function(tr){ var c = tr.querySelector(".rk-cty") || tr.querySelector(".country"); return c ? c.textContent.trim().toLowerCase() : ""; };
      var hit = all.filter(function(tr){ return name(tr).indexOf(q) === 0; })[0] || all.filter(function(tr){ return name(tr).indexOf(q) !== -1; })[0];
      if(!hit) return;
      if(hit.classList.contains("rk-m-hide")) setRegion("");
      hit.classList.add("rk-m-hit");
      if(hit.scrollIntoView) hit.scrollIntoView({block:"center", behavior:"smooth"});
    });
    var card = table.closest(".rk-card") || table.parentNode;
    card.insertAdjacentElement("beforebegin", bar);
  }

  /* ------------------------------------------------------------------
     v1.9.72 shared bottom sheet (phones): a title plus a list of actions.
     items: [{label, note, danger, pressed, onClick}]
     ------------------------------------------------------------------ */
  function closeEaSheet(){
    var b = document.getElementById("eaSheetBackdrop"), sh = document.getElementById("eaSheet");
    if(b) b.remove();
    if(sh) sh.remove();
    document.removeEventListener("keydown", eaSheetKey);
  }
  function eaSheetKey(e){ if(e.key === "Escape") closeEaSheet(); }
  function openEaSheet(title, items, foot){
    closeEaSheet();
    var back = document.createElement("div");
    back.id = "eaSheetBackdrop";
    back.className = "ea-sheet-backdrop";
    back.addEventListener("click", closeEaSheet);
    var sh = document.createElement("div");
    sh.id = "eaSheet";
    sh.className = "ea-sheet ea-sheet-menu";
    sh.setAttribute("role", "dialog");
    sh.setAttribute("aria-modal", "true");
    sh.setAttribute("aria-label", title);
    var h = document.createElement("p");
    h.className = "ea-sheet-title";
    h.textContent = title;
    sh.appendChild(h);
    items.forEach(function(it){
      var b = document.createElement("button");
      b.type = "button";
      b.className = "ea-sheet-item" + (it.danger ? " danger" : "");
      if(it.pressed != null){ b.setAttribute("aria-pressed", it.pressed ? "true" : "false"); }
      b.innerHTML = '<span class="l"></span>' + (it.pressed != null ? '<span class="sw" aria-hidden="true"></span>' : "");
      b.querySelector(".l").textContent = it.label;
      b.addEventListener("click", function(){ closeEaSheet(); it.onClick(); });
      sh.appendChild(b);
    });
    if(foot){
      var f = document.createElement("p");
      f.className = "ea-sheet-foot";
      f.textContent = foot;
      sh.appendChild(f);
    }
    var cancel = document.createElement("button");
    cancel.type = "button";
    cancel.className = "ea-sheet-item cancel";
    cancel.textContent = "Close";
    cancel.addEventListener("click", closeEaSheet);
    sh.appendChild(cancel);
    document.body.appendChild(back);
    document.body.appendChild(sh);
    document.addEventListener("keydown", eaSheetKey);
    var first = sh.querySelector(".ea-sheet-item");
    if(first && first.focus) first.focus();
  }
  window.EA_openSheet = openEaSheet;

  /* ------------------------------------------------------------------
     v1.9.72 Dashboard on phones: dashboard tabs get a "⋯" with Rename,
     Delete, From template and Add, routed through the page's own sidebar
     controls so behaviour (prompts, Pro limits, RLS) stays identical.
     ------------------------------------------------------------------ */
  /* v1.9.75: on phones Export leaves the toggles row (Make it real and
     Dollarise get the full width) and sits under the tiles as a labelled
     button, shown only when there is something to export. Desktop keeps it
     at the end of the toggles row. The real button node moves, so its own
     click handler and "Exporting..." labels keep working. */
  function initDashOptions(){
    var grid = document.getElementById("dashGrid");
    var exp = document.getElementById("exportDashboardBtn");
    var row = document.querySelector(".metric-toggles");
    if(!grid || !exp || !row) return;
    var holder = document.getElementById("dashExportRow");
    if(isMobile()){
      if(!holder){
        holder = document.createElement("div");
        holder.id = "dashExportRow";
        holder.className = "dash-export-row";
        grid.insertAdjacentElement("afterend", holder);
      }
      if(exp.parentNode !== holder) holder.appendChild(exp);
      var sync = function(){ holder.hidden = !grid.querySelector(".tile"); };
      sync();
      if(!grid._mobExportWatched){
        grid._mobExportWatched = true;
        new MutationObserver(function(){ var h = document.getElementById("dashExportRow"); if(h) h.hidden = !grid.querySelector(".tile"); })
          .observe(grid, {childList:true});
      }
    } else if(exp.parentNode !== row){
      row.appendChild(exp);
      if(holder) holder.hidden = true;
    }
  }

  function decorateDashTabs(){
    var tabs = document.getElementById("dashMobileTabs");
    var list = document.getElementById("dashSidebarList");
    if(!tabs || !list) return;
    tabs.setAttribute("role", "tablist");
    tabs.setAttribute("aria-label", "Your dashboards");
    var items = $all(".dash-sidebar-item", list);
    $all(".dash-mobile-tab", tabs).forEach(function(tab, i){
      if(tab.classList.contains("dash-mobile-tab-add")){
        tab.setAttribute("role", "button");
        tab.setAttribute("tabindex", "0");
        return;
      }
      var active = tab.classList.contains("active");
      tab.setAttribute("role", "tab");
      tab.setAttribute("aria-selected", active ? "true" : "false");
      tab.setAttribute("tabindex", active ? "0" : "-1");
      if(!active || tab.querySelector(".dash-tab-more")) return;
      var item = items[i];
      if(!item) return;
      var more = document.createElement("button");
      more.type = "button";
      more.className = "dash-tab-more";
      more.setAttribute("aria-label", "Options for " + tab.textContent.trim());
      more.textContent = "\u22EF";
      more.addEventListener("click", function(e){
        e.stopPropagation();
        var name = item.querySelector(".dash-sidebar-item-name");
        var menuBtns = $all(".dash-sidebar-menu button", item);
        var acts = menuBtns.map(function(mb){
          return {label: mb.textContent.trim(), danger: mb.classList.contains("danger"), onClick:function(){ mb.click(); }};
        });
        $all(".dash-sidebar-add", list).forEach(function(add){
          var t = add.textContent.replace(/^\s*[+\u2731]\s*/, "").trim();
          acts.push({label: t === "Add dashboard" ? "New dashboard" : "New " + t.toLowerCase(), onClick:function(){ add.click(); }});
        });
        openEaSheet(name ? name.textContent.trim() : "Dashboard", acts);
      });
      tab.appendChild(more);
    });
  }
  function watchDashTabs(){
    var tabs = document.getElementById("dashMobileTabs");
    if(!tabs || tabs._mobWatched) return;
    tabs._mobWatched = true;
    decorateDashTabs();
    new MutationObserver(function(){ decorateDashTabs(); }).observe(tabs, {childList:true});
  }

  /* ------------------------------------------------------------------
     v1.9.72 UK inactivity reasons bar: on phones, segments too narrow for
     their number lose the in-bar label, and every figure moves into the
     legend so nothing is lost.
     ------------------------------------------------------------------ */
  var REASON_MIN_SHARE = 14; // % of bar width a label needs on a ~343px bar
  function fixReasonBar(){
    var bar = document.getElementById("reasonBar"), legend = document.getElementById("reasonLegend");
    if(!bar || !legend) return;
    var segs = $all("div", bar);
    if(!segs.length) return;
    var mobile = isMobile();
    var total = segs.reduce(function(a, d){ return a + (parseFloat(d.style.flex) || parseFloat(d.style.flexGrow) || 0); }, 0) || 100;
    var spans = $all("span", legend);
    segs.forEach(function(d, i){
      var share = (parseFloat(d.style.flex) || parseFloat(d.style.flexGrow) || 0) / total * 100;
      d.classList.toggle("rb-narrow", mobile && share < REASON_MIN_SHARE);
      var sp = spans[i];
      if(!sp) return;
      var v = sp.querySelector(".rb-v");
      if(mobile){
        if(!v){ v = document.createElement("b"); v.className = "rb-v"; sp.appendChild(v); }
        v.textContent = d.textContent.trim();
      } else if(v){ v.remove(); }
    });
  }
  function watchReasonBar(){
    var bar = document.getElementById("reasonBar");
    if(!bar || bar._mobWatched) return;
    bar._mobWatched = true;
    fixReasonBar();
    new MutationObserver(fixReasonBar).observe(bar, {childList:true});
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
    safeCall(initSlimHeader);
    safeCall(keepActiveChipInView);
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
    safeCall(initDashOptions);
    safeCall(watchDashTabs);
    safeCall(watchReasonBar);
    safeCall(initCompareMobile);
    safeCall(initRankingsTools);
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
    safeCall(initDashOptions); safeCall(fixReasonBar); safeCall(initCompareMobile); safeCall(initRankingsTools);
    alignCountryMapWithSearch();
  });
  window.addEventListener("load", function(){
    setTimeout(init, 400); // second pass after country/compare/calendar data fetches resolve
  });
})();
