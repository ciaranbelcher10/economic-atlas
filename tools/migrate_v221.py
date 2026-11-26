#!/usr/bin/env python3
"""v2.0.21: a mouse wheel scrolls the page; it no longer zooms maps and charts.

With a mouse, the wheel over a map or chart zoomed it and the page stopped scrolling, so getting past a
map was hard. Now (the convention Google Maps uses):
  * maps (homepage, every country page's mini-map, Compare, Dashboard): a plain wheel scrolls the page
    and shows "Ctrl + scroll to zoom the map" (the Command key on a Mac) for a moment; Ctrl or Command +
    wheel zooms. A trackpad pinch arrives as Ctrl + wheel, so pinch still zooms. Touch is unchanged.
  * charts (country pages, Dashboard): zoom.wheel.modifierKey "ctrl". Drag-to-zoom and pinch unchanged.
  * the map hint "Scroll or pinch to zoom" becomes "Ctrl + scroll or pinch to zoom" ("Pinch to zoom" on
    touch screens, "⌘ + scroll..." on a Mac).
Idempotent. python3 tools/migrate_v221.py [--check]
"""
import glob, os, re, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MARK = "/* v2.0.21 wheel */"
HELPER = """<script>
""" + MARK + """
/* A plain mouse wheel scrolls the page. Ctrl or Command + wheel zooms the map (a trackpad pinch arrives as
   Ctrl + wheel). d3's own default filter is kept for everything else. */
function eaWheelFilter(e){
  if(e.type === "wheel" && !e.ctrlKey && !e.metaKey){ eaWheelNudge(this); return false; }
  return (!e.ctrlKey || e.type === "wheel") && !e.button;
}
var eaWheelTimer = null;
function eaWheelNudge(svg){
  var box = svg && svg.parentNode;
  if(!box) return;
  var h = box.querySelector(".ea-wheelhint");
  if(!h){
    h = document.createElement("div");
    h.className = "ea-wheelhint";
    h.setAttribute("aria-hidden", "true");
    h.textContent = (/Mac|iPhone|iPad/.test(navigator.platform) ? "\\u2318" : "Ctrl") + " + scroll to zoom the map";
    h.style.cssText = "position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);background:rgba(20,33,52,.85);"
      + "color:#fff;font-size:13px;line-height:1.3;padding:8px 14px;border-radius:8px;pointer-events:none;"
      + "white-space:nowrap;opacity:0;transition:opacity .2s;z-index:6;";
    if(getComputedStyle(box).position === "static") box.style.position = "relative";
    box.appendChild(h);
  }
  h.style.opacity = "1";
  clearTimeout(eaWheelTimer);
  eaWheelTimer = setTimeout(function(){ h.style.opacity = "0"; }, 1400);
}
(function(){
  function label(){
    var t = matchMedia("(hover: none)").matches ? "Pinch to zoom"
          : (/Mac/.test(navigator.platform) ? "\\u2318" : "Ctrl") + " + scroll or pinch to zoom";
    document.querySelectorAll(".zoomhint").forEach(function(el){ el.textContent = t; });
  }
  if(document.readyState === "loading") document.addEventListener("DOMContentLoaded", label); else label();
})();
</script>
"""

ZOOM = re.compile(r"d3\.zoom\(\)(?!\.filter\(eaWheelFilter\))")
WHEEL = re.compile(r"wheel:(\s?)\{(\s?)enabled:(\s?)true(\s?)\}")


def migrate(t):
    n = {}
    if "d3.zoom()" in t:
        t, n["maps"] = ZOOM.subn("d3.zoom().filter(eaWheelFilter)", t)
        if MARK not in t:
            # before the first script that builds a zoom, so the helper exists when the map is drawn
            i = t.index("d3.zoom()")
            # the last real <script> tag before it (at the start of a line, not "<script>" in a JS comment)
            j = [m.start() + 1 for m in re.finditer(r"\n<script(?:\s[^>]*)?>", t[:i])][-1]
            t = t[:j] + HELPER + t[j:]
            n["helper"] = 1
    t, n["charts"] = WHEEL.subn(lambda m: f'wheel:{m.group(1)}{{{m.group(2)}enabled:{m.group(3)}true, modifierKey:"ctrl"{m.group(4)}}}', t)
    t, n["hint"] = re.subn(r'(<span class="zoomhint">)Scroll or pinch to zoom(</span>)', r"\1Ctrl + scroll or pinch to zoom\2", t)
    return t, {k: v for k, v in n.items() if v}


def main():
    check = "--check" in sys.argv
    files = sorted(glob.glob(os.path.join(ROOT, "*.html")))
    total = {}
    for p in files:
        t = open(p, encoding="utf-8").read()
        new, n = migrate(t)
        if new != t:
            for k, v in n.items():
                total[k] = total.get(k, 0) + v
            total["files"] = total.get("files", 0) + 1
            if not check:
                open(p, "w", encoding="utf-8").write(new)
    print(("would change " if check else "changed ") + ", ".join(f"{k} {v}" for k, v in sorted(total.items())) if total else "nothing to do")


if __name__ == "__main__":
    main()
