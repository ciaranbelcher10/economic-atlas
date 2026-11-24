# v2.0.15: Phase 3 (SEO and readability for search engines and AI assistants), part 1

## Audit (already in place, unchanged)
Every listed page has a canonical link, Open Graph and Twitter cards, and a unique title and description. robots.txt allows all crawlers and names the sitemap; the sitemap has 1,199 URLs with per-page lastmod; llms.txt exists. Country pages carry a plain-text summary of the latest figures in the HTML, and the indicator pages lead with the figure ("UK Inflation Rate: 3.6% (Oct 2026)"). Long titles and descriptions are cut only at their tail, so they are left as they are.

## Changed
1. **Dataset structured data** (1,109 indicator pages and the ranking pages), built by generate_indicator_pages.py:
   - `creator` is the original publisher, matched from the source line, most specific agency first: Office for National Statistics, Bank of England, U.S. Bureau of Labor Statistics, Cabinet Office of Japan, Eurostat, IMF and so on (23 publishers). Before, every page named The Economic Atlas as creator. Only one page falls back (none now: Taiwan's central bank was added).
   - `publisher` is The Economic Atlas.
   - `isAccessibleForFree` is true.
   - `spatialCoverage` is a Place with the full name ("United Kingdom", not "UK").
   - These fields support eligibility for Google Dataset Search.
2. **Structured data on the 8 main pages that had none** (tools/migrate_v215.py): About (AboutPage), Contact (ContactPage), Calendar, Markets, Privacy and Terms (WebPage), Chartmaker and My Dashboard (WebApplication, free). Each is built from the page's own title, description and canonical link.

Rehearsed on a fresh main: the migration changed 8 files and the generator ran cleanly; html_gate and generated_pages_gate report 0 failures. All 1,123 Dataset entries parse with publisher and isAccessibleForFree.

## Deploy (Claude Code)
1. Verify the sha256, run `git pull`, then unzip at the repo root.
2. Run `python3 tools/migrate_v215.py` (expect 8 files), then run it again (expect 0).
3. Run `python3 generate_indicator_pages.py`. This regenerates the indicator and ranking pages with the new structured data, as the hourly bot does.
4. Run `python3 tools/html_gate.py` and `python3 tools/generated_pages_gate.py` (expect 0 failures each).
5. `git add -u && xargs git add < FILES.txt`, commit "v2.0.15: Dataset structured data credits the original publisher; structured data on main pages" and push.
