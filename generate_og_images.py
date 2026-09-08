#!/usr/bin/env python3
"""
generate_og_images.py

Generates 1200x630 PNG social-share cards for every indicator page,
matching The Economic Atlas's visual style. Run AFTER
generate_indicator_pages.py (reuses the same country/metric config).

Output: /og/{country-slug}-{metric-slug}.png

These are static, baked at generation time -- correct for the data
available at the moment this script runs. Re-run alongside the hourly
data refresh (or daily is plenty for OG cards; they don't need to be
hourly-fresh the way the live pages are) to keep them current.
"""
import json, os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image

from generate_indicator_pages import COUNTRIES, CORE_METRICS, load_json, fmt_value, flag_emoji, ROOT, annualize_gdp_points

NAVY = "#1E4566"
BLUE = "#4796CE"
PAPER = "#F5F6F3"
INK = "#171B1E"
SCALE = 2  # render at 2x then downsample for crisp anti-aliased text/lines

def value_fontsize(s):
    # Longer formatted values (currency symbol + digits + suffix) need to
    # shrink to stay on one line within the card's left column.
    n = len(s)
    if n <= 7:
        return 44
    if n <= 11:
        return 36
    if n <= 15:
        return 28
    return 22

def make_card(country_name, metric_title, latest_str, latest_period, pts, out_path):
    fig = plt.figure(figsize=(12, 6.3), dpi=100 * SCALE)
    fig.patch.set_facecolor(PAPER)
    ax_text = fig.add_axes([0.06, 0.08, 0.5, 0.84])
    ax_text.axis("off")
    ax_chart = fig.add_axes([0.60, 0.15, 0.35, 0.55])

    ax_text.text(0, 0.92, "THE ECONOMIC ATLAS", fontsize=13, color=BLUE, fontweight="bold", family="sans-serif", transform=ax_text.transAxes)
    ax_text.text(0, 0.72, f"{country_name}", fontsize=30, color=INK, fontweight="bold", family="sans-serif", transform=ax_text.transAxes)
    ax_text.text(0, 0.58, f"{metric_title}", fontsize=20, color=INK, alpha=0.75, family="sans-serif", transform=ax_text.transAxes)
    ax_text.text(0, 0.32, f"{latest_str}", fontsize=value_fontsize(latest_str), color=NAVY, fontweight="bold", family="sans-serif", transform=ax_text.transAxes)
    ax_text.text(0, 0.16, f"as of {latest_period}  ·  live, hourly-refreshed data", fontsize=12, color=INK, alpha=0.55, family="sans-serif", transform=ax_text.transAxes)

    if len(pts) >= 2:
        xs = list(range(len(pts)))
        ys = [p[1] for p in pts]
        ax_chart.plot(xs, ys, color=BLUE, linewidth=2.5)
        ax_chart.fill_between(xs, ys, min(ys), color=BLUE, alpha=0.08)
        ax_chart.scatter([xs[-1]], [ys[-1]], color=NAVY, s=40, zorder=5)
    ax_chart.set_facecolor("none")
    for spine in ax_chart.spines.values():
        spine.set_visible(False)
    ax_chart.set_xticks([])
    ax_chart.set_yticks([])

    tmp_path = out_path + ".tmp.png"
    fig.savefig(tmp_path, facecolor=PAPER, bbox_inches=None)
    plt.close(fig)
    with Image.open(tmp_path) as im:
        im = im.resize((1200, 630), Image.LANCZOS)
        im.save(out_path)
    os.remove(tmp_path)

def main():
    sources = load_json("data-metric-sources.json")
    out_dir = os.path.join(ROOT, "og")
    os.makedirs(out_dir, exist_ok=True)
    made = 0

    for country_name, (iso2, slug, alpha2) in COUNTRIES.items():
        data_file = "data.json" if iso2 == "uk" else f"data-{iso2}.json"
        data_path = os.path.join(ROOT, data_file)
        if not os.path.exists(data_path):
            continue
        data = load_json(data_file)
        series = data.get("series", {})
        country_sources = sources.get(country_name, {})

        for metric_key, (metric_slug, metric_title) in CORE_METRICS.items():
            if metric_key not in series or metric_key not in country_sources:
                continue
            s = series[metric_key]
            pts = [p for p in s.get("points", []) if p[1] is not None]
            if metric_key == "gdp_level":
                pts = annualize_gdp_points(pts, s.get("freq", ""), country_name)
            if len(pts) < 2:
                continue
            unit = s.get("unit", "")
            latest_period, latest_val = pts[-1]
            latest_str = fmt_value(latest_val, unit)
            page_slug = f"{slug}-{metric_slug}"
            out_path = os.path.join(out_dir, f"{page_slug}.png")
            make_card(country_name, metric_title, latest_str, latest_period, pts[-40:], out_path)
            made += 1

    print(f"Generated {made} OG images in /og/")

if __name__ == "__main__":
    main()
