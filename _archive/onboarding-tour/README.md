# Onboarding tour (archived in v1.9.1)

The guided first-visit tour was removed from the live site in v1.9.1. Everything it used is kept here so it can be brought back.

This folder is not published: GitHub Pages builds the site with Jekyll, which skips folders whose names start with an underscore.

## What the tour was

A step-by-step box that walked a visitor through the homepage, the UK page, Compare and the Dashboard (27 steps, defined in `TOUR_STEPS`). It ran on five pages: `index.html`, `uk.html`, `compare.html`, `dashboard.html` and `methodology.html`. At the time of removal it was already switched off: auto-start sat inside `if(false)`, and `style.css` hid the footer "Take the tour" button.

## What was removed

- `tour-engine.txt`: the engine `<script>` block (identical on all five pages apart from the `THIS_PAGE` line, listed at the top of the file).
- `tour.css.txt`: three pieces of `style.css` (the box, the highlight pulse, the hidden button rule, and the narrow-screen sizing).
- `page-hooks.txt`: the footer button on each page, the banner rule that waited for the tour box to close, the UK page's `window.openChartModal`, `window.closeChartModal` and `window.ANCHORS` exposures, four `window.EATLAS_COMPARE` members (`toggleCountry`, `addMetric`, `openCountryModal`, `closeCountryModal`) and comments that described the tour.

Kept on purpose: `window.EATLAS_COMPARE` (Compare's Customise & Export modal uses it), `window.EATLAS_DASH.ensurePinned` (used by `tools/test_dashboard_inflation.js`) and the `data-key`, `data-country` and `data-metric` attributes.

## How to bring it back

Easiest, if those six files have not changed much since v1.9.1. From the repo root:

```
git apply --check _archive/onboarding-tour/restore.patch
git apply _archive/onboarding-tour/restore.patch
```

This returns `index.html`, `uk.html`, `compare.html`, `dashboard.html`, `methodology.html` and `style.css` to exactly their pre-removal state for the tour parts (tested when archived). The tour would still be off, as it was then: to switch it on, change `if(false){` near the end of the engine block back to the condition you want on each page, and delete `#tourReplayWrap{display:none;}` from `style.css` to show the footer button.

If the patch no longer applies, paste the pieces back by hand using the three `.txt` files, which say where each piece went. The full pre-removal pages are also in git history: the commit before the v1.9.1 commit.

## Before reusing it

Some step text is out of date. The first step says the site checks official data "every hour", which the v2.0 roadmap asks to soften unless the run history supports it. Steps point at specific buttons and charts by id, so check each step still finds its target.
