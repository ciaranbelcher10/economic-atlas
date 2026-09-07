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

  /* ------------------------------------------------------------------
     3. COUNTRY PAGES — swipe between sections, dot indicator
     Hooks into the page's own global showSec(name) function rather
     than re-implementing section switching.
     ------------------------------------------------------------------ */
  function initCountrySwipe(){
    var nav = document.querySelector("nav.cat");
    if(!isMobile() || !nav || typeof window.showSec !== "function") return;
    var btns = $all("button", nav);
    if(!btns.length) return;

    var hint = document.createElement("div");
    hint.className = "sec-swipehint";
    btns.forEach(function(){ hint.appendChild(document.createElement("span")); });
    nav.insertAdjacentElement("afterend", hint);

    function syncDots(){
      var activeIdx = btns.findIndex(function(b){ return b.classList.contains("active"); });
      $all("span", hint).forEach(function(dot, i){ dot.classList.toggle("active", i===activeIdx); });
    }
    var mo = new MutationObserver(syncDots);
    btns.forEach(function(b){ mo.observe(b, {attributes:true, attributeFilter:["class"]}); });
    syncDots();

    var startX = null, startY = null;
    var main = document.querySelector("main") || document.body;
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
      var idx = btns.findIndex(function(b){ return b.classList.contains("active"); });
      var next = dx < 0 ? idx+1 : idx-1;
      if(next < 0 || next >= btns.length) return;
      window.showSec(btns[next].dataset.sec);
      btns[next].scrollIntoView({inline:"center", block:"nearest"});
    }, {passive:true});
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
  function initCalendarAgenda(){
    if(!isMobile()) return;
    if(typeof window.EVENTS === "undefined" || typeof window.eventsForDate !== "function") return;
    var grid = document.querySelector(".cal-grid");
    if(!grid) return;

    var agenda = document.getElementById("calAgenda");
    var heading = document.getElementById("calAgendaHeading");
    if(!agenda){
      heading = document.createElement("p");
      heading.id = "calAgendaHeading";
      heading.className = "cal-agenda-title";
      heading.textContent = "This month's tracked releases";
      agenda = document.createElement("div");
      agenda.id = "calAgenda";
      // Insert relative to the day-detail box (present on every calendar
      // build) rather than relying on .cal-grid's exact position, so this
      // keeps working even if that markup shifts around in future edits.
      var dayDetail = document.getElementById("calDayDetail");
      var anchor = dayDetail || grid;
      anchor.insertAdjacentElement("beforebegin", heading);
      anchor.insertAdjacentElement("beforebegin", agenda);
    }

    var METRIC_COLOURS = {
      gdp:"#2E6FA7", cpi:"#C97A2B", jobs:"#2E8B57", rate:"#C4453B",
      ppi:"#7B5EC9", pce:"#C13D8A", trade:"#B99A2C", public:"#5C6470"
    };
    function colourFor(ev){
      return METRIC_COLOURS[ev.concept] || METRIC_COLOURS[(ev.type||"").toLowerCase()] || "#37659E";
    }

    function renderAgenda(){
      var yr = window.viewYear, mo = window.viewMonth;
      var names = window.MONTH_NAMES || ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
      var daysInMonth = new Date(yr, mo+1, 0).getDate();
      var today = new Date(); today.setHours(0,0,0,0);
      var jumpDays = [];
      var html = "";
      for(var d=1; d<=daysInMonth; d++){
        var dateObj = new Date(yr, mo, d);
        var iso = dateObj.getFullYear()+"-"+String(dateObj.getMonth()+1).padStart(2,"0")+"-"+String(dateObj.getDate()).padStart(2,"0");
        var evs = window.eventsForDate(iso) || [];
        if(!evs.length) continue; // agenda view only lists days with tracked releases
        var isToday = dateObj.getTime()===today.getTime();
        jumpDays.push({d:d, iso:iso});
        html += '<div class="cal-agenda-day'+(isToday?" is-today":"")+'" id="agenda-day-'+d+'">';
        html += '<div class="d-head"><span class="d-num">'+d+'</span><span class="d-dow">'+dateObj.toLocaleDateString(undefined,{weekday:"short"})+(isToday?" \u00b7 Today":"")+'</span></div>';
        evs.forEach(function(ev){
          html += '<div class="cal-agenda-pill" style="background:'+colourFor(ev)+'">';
          html += '<span class="dot" aria-hidden="true"></span>';
          html += '<span class="country">'+(ev.country||"")+'</span> \u2014 '+(ev.title||ev.name||ev.concept||"Release");
          html += '</div>';
        });
        html += '</div>';
      }
      if(!html){
        html = '<p class="cal-agenda-empty">No tracked releases in '+names[mo]+' '+yr+'.</p>';
      }
      agenda.innerHTML = html;

      var jump = document.getElementById("calAgendaJump");
      if(!jump){
        jump = document.createElement("div");
        jump.id = "calAgendaJump";
        jump.className = "cal-jump";
        agenda.insertAdjacentElement("beforebegin", jump);
      }
      var jumpHtml = "";
      for(var d2=1; d2<=daysInMonth; d2++){
        var has = jumpDays.some(function(j){ return j.d===d2; });
        jumpHtml += '<button type="button" data-d="'+d2+'" class="'+(has?"has-events":"")+'">'+d2+'</button>';
      }
      jump.innerHTML = jumpHtml;
      $all("button", jump).forEach(function(btn){
        btn.addEventListener("click", function(){
          var target = document.getElementById("agenda-day-"+this.dataset.d);
          if(target) target.scrollIntoView({behavior:"smooth", block:"start"});
        });
      });
    }

    if(!window._mobCalPatched){
      window._mobCalPatched = true;
      var origRenderMonth = window.renderMonth;
      if(typeof origRenderMonth === "function"){
        window.renderMonth = function(){
          origRenderMonth.apply(this, arguments);
          if(isMobile()) renderAgenda();
        };
      }
    }
    renderAgenda();
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
  function initDashboardSearch(){
    if(!isMobile()) return;
    var grid = document.getElementById("metricPickerGrid");
    if(!grid) return;
    addPickerSearch("metricPickerGrid", "dashMetricSearchWrap", "dashMetricSearch", "Search countries or metrics\u2026");
  }
  function initCompareMetricSearch(){
    if(!isMobile()) return;
    addPickerSearch("metricPickerGrid", "dashMetricSearchWrap", "dashMetricSearch", "Search countries or metrics\u2026");
    addPickerSearch("pickerRegions", "pickerSearchWrap", "pickerSearch", "Search countries\u2026");
  }

  /* ------------------------------------------------------------------
     init
     ------------------------------------------------------------------ */
  function init(){
    buildToolbar();
    addMapCaption();
    initCountrySwipe();
    addTradeNote();
    watchCompareTable();
    watchComparePage();
    initCompareMetricSearch();
    initDashboardSearch();
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
