/* Consent-gated Google Analytics for generated pages (indicators, rankings, methodology).
   Same storage key and wording as the root pages, so one choice carries across the whole site.
   GA4 never loads before an explicit Accept (or a previously saved "granted"). */
(function () {
  "use strict";
  var GA_MEASUREMENT_ID = "G-PJSXJN5H6G";
  var CONSENT_KEY = "eatlas_cookie_consent";
  function loadGA() {
    if (window._gaLoaded) return;
    window._gaLoaded = true;
    var s = document.createElement("script");
    s.async = true;
    s.src = "https://www.googletagmanager.com/gtag/js?id=" + GA_MEASUREMENT_ID;
    document.head.appendChild(s);
    window.dataLayer = window.dataLayer || [];
    function gtag() { window.dataLayer.push(arguments); }
    window.gtag = gtag;
    gtag("js", new Date());
    gtag("config", GA_MEASUREMENT_ID);
  }
  var banner = document.getElementById("cookieBanner");
  var consent = null;
  try { consent = localStorage.getItem(CONSENT_KEY); } catch (e) {}
  if (consent === "granted") {
    loadGA();
  } else if (consent !== "denied" && banner) {
    banner.classList.add("show");
  }
  var accept = document.getElementById("cookieAccept");
  var reject = document.getElementById("cookieReject");
  if (accept) accept.addEventListener("click", function () {
    try { localStorage.setItem(CONSENT_KEY, "granted"); } catch (e) {}
    if (banner) banner.classList.remove("show");
    loadGA();
  });
  if (reject) reject.addEventListener("click", function () {
    try { localStorage.setItem(CONSENT_KEY, "denied"); } catch (e) {}
    if (banner) banner.classList.remove("show");
  });
})();
