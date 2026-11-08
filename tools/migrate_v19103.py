#!/usr/bin/env python3
"""v1.9.103 desktop consistency: page edits made at deploy time, like bump_assets.py,
because the data bot rewrites the country pages. Idempotent: a page already done is left alone.

  1. Freshness key wording, one site-wide: "Up to date" / "Awaiting update".
  2. Signed-in header button: initial + "Account" (email moves to the tooltip).
  3. Compare: drop its narrower 1080px container. Chartmaker: drop its 1520px container.

Run from the repo root:  python3 tools/migrate_v19103.py
Exits 1 if a page still carries an old pattern afterwards."""
import glob, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GENERATED = {"methodology-by-economy.html", "gdp-by-country.html", "inflation-by-country.html",
             "unemployment-by-country.html", "data-status.html"}

OLD_AUTH = '''      authBtn.textContent = session.user.email;
      authBtn.classList.add("signed-in");
    } else {
      authBtn.textContent = "Sign Up";
      authBtn.classList.remove("signed-in");'''
NEW_AUTH = '''      var em = session.user.email || "";
      var ini = (em.charAt(0) || "?").toUpperCase().replace(/[^A-Z0-9]/, "?");
      authBtn.innerHTML = '<span class="acct-i" aria-hidden="true">' + ini + '</span>Account';
      authBtn.title = "Signed in as " + em;
      authBtn.setAttribute("aria-label", "Account, signed in as " + em);
      authBtn.classList.add("signed-in");
    } else {
      authBtn.textContent = "Sign Up";
      authBtn.removeAttribute("title");
      authBtn.removeAttribute("aria-label");
      authBtn.classList.remove("signed-in");'''

PAGE_SUBS = [
    ('</span>&nbsp;matches latest release</span>', '</span>&nbsp;Up to date</span>'),
    ('</span>&nbsp;not refreshed recently</span>', '</span>&nbsp;Awaiting update</span>'),
    ('</span>Latest version of the data is live</span>', '</span>Up to date</span>'),
    ('</span>Data may be outdated, awaiting next update</span>', '</span>Awaiting update</span>'),
    (OLD_AUTH, NEW_AUTH),
]
FILE_SUBS = {
    "compare.html": [('<div class="wrap" style="max-width:1080px; padding:30px 24px 60px;">',
                      '<div class="wrap" style="padding:30px 24px 60px;">')],
    "chartmaker.html": [('.cm-wrap{max-width:1520px;}\n', '')],
}
GEN_SUBS = [
    ("'Matches the latest release</span><span><span class=\"led orange\" aria-hidden=\"true\"></span>'\n"
     "              'Not refreshed recently, awaiting the next release</span></p>')",
     "'Up to date</span><span><span class=\"led orange\" aria-hidden=\"true\"></span>'\n"
     "              'Awaiting update</span></p>')"),
    (OLD_AUTH, NEW_AUTH),
]

def apply(path, subs):
    s = open(path, encoding="utf-8").read(); new = s; n = 0
    for a, b in subs:
        c = new.count(a)
        if c: new = new.replace(a, b); n += c
    if new != s:
        open(path, "w", encoding="utf-8").write(new)
    return n, new

def main():
    pages = changed = 0; leftovers = []
    for f in sorted(glob.glob(os.path.join(ROOT, "*.html"))):
        name = os.path.basename(f)
        if name in GENERATED: continue
        n, s = apply(f, PAGE_SUBS + FILE_SUBS.get(name, []))
        if n: pages += 1; changed += n
        for a, _ in PAGE_SUBS + FILE_SUBS.get(name, []):
            if a in s: leftovers.append(name)
    g = os.path.join(ROOT, "generate_indicator_pages.py")
    gn, gs = apply(g, GEN_SUBS)
    for a, _ in GEN_SUBS:
        if a in gs: leftovers.append("generate_indicator_pages.py")
    print(f"migrate_v19103: {pages} page(s) changed, {changed} edit(s); generator {gn} edit(s)")
    if leftovers:
        print("migrate_v19103: FAIL old patterns remain in: " + ", ".join(sorted(set(leftovers)))); return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
