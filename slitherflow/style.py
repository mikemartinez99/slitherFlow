"""Colours, layout constants and the text-width estimate shared by the renderer and overlap check."""
import sys

# Named line palettes, each in the order lines are given colours. A spec picks one with `palette: <name>` (or gives
# its own list of colours); okabe-ito is the default.
PALETTES = {
    # Okabe & Ito (2008): colour-blind safe
    "okabe-ito": ["#009E73", "#E69F00", "#CC79A7", "#D55E00", "#56B4E9", "#0072B2", "#F0E442", "#000000"],
    # Paul Tol's qualitative schemes: colour-blind safe
    "tol-bright": ["#4477AA", "#EE6677", "#228833", "#CCBB44", "#66CCEE", "#AA3377", "#BBBBBB"],
    "tol-vibrant": ["#0077BB", "#EE7733", "#009988", "#CC3311", "#33BBEE", "#EE3377", "#BBBBBB"],
    "tol-muted": ["#332288", "#88CCEE", "#44AA99", "#117733", "#999933", "#DDCC77", "#CC6677", "#882255", "#AA4499"],
    # IBM Design Library: colour-blind safe, five colours
    "ibm": ["#648FFF", "#DC267F", "#FE6100", "#785EF0", "#FFB000"],
    # matplotlib's default cycle (tab10): familiar, but not colour-blind safe
    "tab10": ["#1F77B4", "#FF7F0E", "#2CA02C", "#D62728", "#9467BD", "#8C564B", "#E377C2", "#7F7F7F", "#BCBD22",
              "#17BECF"],
}
DEFAULT_PALETTE = "okabe-ito"
PALETTE = PALETTES[DEFAULT_PALETTE]


def palette_colours(choice):
    """The colours for a spec's `palette:` value: a palette name, a list of colours, or None for the default."""
    if choice is None:
        return PALETTE
    if isinstance(choice, str):
        if choice.lower() in PALETTES:
            return PALETTES[choice.lower()]
        sys.exit(f"palette '{choice}' is not one of: {', '.join(PALETTES)} (or give a list of colours)")
    if isinstance(choice, list) and choice and all(isinstance(c, str) and c.strip() for c in choice):
        return [c.strip() for c in choice]
    sys.exit('palette must be a palette name or a non-empty list of colours, e.g. ["#4477AA", "#EE6677"]')

STYLE = {
    "font": "'Helvetica Neue', Helvetica, Arial, sans-serif",
    "ink": "#1f2328", "muted": "#59636e", "faint": "#8c959f", "rule": "#d0d7de",
    "line_width": 7,        # width of every line
    "gap": 10,              # spacing between parallel lines on the trunk
    "spacing": 170,         # distance between trunk stations
    "branch_spacing": 140,  # distance between stations on a branch
    "row_height": 130,      # vertical distance per row (row 1 = one row below the trunk)
    "corner": 22,           # corner radius of 90-degree bends
    "dash": "16 9",         # optional lines
    "margin": 48,
    "station_radius": 11,
}

LABEL_OFFSET = 34            # station centre -> station name baseline
TOOL_OFFSET = 17             # station name -> tool line
ICON_W, ICON_H = 46, 58
FEED_LANE = 90               # shortest straight run of a `feeds:` connector between its two bends


def text_width(s, size, bold=False):
    """Rough rendered width of Helvetica text (good enough for layout and overlap checks)."""
    return len(s) * size * (0.58 if bold else 0.53)   # calibrated on rsvg-convert renders
