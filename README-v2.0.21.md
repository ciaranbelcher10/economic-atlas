# v2.0.21: a mouse wheel scrolls the page instead of zooming maps and charts

With a mouse, scrolling over a map or chart zoomed it and the page stopped scrolling.
Now a plain wheel always scrolls the page. Ctrl + wheel (Command + wheel on a Mac, or a trackpad pinch)
zooms maps; Ctrl + wheel or a trackpad pinch zooms charts. Touch screens are unchanged.

- Maps: homepage, the mini-map and trade-partners map on every country page, Compare, Dashboard.
  A plain wheel shows "Ctrl + scroll to zoom the map" for a moment.
- Charts: country pages and Dashboard (drag-to-zoom unchanged).
- Map hint: "Ctrl + scroll or pinch to zoom" ("Pinch to zoom" on touch screens, the Command symbol on a Mac).

Applied by `tools/migrate_v221.py` (idempotent) rather than shipped as whole pages, so the hourly
data commits to the country pages cannot clash. Test: `tools/test_v221_wheel.js` (65 pages, 585 checks).
