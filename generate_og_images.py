#!/usr/bin/env python3
"""
generate_og_images.py

Generates 1200x630 PNG social-share cards for every indicator page,
matching The Economic Atlas's real visual identity: the site's actual
logo mark, the real Nunito Sans font (the same fallback the site's own
CSS font stack uses), and no chart -- one big number, always in US$ for
currency metrics.

Uses PIL directly (not matplotlib) for pixel-precise logo placement and
because it needs no font-cache registration step -- just point it at a
.ttf and draw. Font files live in /fonts (Nunito Sans Regular/Bold/
ExtraBold, converted from the real @fontsource/nunito-sans woff2 files
since matplotlib/PIL both need ttf/otf, not woff2). Logo comes from the
site's own /logo.png.

Output: /og/{country-slug}-{metric-slug}.png

These are static, baked at generation time -- correct for the data
available at the moment this script runs. Run alongside
generate_indicator_pages.py after the hourly data refresh.
"""
import json, os
from PIL import Image, ImageDraw, ImageFont

from generate_indicator_pages import (
    COUNTRIES, CORE_METRICS, load_json, fmt_value, ROOT,
    annualize_gdp_points, fmt_period_label,
)

NAVY = (30, 69, 102)      # --navy
BLUE = (71, 150, 206)     # --blue
PAPER = (245, 246, 243)   # --paper
INK = (23, 27, 30)        # --ink
INK2 = (90, 97, 103)      # --ink2

W, H = 1200, 630
SCALE = 2  # render at 2x, downsample for crisp anti-aliased text/logo

FONT_DIR = os.path.join(ROOT, "fonts")
LOGO_PATH = os.path.join(ROOT, "logo.png")

def font(weight, size):
    path = {
        "regular": os.path.join(FONT_DIR, "NunitoSans-Regular.ttf"),
        "bold": os.path.join(FONT_DIR, "NunitoSans-Bold.ttf"),
        "extrabold": os.path.join(FONT_DIR, "NunitoSans-ExtraBold.ttf"),
    }[weight]
    return ImageFont.truetype(path, size)

def value_fontsize(s):
    n = len(s)
    if n <= 8:
        return 108
    if n <= 11:
        return 88
    if n <= 15:
        return 68
    return 54

def to_usd(value, unit, fx):
    if not unit or "%" in unit or unit == "index":
        return value, True
    if fx is None:
        return value, True
    rate, direction = fx.get("rate"), fx.get("direction")
    if rate is None or direction is None:
        return value, False
    if direction == "multiply":
        return value * rate, True
    if direction == "divide":
        return value / rate, True
    return value, False

def usd_unit(unit):
    if not unit or "%" in unit or unit == "index":
        return unit
    for suf in ("bn", "m", "k"):
        if unit.endswith(suf) and len(unit) > len(suf):
            return "$" + suf
    return "$"

def make_card(country_name, metric_title, latest_str, latest_period_label, out_path):
    img = Image.new("RGB", (W * SCALE, H * SCALE), PAPER)
    draw = ImageDraw.Draw(img)
    cx = (W * SCALE) // 2

    # --- Brand lockup: logo mark + "The Economic Atlas" wordmark, centred ---
    logo = Image.open(LOGO_PATH).convert("RGBA")
    logo_h = 46 * SCALE
    logo_w = int(logo.width * (logo_h / logo.height))
    logo_resized = logo.resize((logo_w, logo_h), Image.LANCZOS)

    f_the = font("regular", 24 * SCALE)
    f_atlas = font("extrabold", 24 * SCALE)
    the_w = draw.textlength("The ", font=f_the)
    atlas_w = draw.textlength("Economic Atlas", font=f_atlas)
    divider_gap = 16 * SCALE
    text_block_w = the_w + atlas_w
    total_w = int(logo_w + divider_gap + text_block_w)
    start_x = int(cx - total_w // 2)
    brand_y = 74 * SCALE

    img.paste(logo_resized, (start_x, brand_y - logo_h // 2), logo_resized)
    divider_x = start_x + logo_w + divider_gap // 2
    draw.line([(divider_x, brand_y - 22 * SCALE), (divider_x, brand_y + 22 * SCALE)], fill=NAVY, width=max(1, SCALE))
    text_x = start_x + logo_w + divider_gap
    draw.text((text_x, brand_y), "The ", font=f_the, fill=NAVY, anchor="lm")
    draw.text((text_x + the_w, brand_y), "Economic Atlas", font=f_atlas, fill=NAVY, anchor="lm")

    # --- Country + metric line ---
    f_sub = font("bold", 30 * SCALE)
    draw.text((cx, 200 * SCALE), f"{country_name} \u00b7 {metric_title}", font=f_sub, fill=INK, anchor="mm")

    # --- Big value ---
    f_val = font("extrabold", value_fontsize(latest_str) * SCALE)
    draw.text((cx, 330 * SCALE), latest_str, font=f_val, fill=NAVY, anchor="mm")

    # --- Footer ---
    f_foot = font("regular", 18 * SCALE)
    draw.text((cx, 470 * SCALE), f"as of {latest_period_label}  \u00b7  live, hourly-refreshed data", font=f_foot, fill=INK2, anchor="mm")

    img = img.resize((W, H), Image.LANCZOS)
    img.save(out_path)

def main():
    sources = load_json("data-metric-sources.json")
    out_dir = os.path.join(ROOT, "og")
    os.makedirs(out_dir, exist_ok=True)
    made = 0
    fx_missing = []

    for country_name, (iso2, slug, alpha2) in COUNTRIES.items():
        data_file = "data.json" if iso2 == "uk" else f"data-{iso2}.json"
        data_path = os.path.join(ROOT, data_file)
        if not os.path.exists(data_path):
            continue
        data = load_json(data_file)
        series = data.get("series", {})
        country_sources = sources.get(country_name, {})
        fx = data.get("fx_to_usd")

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

            usd_val, ok = to_usd(latest_val, unit, fx)
            if not ok:
                fx_missing.append((country_name, metric_key))
                usd_val = latest_val
            latest_str = fmt_value(usd_val, usd_unit(unit))

            page_slug = f"{slug}-{metric_slug}"
            out_path = os.path.join(out_dir, f"{page_slug}.png")
            make_card(country_name, metric_title, latest_str, fmt_period_label(latest_period), out_path)
            made += 1

    print(f"Generated {made} OG images in /og/")
    if fx_missing:
        print(f"Warning: {len(fx_missing)} pairs had no usable FX rate, used raw local-currency value:")
        for c, m in fx_missing:
            print(f"  {c} / {m}")

if __name__ == "__main__":
    main()
