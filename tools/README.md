# Audit tools

Reusable harnesses built during the fourth site audit (September 2026). They
exist because that audit's find rate was limited by tooling rather than by
remaining defect density: each new harness unlocked a category of defect that
had been invisible to greps and reading.

Nothing in here is served content or touched by any workflow. These are
developer tools, run by hand.

## Setup

They locate the repo automatically as the parent of this directory, so from a
clone you can just run them:

```
python3 tools/citation_ids.py
node tools/sampledata_gate.js
```

Override with `ATLAS_REPO=/path/to/clone` if you keep them elsewhere.

Requires `python3` and `node`. No third-party packages.

---

## `history_walk.py` — series shape over git history

**Needs a full clone, not `--depth 1`.** On a shallow clone it reports one
revision per file and finds nothing.

```
python3 tools/history_walk.py walk     # writes tools/history_shapes.json
python3 tools/history_walk.py report   # flags drops, frequency changes, oscillation
```

Reconstructs every series' shape at every commit that touched its data file,
then flags point-count drops, frequency downgrades, start dates moving
forward, provider label changes, and series that oscillate between two states.

**What it found:** Poland's CPI serving 7 points where it should have 139,
oscillating across four shapes for weeks, plus four more live oscillations
nobody had seen. This is the tool that justifies a deep clone.

A useful follow-on question it answers: for each series, current point count
against its own historical maximum. Anything well below its own best is either
a silent truncation or a deliberate swap, and the difference is usually
visible in whether the label changed too.

## `citation_ids.py` — citation identifiers against fetch scripts

```
python3 tools/citation_ids.py
```

Compares the series identifier quoted in each `data-metric-sources.json` entry
against the identifier the country's fetch script actually uses. The sitewide
citation check matches provider *names* only, so a citation naming the wrong
FRED series from the right provider passes straight through it.

**What it found:** 17 mismatches. Colombia's employment rate popover cited the
ages 15-64 series while the script fetched the 15-and-over one, so the figure
was described as a different population than it measured. Fourteen citations
named a Eurostat dataset that does not exist. Sweden's government finance
citations had been copied from Norway's and never updated.

Expected clean result: `MISMATCH 0`. `UNCITED` counts citations naming no
identifier at all, which is a smaller issue and partly a false positive for
the UK, because `fetch_data.py` serves both the UK and the US and the resolver
cannot tell which table a UK metric belongs to.

## `run_surface.py` — extract and exercise a page module

```
python3 tools/run_surface.py calendar.html EATLAS_PREFS
```

Pulls a named `window.X = (function(){...})()` module out of a page by brace
matching and writes it to `tools/_extracted.js`, so it can be run under node
with a stubbed DOM and its failure branches actually exercised rather than
read.

**What it found:** `EATLAS_PREFS` exists in seven different implementations
across 41 pages, and only `compare.html` persists anonymous preferences. It
also ruled out three suspected defects that a grep would have flagged.

## `promise_extract.py` — testable claims from prose pages

```
python3 tools/promise_extract.py methodology.html
```

Extracts visible text, splits into sentences, and flags the ones making
testable claims: universals (every, all, always, never), cadence promises,
coverage counts, provenance and forecast claims.

**What it found:** the methodology page claimed national statistical office
sourcing "for every country covered" when 10 of 36 data files have one, and
told visitors their trade data might come from a feed discontinued in April
2023 when it is current to last month.

Pay attention to both directions. Behaviour falling short of a promise is a
defect; behaviour exceeding a stale description is also a defect, because the
documentation is wrong and the site is underselling itself.

## `sampledata_gate.js` — execute every country page's `sampleData()`

```
node tools/sampledata_gate.js
```

Runs each country page's `sampleData()` under a stubbed DOM and asserts every
series is non-empty and every point numeric and finite. `node --check` is
blind to runtime errors like a deleted variable initialisation; this is not.

Expected: **32 of 32 clean, 431 series, 72,576 points.** Exit code 1 on any
failure. Run it before every package.

The page blocks are `"use strict"`, so function declarations do not leak to
`globalThis` and `sampleData` has to be captured from inside the eval scope.
It returns `{updated, sample, series:{...}}`, not a bare series map.

## `test_guard.py` — behavioural tests for `series_guard.py`

```
python3 tools/test_guard.py
```

Sixteen branches covering what the shrinkage guard must block, what it must
allow, the stale exemption, the `ALLOW_SHRINK` override, grafting, and the
failure paths. If `tools/history_shapes.json` exists from `history_walk.py`,
it also replays the guard against every recorded shape transition.

Run this after any change to `series_guard.py`.

## `shape_harness.py` — inventory and point-in-time diff

```
python3 tools/shape_harness.py inventory HEAD     # TSV of every (country, metric)
python3 tools/shape_harness.py diff <commitA> <commitB>
```

The inventory is the artefact to read *before* forming a hypothesis. Almost
every real finding in the audit was first visible as a row that did not look
like its siblings: one country's growth rate on a different price basis, one
country's CPI starting eleven years later than everyone else's.

---

## The most important lesson from that audit

`py_compile` is not enough. It passes on an undefined name.

A bulk edit across the fetch scripts once left 21 of them calling a helper
that was never defined, which would have failed 21 country pipelines at
runtime. It was caught only by *importing* each module:

```
for f in fetch_*.py; do
  python3 -c "
import importlib.util
sp=importlib.util.spec_from_file_location('m','$f'); m=importlib.util.module_from_spec(sp)
try: sp.loader.exec_module(m)
except SystemExit: pass
" || echo "IMPORT FAIL $f"
done
```

Expected: 70 pass, 0 failures. Make this part of every gate run.

The cause was a "symbol already present" check that matched the symbol inside
the replacement text it had just inserted. That same mistake happened three
times in one session. When writing a bulk migration, check for `def name`,
never the bare `name`.
