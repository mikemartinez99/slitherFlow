"""Draw the GitHub social preview card (1280x640), in the same layout as the Scoranet card.

    python3 logo/make_social_preview.py                        -> logo/social_preview.svg
    rsvg-convert logo/social_preview.svg -o logo/social_preview.png

Upload the PNG under the repository's Settings -> General -> Social preview.
"""
import base64
import math
import random
from pathlib import Path

HERE = Path(__file__).parent
W, H = 1280, 640
FONT = "'Helvetica Neue', Helvetica, Arial, sans-serif"
GREEN, ORANGE, PINK, SKY, BLUE = "#009E73", "#E69F00", "#CC79A7", "#56B4E9", "#0072B2"
TEXT, MUTED = "#ffffff", "#9fb0c3"

out = []
add = out.append
add(f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
    f'viewBox="0 0 {W} {H}" width="{W}" height="{H}">')
add('<defs><linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">'
    '<stop offset="0" stop-color="#1d3556"/><stop offset="1" stop-color="#0e1827"/></linearGradient></defs>')
add(f'<rect width="{W}" height="{H}" fill="url(#bg)"/>')


# ---- faint background: small subway-map fragments, each in a soft circle ----
def fragment(cx, cy, r, seed):
    rnd = random.Random(seed)
    add(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="#ffffff" fill-opacity="0.025"/>')
    add(f'<g transform="rotate({rnd.choice([-90, 0, 0, 90, 180])} {cx} {cy})">')
    colours = rnd.sample([GREEN, ORANGE, PINK, SKY], 2)
    s = r * 0.55
    for k, col in enumerate(colours):
        dy = (k - 0.5) * 12
        up = rnd.choice([-1, 1])
        x0, x1 = cx - s, cx - s * 0.15
        x2, x3 = x1 + s * 0.45, cx + s
        y0, y2 = cy + dy, cy + dy + up * s * 0.45
        d = f"M{x0:.0f},{y0:.0f} L{x1:.0f},{y0:.0f} L{x2:.0f},{y2:.0f} L{x3:.0f},{y2:.0f}"
        add(f'<path d="{d}" fill="none" stroke="{col}" stroke-width="5" stroke-linecap="round" '
            f'stroke-linejoin="round" stroke-opacity="0.24"/>')
        for x, y in [(x0 + s * 0.3, y0), (x2 + s * 0.15, y2), (x3, y2)]:
            add(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="5" fill="#0e1827" stroke="#ffffff" stroke-width="2" '
                f'stroke-opacity="0.3" fill-opacity="0.6"/>')
    add('</g>')


for i, (cx, cy, r) in enumerate([(300, 40, 85), (690, 95, 85), (1020, 70, 80), (1250, 230, 80), (1190, 400, 70),
                                  (240, 595, 85), (640, 600, 80), (900, 590, 80), (1200, 560, 85), (-10, 330, 80)]):
    fragment(cx, cy, r, seed=i)

# ---- the hex logo on the left ----
logo = base64.b64encode((HERE / "slitherflow_hex.png").read_bytes()).decode()
lh = 440
lw = lh * 1560 / 1800
add(f'<image x="{255 - lw / 2:.1f}" y="{320 - lh / 2:.1f}" width="{lw:.1f}" height="{lh}" '
    f'xlink:href="data:image/png;base64,{logo}"/>')

# ---- title ----
X = 470
for y, line in [(238, "Subway maps for"), (298, "Snakemake pipelines")]:
    add(f'<text x="{X}" y="{y}" font-family="{FONT}" font-size="50" font-weight="700" fill="{TEXT}" '
        f'letter-spacing="-0.5">{line}</text>')

# ---- pipeline pills ----
def text_w(s, size):
    return len(s) * size * 0.56


x, y, ph, size = X, 360, 40, 16
steps = [("Rule graph", ORANGE), ("Draft YAML", SKY), ("Edit", GREEN), ("SVG · PNG · PDF", PINK)]
for i, (label, col) in enumerate(steps):
    w = text_w(label, size) + 30
    add(f'<rect x="{x}" y="{y}" width="{w:.0f}" height="{ph}" rx="{ph / 2}" fill="{col}" fill-opacity="0.18" '
        f'stroke="{col}" stroke-width="2"/>')
    add(f'<text x="{x + w / 2:.0f}" y="{y + ph / 2 + size * 0.36:.0f}" font-family="{FONT}" font-size="{size}" '
        f'font-weight="500" fill="{TEXT}" text-anchor="middle">{label}</text>')
    x += w
    if i < len(steps) - 1:
        add(f'<path d="M{x + 8},{y + ph / 2} H{x + 22}" stroke="{MUTED}" stroke-width="2"/>')
        add(f'<path d="M{x + 17},{y + ph / 2 - 4} L{x + 23},{y + ph / 2} L{x + 17},{y + ph / 2 + 4}" fill="none" '
            f'stroke="{MUTED}" stroke-width="2" stroke-linejoin="round"/>')
        x += 30

# ---- repo URL ----
add(f'<text x="{X}" y="448" font-family="{FONT}" font-size="18" fill="{MUTED}" letter-spacing="0.3">'
    f'github.com/mikemartinez99/slitherFlow</text>')

add('</svg>')
(HERE / "social_preview.svg").write_text("\n".join(out), encoding="utf-8")
print(f"wrote {HERE / 'social_preview.svg'}")
