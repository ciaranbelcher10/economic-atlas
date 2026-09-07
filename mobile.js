/* ==========================================================================
   The Economic Atlas — mobile.js
   Loaded on every page after the page's own scripts. Everything here is
   gated behind an isMobile() check and feature-detects the elements it
   needs, so this single file is safe to include sitewide: it does nothing
   on pages/sections it doesn't recognise, and does nothing at all on
   desktop/tablet widths.
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
    { file:"data.json",     slug:"uk",      name:"UK",      flag:"\uD83C\uDDEC\uD83C\uDDE7" },
    { file:"data-de.json",  slug:"germany", name:"Germany", flag:"\uD83C\uDDE9\uD83C\uDDEA" },
    { file:"data-jp.json",  slug:"japan",   name:"Japan",   flag:"\uD83C\uDDEF\uD83C\uDDF5" },
    { file:"data-fr.json",  slug:"france",  name:"France",  flag:"\uD83C\uDDEB\uD83C\uDDF7" },
    { file:"data-br.json",  slug:"brazil",  name:"Brazil",  flag:"\uD83C\uDDE7\uD83C\uDDF7" },
    { file:"data-in.json",  slug:"india",   name:"India",   flag:"\uD83C\uDDEE\uD83C\uDDF3" }
  ];
  var TICKER_METRICS = [
    { key:"cpi", label:"inflation", fmt:function(v){ return v.toFixed(1)+"%"; } },
    { key:"unemployment", label:"unemployment", fmt:function(v){ return v.toFixed(1)+"%"; } }
  ];

  function fetchTickerFacts(cb){
    var facts = [];
    var pending = TICKER_COUNTRIES.length;
    function done(){ pending--; if(pending === 0) cb(facts); }
    TICKER_COUNTRIES.forEach(function(c){
      fetch(c.file, {cache:"no-cache"}).then(function(r){
        if(!r.ok) throw new Error("HTTP "+r.status);
        return r.json();
      }).then(function(data){
        var series = data.series || {};
        TICKER_METRICS.forEach(function(m){
          var s = series[m.key];
          if(!s || !s.points || s.points.length < 2) return;
          var pts = s.points;
          var latest = pts[pts.length-1], prior = pts[pts.length-2];
          if(latest[1] == null || prior[1] == null) return;
          facts.push({
            country:c.name, slug:c.slug, flag:c.flag, metricLabel:m.label,
            value:m.fmt(latest[1]), delta:+(latest[1]-prior[1]).toFixed(2),
            period:latest[0]
          });
        });
        done();
      }).catch(function(){ done(); });
    });
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

    fetchTickerFacts(function(facts){
      if(!facts.length) return;
      var strip = document.createElement("div");
      strip.id = "homeTicker";
      strip.setAttribute("aria-label", "Today's figures");
      strip.innerHTML = facts.map(function(f){
        var arrow = f.delta > 0 ? "\u25B2" : (f.delta < 0 ? "\u25BC" : "\u2013");
        var cls = f.delta > 0 ? "up" : (f.delta < 0 ? "down" : "flat");
        return '<a class="ht-item" href="'+f.slug+'">'+f.flag+' <b>'+f.country+'</b> '+f.metricLabel+' '+f.value
          + ' <span class="ht-delta '+cls+'">'+arrow+' '+Math.abs(f.delta).toFixed(1)+'pp</span></a>';
      }).join("");
      marker.insertAdjacentElement("afterend", strip);
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
    if(document.getElementById("homeScrollCatch")) return;
    var shown = false;
    window.addEventListener("scroll", function onScroll(){
      if(shown) return;
      if(window.scrollY < window.innerHeight * 0.9) return;
      shown = true;
      window.removeEventListener("scroll", onScroll);
      var bar = document.createElement("div");
      bar.id = "homeScrollCatch";
      bar.innerHTML =
        '<input type="text" id="scrollCatchInput" placeholder="Jump to a country\u2026" autocomplete="off">' +
        '<button type="button" id="scrollCatchClose" aria-label="Dismiss">&times;</button>';
      document.body.appendChild(bar);
      requestAnimationFrame(function(){ bar.classList.add("visible"); });
      var input = document.getElementById("scrollCatchInput");
      input.addEventListener("focus", function(){
        var main = document.getElementById("hqnSearch");
        if(main){ main.scrollIntoView({behavior:"smooth", block:"center"}); main.focus(); bar.remove(); }
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
  function initHomeQuickNav(){
    var heroHeading = document.querySelector(".hero-h1");
    var subline = document.querySelector(".subline");
    if(!heroHeading || !subline || document.getElementById("homeQuickNav")) return;
    var links = $all("#macroPanel a[href]").filter(function(a){ return a.getAttribute("href") !== "index"; });
    if(!links.length) return;

    var POPULAR = ["uk","us","germany","japan","france","brazil","india","china"];
    var popular = [];
    POPULAR.forEach(function(slug){
      var a = links.find(function(l){ return l.getAttribute("href") === slug; });
      if(a) popular.push(a);
    });
    if(popular.length < 4){ popular = links.slice(0, 8); }

    var box = document.createElement("div");
    box.id = "homeQuickNav";
    box.innerHTML =
      '<div class="hqn-searchwrap">' +
        '<input type="text" id="hqnSearch" placeholder="Jump straight to a country\u2026" autocomplete="off">' +
        '<div class="hqn-results" id="hqnResults" hidden></div>' +
      '</div>' +
      '<div class="hqn-popular" id="hqnPopular">' +
        popular.map(function(a){ return '<a href="'+a.getAttribute("href")+'">'+a.textContent+'</a>'; }).join("") +
      '</div>';
    subline.insertAdjacentElement("afterend", box);

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

  /* ------------------------------------------------------------------
     5. COMPARE PAGE — stacked cards from the existing rank table,
     search box in the country picker.
     ------------------------------------------------------------------ */
  function tableToCards(){
    if(!isMobile()) return;
    var table = document.getElementById("rankTable");
    if(!table) return;
    var wrap = table.closest("div");
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

  /* ------------------------------------------------------------------
     init
     ------------------------------------------------------------------ */
  function init(){
    buildToolbar();
    addMapCaption();
    initHomeQuickNav();
    initHomeTicker();
    initSearchPlaceholderRotation();
    initScrollCatch();
    initCountrySwipe();
    initMapCollapse();
    addTradeNote();
    watchCompareTable();
    watchComparePage();
    initCompareCountrySearch();
    initCalendarAgenda();
    fixStaleCalendarCopy();
    simplifyCalendarCopy();
    chartmakerGate();
  }

  if(document.readyState === "loading"){
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
  // Re-run the cheap, idempotent bits after async page data loads and on resize/orientation change.
  window.addEventListener("resize", function(){
    addTradeNote(); tableToCards(); chartmakerGate(); simplifyComparePage(); simplifyCalendarCopy();
  });
  window.addEventListener("load", function(){
    setTimeout(init, 400); // second pass after country/compare/calendar data fetches resolve
  });
})();
