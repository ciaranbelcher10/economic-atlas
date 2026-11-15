#!/usr/bin/env python3
"""v1.9.136 text review pass 2: the (i) text, chart text and source lines on every country page.

Rules (claude/v1.9.135-text-review.md, plus Ciaran's 15 Nov notes on Turkey):
  - A tile's source line is the publisher and series code only. Tiles render it through eaShortSrc(), so
    every tile is the same height whatever its source string says; the (i) and the chart keep the full line.
  - A source line is one sentence: the publisher, the series, its basis. Explanations of why that source was
    chosen, fallbacks and reassurance ("not a sign the feed has broken") go.
  - A definition keeps its first sentence. Later sentences stay only if they stop a misreading; sentences that
    defend the site, explain its choices, speak as "we", reassure, or narrate the data go.
  - Toggle notes use the toggles' real names (Adjust for inflation, Convert to USD$).

Idempotent: run twice, expect "N changed" then "0 changed".
"""
import glob, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from secnotes_v19136 import rewrite as rewrite_note

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")

# Sentences that fail "does the user need this": process, defence, reassurance, "we", narration.
DROP = re.compile("|".join([
    r"not a data error", r"not a sign", r"which is why", r"gap is expected", r"does not publish", r"do not publish",
    r"\bdeliberately\b", r"(?<![A-Za-z])[Ww]e(?![A-Za-z'’])", r"\b[Oo]ur\b", r"[Tt]his site\b",
    r"\bthe Atlas\b", r"neither an EU nor", r"reflect real conditions", r"used on most other pages",
    r"used for European pages", r"rather than guess", r"is not hidden", r"\bon a given run\b", r"\bthis run\b",
    r"\b[Ff]etch(?:ed|es)?\b", r"\bpipeline\b", r"\bwired\b", r"\b[Ff]alls? back\b", r"\b[Ff]allback\b",
    r"\bexceptionally volatile\b", r"\b[Nn]ot a data error\b", r"\b[Tt]he Atlas\b", r"\bfor exactly this reason\b", r"\b[Oo]n the roadmap\b", r"\bknown gap\b", r"\bnot yet\b",
]))

ABBR = r"(?<!\bSt)(?<!\be\.g)(?<!\bi\.e)(?<!\bU\.S)(?<!\bNo)(?<!\bvs)(?<!\bapprox)(?<!\bincl)(?<!\bJan)(?<!\bFeb)(?<!\bMar)(?<!\bApr)(?<!\bJun)(?<!\bJul)(?<!\bAug)(?<!\bSep)(?<!\bSept)(?<!\bOct)(?<!\bNov)(?<!\bDec)"
SPLIT = re.compile(ABBR + r"(?<=[.!?])\s+(?=[A-Z0-9“(\\])")


def sentences(t):
    return [x for x in SPLIT.split(t) if x.strip()]


def rename(t):
    t = re.sub(r"Dollari[sz]ed", "converted to US$", t)
    t = re.sub(r"Dollari[sz]ing", "converting to US$", t)
    t = re.sub(r"Dollari[sz]e", "Convert to USD$", t)
    t = t.replace("Make it real", "Adjust for inflation").replace("Make It Real", "Adjust for inflation")
    return t


def clean_text(t, keep_first=True):
    """Definitions, chart descriptions, toggle notes and section notes."""
    t = rename(t)
    ss = sentences(t)
    if not ss:
        return t
    out = [ss[0]] if keep_first else ([] if DROP.search(ss[0]) else [ss[0]])
    out += [s for s in ss[1:] if not DROP.search(s)]
    return " ".join(out).strip()


def clean_source(t):
    """A source line: publisher, series and basis. Fallback parentheticals and sentences that explain the site's
    choices go; a caveat that stops a misreading stays."""
    t = rename(t)
    t = re.sub(r"\s*\((?:falls back|fall back|see |only if|until )[^()]*\)", "", t)
    ss = sentences(t)
    if not ss:
        return t.strip()
    return " ".join([ss[0]] + [x for x in ss[1:] if not DROP.search(x)]).strip()


