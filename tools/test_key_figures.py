"""Behavioural tests for the country-page key figures block (v1.9.28).   python3 tools/test_key_figures.py"""
import importlib.util, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
spec = importlib.util.spec_from_file_location("g", os.path.join(ROOT, "generate_indicator_pages.py"))
g = importlib.util.module_from_spec(spec); spec.loader.exec_module(g)

n = fails = 0
def check(name, got, want):
    global n, fails
    n += 1
    if got != want:
        fails += 1
        print(f"FAIL {name}: got {got!r}, want {want!r}")

PAGE = '<html><script type="application/ld+json">{\n  "@type": "Dataset",\n  "isAccessibleForFree": true,\n}</script><h1>Testland</h1><main>x</main><footer>f</footer></html>'
def blk(value):
    return lambda st: f'{g.KF_START}<p><time class="kf-date" datetime="{st}">{g.fmt_day(st)}</time> {value}</p>{g.KF_END}'

a = g.inject_key_figures(PAGE, blk("1.0%"), "2026-10-01")
check("block placed once", a.count(g.KF_START), 1)
check("block sits before the footer", a.index(g.KF_END) < a.index("<footer"), True)
check("Dataset date set", '"dateModified": "2026-10-01",' in a, True)
b = g.inject_key_figures(a, blk("1.0%"), "2026-10-30")
check("unchanged figures keep the old date, page identical", b, a)
c = g.inject_key_figures(a, blk("1.1%"), "2026-10-30")
check("changed figure takes today's date", '<time class="kf-date" datetime="2026-10-30">' in c, True)
check("changed figure moves the Dataset date", ('"dateModified": "2026-10-30",' in c, c.count('"dateModified"')), (True, 1))
check("still one block after a change", c.count(g.KF_START), 1)
try:
    g.inject_key_figures("<html>no footer</html>", blk("1"), "2026-10-30")
    check("no footer raises", False, True)
except ValueError:
    check("no footer raises", True, True)

check("the before names", (g.kf_name("United Kingdom"), g.kf_name("Japan"), g.kf_name("Netherlands")), ("the United Kingdom", "Japan", "the Netherlands"))
check("label keeps the bracketed unit", g.kf_label("Government Debt (% of GDP)"), "government debt (% of GDP)")
check("publisher: FRED mirror of IMF", g.kf_publisher("FRED series NGDPSAXDCDEQ \u00b7 IMF International Financial Statistics, quarterly."), "IMF via FRED")
check("publisher: NGDPSAXD is not PSA", g.kf_publisher("FRED series NGDPSAXDCAUQ (IMF International Financial Statistics), quarterly."), "IMF via FRED")
check("publisher: bare FRED id mapped", g.kf_publisher("FRED series ECBDFR \u00b7 end-of-month value."), "ECB via FRED")
check("publisher: ONS", g.kf_publisher("ONS series D7G7 (MM23)"), "ONS")
check("publisher: earliest named wins", g.kf_publisher("Central Reserve Bank of Peru (BCRP), series PN01273PM, from INEI"), "Central Reserve Bank of Peru")
check("publisher: derived names the base", g.kf_publisher("Calculated from real GDP, each period. Real GDP: Eurostat namq_10_gdp"), "Eurostat")

# a hand-written Dataset that already ends with its own dateModified: updated in place, never duplicated
OLD = PAGE.replace('  "isAccessibleForFree": true,\n}', '  "isAccessibleForFree": true,\n  "dateModified": "2026-08-04"\n}')
d = g.inject_key_figures(OLD, blk("1.0%"), "2026-10-01")
check("existing dateModified updated, not duplicated", (d.count('"dateModified"'), '"dateModified": "2026-10-01"' in d), (1, True))
# a page from v1.9.28 that already carries both keys is repaired
BOTH = OLD.replace('  "isAccessibleForFree": true,', '  "dateModified": "2026-10-30",\n  "isAccessibleForFree": true,')
e2 = g.inject_key_figures(BOTH, blk("1.0%"), "2026-10-31")
check("v1.9.28 duplicate repaired", (e2.count('"dateModified"'), '"dateModified": "2026-10-31"' in e2), (1, True))
check("repaired page is stable on the next run", g.inject_key_figures(e2, blk("1.0%"), "2026-11-02"), e2)

print(f"test_key_figures: {n} checks, {fails} failures")
sys.exit(1 if fails else 0)
