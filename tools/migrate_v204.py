#!/usr/bin/env python3
"""v2.0.4 migration: Phase 1 of the v2.0 production list.

Applies every v2.0.4 text edit to the working tree as it stands (so it can
run after v2.0.3 or any data-bot commit without overwriting them).
Idempotent: a second run changes nothing and reports 0.

1. Country-page footers: rewrite the "not available" sentences so they match
   the data each page actually carries (UK and US no longer claim to lack a
   10-year yield, etc.), in plain declarative wording.
2. Section notes contradicted by the data: removed or corrected (exports and
   imports for BR/CA/DK/MX/KR, Singapore's 10-year yield, TH/MA long-term yield).
3. "Not an oversight" wording removed from metric sources and the two
   generated indicator pages that carry it.
4. Terms of Service: colloquial asides removed; "check the original
   publisher" line added.
5. Sign-up form: a Terms of Service / Privacy notice with two buttons, shown
   in Sign up mode only, on every page with the auth modal and in the
   indicator page generator.

Run from the repo root: python3 tools/migrate_v204.py
"""
import glob
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
changed = set()


def rd(p):
    return open(os.path.join(ROOT, p), encoding="utf-8").read()


def wr(p, t):
    with open(os.path.join(ROOT, p), "w", encoding="utf-8") as f:
        f.write(t)
    changed.add(p)


# ---------------------------------------------------------------- 1. footers
P = "Productivity (GDP per hour worked) is currently only tracked for the UK and US."


def ex(c):
    return f"Exports and imports are not available separately for {c}, so only the trade balance is shown."


FOOT = {
    "argentina": "No reliable live source is currently available for Argentina's policy interest rate, current account balance or labour force participation, so they are not shown.",
    "australia": ex("Australia"),
    "brazil": "No live 10-year government bond yield source is available for Brazil. Unemployment is annual (World Bank), as the monthly series for Brazil stopped updating in 2015. Nominal GDP uses a not seasonally adjusted series (the seasonally adjusted version stopped updating in 2025), so quarter-on-quarter GDP growth can look noisier than on other country pages.",
    "canada": P,
    "chile": ex("Chile"),
    "colombia": ex("Colombia"),
    "denmark": None,
    "eurozone": P,
    "indonesia": "No reliable live source is currently available for Indonesia's policy interest rate, current account balance or labour force participation, so they are not shown.",
    "israel": ex("Israel"),
    "japan": P,
    "mexico": None,
    "morocco": "GDP, real GDP and unemployment are annual World Bank figures rather than the quarterly or monthly data shown for most other countries. No goods trade series or business confidence indicator is available for Morocco. The long-term government bond yield follows the national maturity definition and is not a 10-year series. " + P,
    "norway": ex("Norway"),
    "poland": "No reliable live source is currently available for Poland's current account balance, so it is not shown.",
    "singapore": "No reliable live source is currently available for Singapore's policy interest rate, general government fiscal deficit or labour force participation, so they are not shown. The debt figure is central government debt (World Bank), not the general government measure used on most other country pages; most of Singapore's government debt is issued to develop domestic capital markets and invest reserves rather than to fund a deficit. Real GDP growth is annual, as no live quarterly source is available.",
    "southafrica": ex("South Africa"),
    "southkorea": None,
    "sweden": "Exports and imports are not available separately for Sweden, so only the trade balance is shown. Labour force participation and the employment rate are not yet available for Sweden.",
    "switzerland": "No reliable live source is currently available for Switzerland's policy interest rate, labour force participation, current account balance or general government fiscal deficit, so they are not shown. The 10-year government bond yield is shown under Markets.",
    "thailand": "No reliable live source is currently available for Thailand's policy interest rate, current account balance, general government fiscal deficit or labour force participation, so they are not shown. The debt figure is central government debt (World Bank), not the general government measure used on most other country pages. Real GDP growth is annual, as no live quarterly source is available. The long-term government bond yield follows the national maturity definition and is not a 10-year series.",
    "turkey": "No reliable live source is currently available for Turkey's policy interest rate (the OECD short-term rate series stopped updating in December 2023) or current account balance (discontinued in 2013), so they are not shown.",
    "uk": None,
    "us": None,
}
for page, new in FOOT.items():
    fn = page + ".html"
    t = rd(fn)
    a = t.rfind("<footer>")
    b = t.find('<div class="lnk-row">', a)
    assert a != -1 and b != -1, fn
    seg = t[a:b]
    k = seg.find("may be revised.")
    assert k != -1, fn
    k += len("may be revised.")
    rep = seg[:k] + ("\n " + new if new else "") + "\n "
    if rep != seg:
        wr(fn, t[:a] + rep + t[b:])