STR = r'"((?:[^"\\\n]|\\.)*)"'
SHORT_FN = r'''/* v1.9.136: a tile shows its source as publisher and series code only; the (i) keeps the full line */
function eaShortSrc(s){
  s = String(s == null ? "" : s).replace(/\s*\([^()]*\b(?:falls? back|only if|see )[^()]*\)/gi, "");
  s = s.split(/(?<=[.;])\s+(?=[A-Z(])/)[0].replace(/[.;]\s*$/, "");
  var parts = s.split(/\s*·\s*/);
  var code = /[A-Z0-9][A-Z0-9_.\-\/]{3,}/;
  var out = parts[0];
  if(parts.length > 1 && parts[0].length <= 30 && (parts[1].length <= 30 || (parts[1].length <= 40 && !/\b[a-z]{2,}\s+[a-z]{2,}/.test(parts[1]) && (/^[A-Z0-9]/.test(parts[1]) || /[_\d]/.test(parts[1]))))) out += " · " + parts[1];
  if(out.length > 70){ var c = out.match(/^(.*?\b[A-Z0-9][A-Z0-9_.\-\/]{3,}\b\)?)/); if(c && c[1].length >= 8) out = c[1]; }
  return out;
}
'''


def fix(s, page=""):
    n0 = s
    # INFO_CONTENT entries
    i = s.find("const INFO_CONTENT = {")
    if i != -1:
        j = s.find("\n};", i)
        block = s[i:j]
        def ent(m):
            k, v = m.group(1), m.group(2)
            if k == "source":
                nv = clean_source(v)
            elif k in ("real", "dollar", "capita"):
                ss = sentences(clean_text(v))
                nv = " ".join(ss[:2])
            else:
                nv = clean_text(v)
            return f'{k}: "{nv}"'
        block = re.sub(r'\b(description|source|real|dollar|capita|note): ' + STR, ent, block)
        s = s[:i] + block + s[j:]
    # SRC_* constants
    s = re.sub(r'(const SRC_\w+\s*=\s*)' + STR, lambda m: m.group(1) + '"' + clean_source(m.group(2)) + '"', s)
    # chart descriptions (chartPanel second string argument) and series bases
    s = re.sub(r'(chartPanel\([^,\n]+,\s*"charts-[a-z]+",\s*' + STR + r',\s*\n?\s*)' + STR,
               lambda m: m.group(1) + '"' + clean_text(m.group(3)) + '"', s)
    s = re.sub(r'(\bexpl:\s*)' + STR, lambda m: m.group(1) + '"' + clean_text(m.group(2)) + '"', s)
    s = re.sub(r'(\bsrcNote:\s*)' + STR, lambda m: m.group(1) + '"' + clean_source(m.group(2)) + '"', s)
    # section notes
    def sec(m):
        body = re.sub(r"\s+", " ", m.group(2)).strip()
        nb = rewrite_note(page, body)
        nb = clean_text(nb, keep_first=False) if nb else ""
        nb = rewrite_note(page, nb) if nb else ""
        return "" if not nb else m.group(1) + nb + "</p>"
    s = re.sub(r'(<p class="secnote">)([^<]*)</p>', sec, s)
    s = re.sub(r'\n[ \t]*\n(?=[ \t]*</section>)', "\n", s)
    # tiles show the short source
    if "function eaShortSrc(" not in s and "function statTile(" in s:
        s = s.replace("function statTile(", SHORT_FN + "function statTile(", 1)
    s = s.replace('<p class="source">${opts.source}</p>', '<p class="source">${eaShortSrc(opts.source)}</p>')
    return s


def main():
    changed = checked = 0
    for f in sorted(glob.glob(os.path.join(ROOT, "*.html"))):
        s0 = open(f, encoding="utf-8").read()
        if 'id="tiles-misc"' not in s0:
            continue
        s = fix(s0, os.path.basename(f)[:-5])
        checked += 1
        if s != s0:
            open(f, "w", encoding="utf-8").write(s)
            changed += 1
    print(f"{checked} page(s) checked, {changed} changed")


if __name__ == "__main__":
    main()
