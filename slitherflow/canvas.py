"""SVG drawing primitives. The canvas also records what it drew where, for the overlap check."""
import math
from xml.sax.saxutils import escape

from .style import ICON_H, ICON_W, text_width


class Canvas:
    """Collects SVG elements and remembers what was drawn where, for extents and overlap checks."""

    def __init__(self, style):
        self.s = style
        self.out = []
        self.texts, self.icons, self.lines, self.stations = [], [], [], []
        self.terminus = None      # desc of the terminus pill, if the map has one
        self.xmin = self.ymin = math.inf
        self.xmax = self.ymax = -math.inf

    def _extend(self, x0, y0, x1, y1):
        self.xmin, self.ymin = min(self.xmin, x0), min(self.ymin, y0)
        self.xmax, self.ymax = max(self.xmax, x1), max(self.ymax, y1)

    def text(self, x, y, s, size=15, bold=False, fill=None, anchor="middle", desc=None, track=True):
        if s is None or s == "":
            return
        s = str(s)
        w = text_width(s, size, bold)
        x0 = {"middle": x - w / 2, "start": x, "end": x - w}[anchor]
        box = (x0, y - size * 0.78, x0 + w, y + size * 0.22)
        if track:
            self.texts.append((box, desc or s))
            self._extend(*box)
        self.out.append(f'<text x="{x:.1f}" y="{y:.1f}" font-family="{self.s["font"]}" font-size="{size}" '
                        f'font-weight="{"700" if bold else "400"}" fill="{fill or self.s["ink"]}" '
                        f'text-anchor="{anchor}">{escape(s)}</text>')

    def polyline(self, pts, color, desc, dashed=False, casing=False, radius=None, casing_skip=0, casing_pts=None):
        r = self.s["corner"] if radius is None else radius
        d = rounded_path(pts, r)
        lw = self.s["line_width"]
        cpts = casing_pts if casing_pts is not None else pts[casing_skip:]
        if casing and len(cpts) >= 2:  # white halo so crossings read as a bridge
            self.out.append(f'<path d="{rounded_path(cpts, r)}" fill="none" stroke="#ffffff" stroke-width="{lw + 8}" '
                            f'stroke-linecap="round" stroke-linejoin="round"/>')
        da = f' stroke-dasharray="{self.s["dash"]}"' if dashed else ""
        self.out.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{lw}" '
                        f'stroke-linecap="round" stroke-linejoin="round"{da}/>')
        self.lines.append((pts, desc))
        for x, y in pts:
            self._extend(x - lw, y - lw, x + lw, y + lw)

    def station(self, x, y, members, optional=False, desc=""):
        r = self.s["station_radius"]
        da = ' stroke-dasharray="4 3"' if optional else ""
        self.out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="#ffffff" stroke="{self.s["ink"]}" '
                        f'stroke-width="3.2"{da}/>')
        self.stations.append(((x - r, y - r, x + r, y + r), set(members), desc))

    def pill(self, x, y1, y2, members, w=26, desc=""):
        self.out.append(f'<rect x="{x - w / 2:.1f}" y="{y1 - w / 2:.1f}" width="{w}" height="{y2 - y1 + w:.1f}" '
                        f'rx="{w / 2}" fill="#ffffff" stroke="{self.s["ink"]}" stroke-width="3.2"/>')
        self.stations.append(((x - w / 2, y1 - w / 2, x + w / 2, y2 + w / 2), set(members), desc))
        self._extend(x - w / 2, y1 - w / 2, x + w / 2, y2 + w / 2)

    def file_icon(self, cx, cy, tag, color, desc):
        w, h, f = ICON_W, ICON_H, 13
        x, y = cx - w / 2, cy - h / 2
        ink = self.s["ink"]
        self.out.append(f'<path d="M{x:.1f},{y:.1f} H{x + w - f:.1f} L{x + w:.1f},{y + f:.1f} V{y + h:.1f} H{x:.1f} Z" '
                        f'fill="#ffffff" stroke="{ink}" stroke-width="2.2" stroke-linejoin="round"/>')
        self.out.append(f'<path d="M{x + w - f:.1f},{y:.1f} V{y + f:.1f} H{x + w:.1f}" fill="none" stroke="{ink}" '
                        f'stroke-width="2.2" stroke-linejoin="round"/>')
        tag_w = max(w + 10, text_width(tag, 11, True) + 10)
        self.out.append(f'<rect x="{cx - tag_w / 2:.1f}" y="{cy - 2:.1f}" width="{tag_w:.1f}" height="18" rx="3" fill="{color}"/>')
        self.text(cx, cy + 12, tag, 11, True, "#ffffff", track=False)
        box = (cx - tag_w / 2, y, cx + tag_w / 2, y + h)
        self.icons.append((box, desc))
        self._extend(*box)

    def connector(self, x1, y1, x2, y2):
        self.out.append(f'<path d="M{x1:.1f},{y1:.1f} L{x2:.1f},{y2:.1f}" fill="none" stroke="{self.s["faint"]}" '
                        f'stroke-width="2" stroke-dasharray="2 4" stroke-linecap="round"/>')


def rounded_path(pts, r):
    """SVG path through pts with every corner rounded (radius r, limited by segment lengths)."""
    d = f"M{pts[0][0]:.1f},{pts[0][1]:.1f}"
    for i in range(1, len(pts) - 1):
        (x0, y0), (x1, y1), (x2, y2) = pts[i - 1], pts[i], pts[i + 1]
        l1, l2 = math.hypot(x1 - x0, y1 - y0), math.hypot(x2 - x1, y2 - y1)
        if l1 == 0 or l2 == 0:
            continue
        rr = min(r, l1 / 2, l2 / 2)
        ax, ay = x1 - (x1 - x0) / l1 * rr, y1 - (y1 - y0) / l1 * rr
        bx, by = x1 + (x2 - x1) / l2 * rr, y1 + (y2 - y1) / l2 * rr
        d += f" L{ax:.1f},{ay:.1f} Q{x1:.1f},{y1:.1f} {bx:.1f},{by:.1f}"
    d += f" L{pts[-1][0]:.1f},{pts[-1][1]:.1f}"
    return d


def trim_path(pts, a, b):
    """pts with length a cut off the start and length b off the end."""
    def cut(p, d):
        p = list(p)
        while len(p) > 1 and d > 0:
            (x0, y0), (x1, y1) = p[0], p[1]
            seg = math.hypot(x1 - x0, y1 - y0)
            if seg <= d:
                p.pop(0)
                d -= seg
            else:
                p[0] = (x0 + (x1 - x0) * d / seg, y0 + (y1 - y0) * d / seg)
                d = 0
        return p
    return cut(cut(pts, a)[::-1], b)[::-1]


def wrap_words(s, max_chars):
    words, lines, cur = str(s).split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > max_chars:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    return lines + ([cur] if cur else [])


def two_lines(label):
    """Split an output label over two lines at the space nearest the middle."""
    label = str(label)
    if "\n" in label:
        return label.split("\n")[:2]
    if len(label) <= 10 or " " not in label:
        return [label]
    mid = len(label) / 2
    cut = min((i for i, c in enumerate(label) if c == " "), key=lambda i: abs(i - mid))
    return [label[:cut], label[cut + 1:]]