# ------------------------------------------------------------ 2. section notes
def secnote_fix(page, old, new):
    fn = page + ".html"
    t = rd(fn)
    if old in t:
        assert t.count(old) == 1, (fn, t.count(old))
        wr(fn, t.replace(old, new))


for c, name in [("brazil", "Brazil"), ("canada", "Canada"), ("denmark", "Denmark"),
                ("mexico", "Mexico"), ("southkorea", "South Korea")]:
    secnote_fix(c, f'<p class="secnote">Exports and imports are not available separately for {name}, so only the trade balance is shown.</p>', "")
secnote_fix("singapore", '<p class="secnote">No 10-year government bond yield is available for Singapore.</p>', "")
for c, name in [("thailand", "Thailand"), ("morocco", "Morocco")]:
    secnote_fix(c, f'<p class="secnote">No 10-year government bond yield is available for {name}.</p>',
                f'<p class="secnote">No 10-year government bond yield is available for {name}. The long-term yield shown follows the national maturity definition.</p>')

# ------------------------------------------------- 3. "not an oversight" text
OVS = " like most other pages on this site, a genuine data-availability difference, not an oversight."
for fn in ["data-metric-sources.json", "indicators/thailand-gdp-growth-rate.html", "indicators/singapore-gdp-growth-rate.html"]:
    t = rd(fn)
    if OVS in t:
        wr(fn, t.replace(OVS, " like most other pages on this site."))

# ------------------------------------------------------------- 4. terms page
TERMS = [
    (" The rest of this page is the detail behind that, because a one-line policy isn't a real one.", " The rest of this page sets out the detail."),
    ("may change over time, features can be added, removed, or restructured as the product develops.", "may change over time: features can be added, removed or restructured as the product develops."),
    ("used here under their own open licences, we're republishing, not claiming to own the numbers.", "used here under their own open licences. The Economic Atlas republishes these figures and does not claim ownership of them."),
    ("If these terms change, this page gets updated to match, the same way our Privacy page works, meant to describe reality, not a fixed document nobody rereads.", "If these terms change, this page is updated to match."),
    ("Known gaps are disclosed honestly on the relevant page's own footer rather than hidden.", "Known gaps in coverage are noted on the relevant page. Please check any figure against its original publisher before relying on it."),
]
t = rd("terms.html")
t0 = t
for a, b in TERMS:
    if a in t:
        assert t.count(a) == 1, a
        t = t.replace(a, b)
if t != t0:
    wr("terms.html", t)

# --------------------------------------------------- 5. sign-up terms notice
H_OLD = '<button type="submit" class="btn auth-submit" id="authSubmitBtn">Log in</button>'


def h_new(pre):
    return ('<div class="auth-terms" id="authTermsRow" hidden style="margin:2px 0 12px;font-size:12.5px;line-height:1.5;color:var(--ink2)">'
            '<p style="margin:0 0 8px">Creating an account means you accept the Terms of Service and Privacy policy.</p>'
            f'<a class="ea-btn sm" href="{pre}terms" target="_blank" rel="noopener">Terms of Service</a> '
            f'<a class="ea-btn sm" href="{pre}privacy" target="_blank" rel="noopener">Privacy policy</a></div>\n ' + H_OLD)


J_OLD = "  function setMode(newMode){\n    mode = newMode;\n"
J_NEW = J_OLD + '    var authTermsRow = document.getElementById("authTermsRow"); if(authTermsRow) authTermsRow.hidden = (mode === "login");\n'
targets = [os.path.relpath(f, ROOT) for f in glob.glob(os.path.join(ROOT, "**", "*.html"), recursive=True)
           if os.sep + "_archive" + os.sep not in f]
targets.append("generate_indicator_pages.py")
for fn in targets:
    t = rd(fn)
    if H_OLD not in t or 'id="authTermsRow"' in t:
        continue
    assert t.count(H_OLD) == 1 and t.count(J_OLD) == 1, (fn, t.count(H_OLD), t.count(J_OLD))
    # the generator's template is for /indicators/ pages; it rewrites ../ for root pages itself
    pre = "../" if (os.sep in fn or fn == "generate_indicator_pages.py") else ""
    wr(fn, t.replace(H_OLD, h_new(pre)).replace(J_OLD, J_NEW))

print(f"migrate_v204: {len(changed)} files changed")
for p in sorted(changed)[:40]:
    print("  " + p)
if len(changed) > 40:
    print(f"  ... and {len(changed) - 40} more")
sys.exit(0)
