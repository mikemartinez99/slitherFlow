"""Lay out a spec and draw it as an SVG subway map.

`render(spec)` builds a `SubwayMap` and runs it in two halves. Each half is a short list of steps that run in
order, and each step uses what the steps before it worked out.

Layout (where everything goes):

    resolve_lines    fill in what the spec leaves out: names, colours, rows, which lines run along the trunk
    place_rows       the trunk's height on the page, and the y of each trunk line
    place_trunk      the x of each trunk station, and where the trunk splits into its lines
    place_lines      the x of every other station, and the start of each line's path
    place_terminus   where the end station goes, and the track each incoming line takes into it
    finish_paths     where each line ends: in the terminus, in a station on another line, or at its last station
    route_feeds      the `feeds:` connectors between stations on different lines

Drawing (back to front, so later things sit on top): title, lines, feeds, trunk stations, line stations,
terminus, input, output icons, legend.

Positions are written onto the spec's own station dicts as private keys (`_x`, `_y`, `_label_above`, ...), so the
spec passed in is changed. Lengths are SVG pixels, and y grows downwards: "above" means a smaller y.
"""
import math
import sys

from .canvas import Canvas, trim_path, two_lines, wrap_words
from .style import FEED_LANE, ICON_H, ICON_W, LABEL_OFFSET, STYLE, TOOL_OFFSET, palette_colours, text_width


def render(spec):
    """Draw a spec. Returns the SVG text and the Canvas, which records what was drawn where (for the overlap check)."""
    subway = SubwayMap(spec)
    subway.lay_out()
    return subway.draw(), subway.cv


# ---- small helpers -------------------------------------------------------------------------------------------------

def is_branch(ln):
    """A branch leaves a station on another line: `from: {line: <id>, station: <name>}`."""
    return isinstance(ln.get("from"), dict)


def tool_text(st):
    """The grey text under a station's name: its tool, plus "optional" for an optional step."""
    tool = st.get("tool", "") or ""
    if st.get("optional"):
        tool = f"{tool} · optional" if tool else "optional"
    return tool


def label_half_width(name, tool):
    """Half the width of a station label: the bold name over the smaller tool text."""
    return max(text_width(name, 15, True), text_width(tool, 12.5)) / 2


def terminus_tracks(group, single):
    """x offsets (from the terminus centre) of the vertical tracks that the lines in `group` take into the terminus.
    One line uses `single`; several are spread 12 px apart, the first one rightmost."""
    if len(group) == 1:
        return {group[0]: single}
    return {lid: ((len(group) - 1) / 2 - i) * 12 for i, lid in enumerate(group)}


def svg_document(width, height, elements):
    """Wrap the drawn elements in an <svg> element with a white background."""
    head = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.0f} {height:.0f}" '
            f'width="{width:.0f}" height="{height:.0f}">', f'<rect width="{width:.0f}" height="{height:.0f}" fill="#ffffff"/>']
    return "\n".join(head + elements + ["</svg>"])


class SubwayMap:
    """One map being laid out and drawn. The module docstring lists the steps, in the order they run.

    What the layout steps work out, and keep for the steps after them:

        trunk_lines       ids of the lines along the trunk, top to bottom
        branch_order      ids of the branches, each after the line it leaves
        trunk_y           y of row 0, the middle of the trunk
        trunk_line_y      line id -> y of that line along the trunk
        positions         (line id or "trunk", station name) -> (x, y) of the station
        paths             line id -> the points the line's path runs through
        feeds             the routed `feeds:` connectors: (points, colour, dashed, id)
    """

    def __init__(self, spec):
        self.spec = spec
        self.style = dict(STYLE, **(spec.get("style") or {}))
        self.cv = Canvas(self.style)
        self.lines = spec.get("lines") or {}        # line id -> line
        self.trunk = spec.get("trunk") or {}
        self.trunk_stations = self.trunk.get("stations") or []
        self.terminus = spec.get("terminus")
        self.input = spec.get("input")

    def lay_out(self):
        self.resolve_lines()
        self.place_rows()
        self.place_trunk()
        self.place_lines()
        self.place_terminus()
        self.finish_paths()
        self.route_feeds()

    def draw(self):
        """Draw everything, back to front, and return the SVG text."""
        self.draw_title()
        self.draw_lines()
        self.draw_trunk_stations()
        self.draw_line_stations()
        self.draw_terminus()
        self.draw_input()
        self.draw_outputs()
        width = self.spec.get("width") or max(self.cv.xmax + self.style["margin"], 900)   # measured before the legend
        height = self.draw_legend(width)
        return svg_document(width, height, self.cv.out)

    # ==== Layout ====================================================================================================

    def resolve_lines(self):
        """Fill in what the spec leaves out: each line's name, colour, row and end, and which lines run along the
        trunk. The trunk lines are stacked by the row they go to, top row first, so they never cross where they
        split."""
        lines = self.lines
        palette = palette_colours(self.spec.get("palette"))
        k = 0
        for lid, ln in lines.items():
            ln.setdefault("stations", [])
            if not is_branch(ln):
                ln.setdefault("name", lid)
                ln.setdefault("color", palette[k % len(palette)])
                k += 1
        self.branch_order = self._inherit_from_parents()

        trunk_lines = (self.trunk.get("lines")
                       or [lid for lid, ln in lines.items() if ln.get("from", "trunk") == "trunk"])
        for lid in trunk_lines:
            if lid not in lines:
                sys.exit(f"trunk.lines names '{lid}', which is not under lines:")
            lines[lid]["from"] = "trunk"
        for k, lid in enumerate(trunk_lines):      # default rows: spread the trunk lines -1, 0, +1, ...
            lines[lid].setdefault("row", k - (len(trunk_lines) - 1) / 2)
        self.trunk_lines = sorted(trunk_lines, key=lambda lid: lines[lid]["row"])
        for ln in lines.values():
            ln.setdefault("row", 0)
            ln.setdefault("to", "none")

    def _parent_of(self, lid):
        frm = self.lines[lid]["from"]
        if frm.get("line") not in self.lines or "station" not in frm:
            sys.exit(f"line '{lid}': from {frm} must be {{line: <id>, station: <name>}} naming another line")
        return frm["line"]

    def _inherit_from_parents(self):
        """Give each branch its parent line's colour, legend name and dashing. A branch can leave another branch, so
        each parent is done before its branches. Returns the branch ids in that order."""
        lines = self.lines
        order, pending = [], [lid for lid, ln in lines.items() if is_branch(ln)]
        while pending:
            ready = [lid for lid in pending if self._parent_of(lid) not in pending]
            if not ready:
                sys.exit(f"lines {', '.join(pending)} branch from each other in a loop")
            for lid in ready:
                ln, parent = lines[lid], lines[self._parent_of(lid)]
                ln.setdefault("name", parent["name"])
                ln.setdefault("color", parent["color"])
                if parent.get("optional"):
                    ln.setdefault("optional", True)
                pending.remove(lid)
            order += ready
        return order

    def place_rows(self):
        """Put the trunk low enough to leave room for the title and the rows above it, and stack the trunk lines
        `gap` apart around it."""
        s, term = self.style, self.terminus
        rows = [ln["row"] for ln in self.lines.values()] + ([term.get("row", 0)] if term else [])
        min_row = min(rows + [0])
        y0 = max(250, 160 - min_row * s["row_height"])
        if self.spec.get("title") is None:
            y0 -= 60
        self.trunk_y = y0
        n = max(len(self.trunk_lines), 1)
        self.trunk_line_y = {lid: y0 + (k - (n - 1) / 2) * s["gap"] for k, lid in enumerate(self.trunk_lines)}
        self.trunk_top = y0 - (n - 1) / 2 * s["gap"]
        self.trunk_bottom = y0 + (n - 1) / 2 * s["gap"]

    def row_y(self, row):
        """The y of a row. Row 0 is the trunk; negative rows are above it."""
        return self.trunk_y + row * self.style["row_height"]

    def place_trunk(self):
        """Space the trunk stations `spacing` apart, then work out where the trunk splits into its lines and where
        those lines' first stations can start."""
        s, lines = self.style, self.lines
        self.trunk_start_x = s["margin"] + 64 if self.input else s["margin"]     # leaves room for the input icon
        self.input_x = s["margin"] + 22
        self.trunk_labels_above = self.trunk.get("labels", "below") == "above"
        self.positions = {}
        x = self.trunk_start_x + 0.8 * s["spacing"]
        for st in self.trunk_stations:
            x = st.get("x", x + st.get("gap", 0))
            st["_x"] = x
            self.positions[("trunk", st["name"])] = (x, self.trunk_y)
            x += s["spacing"]

        # split far enough past the last trunk station to clear its label
        if self.trunk_stations:
            last = self.trunk_stations[-1]
            last_x = last["_x"]
            auto_gap = max(30, label_half_width(last["name"], last.get("tool", "") or "") - 14)
        else:
            last_x, auto_gap = self.trunk_start_x, 30
        self.split_x = last_x + self.trunk.get("split_gap", auto_gap)

        # at the split each trunk line bends at 45 degrees to its own row; their first stations come after the
        # widest bend, with room for their labels
        widest_bend = max([abs(self.row_y(lines[l]["row"]) - self.trunk_line_y[l]) for l in self.trunk_lines] + [0])
        first_labels = [label_half_width(lines[l]["stations"][0]["name"], lines[l]["stations"][0].get("tool", "") or "")
                        for l in self.trunk_lines if lines[l]["stations"]]
        branch_gap = self.trunk.get("branch_gap", max([60] + [h - 20 for h in first_labels]))
        self.branch_start = self.split_x + widest_bend + branch_gap

    def station_half_width(self, st):
        return label_half_width(st["name"], tool_text(st))

    def place_lines(self):
        """Place the stations of every line that isn't the trunk, and the start of each line's path.

        A line that joins a station on another line (`to: {line, station}`), and a `feeds:` connector, both need
        room to come in at 45 degrees. If an automatically placed target station is too close, it is pushed right
        and everything is placed again. A push also moves the stations after it, and the branches that leave them."""
        lines = self.lines
        # branches last: each needs the line it leaves to be placed first
        self.side_lines = ([l for l, ln in lines.items() if ln["from"] != "trunk" and not is_branch(ln)]
                           + self.branch_order)
        # stations whose output also goes to a station on another line: (line id or "trunk", station)
        self.feeders = ([("trunk", st) for st in self.trunk_stations if st.get("feeds")]
                        + [(lid, st) for lid, ln in lines.items() for st in ln["stations"] if st.get("feeds")])
        for _ in range(100):
            self.paths = {}
            for lid in self.trunk_lines:
                self._place_trunk_line(lid)
            for lid in self.side_lines:
                if is_branch(lines[lid]):
                    self._place_branch(lid)
                else:
                    self._place_side_line(lid)
            pushed_joins = self._push_join_targets()
            pushed_feeds = self._push_feed_targets()
            if not (pushed_joins or pushed_feeds):
                break

    def _place_stations(self, lid, start_x, y, step):
        """Space a line's stations `step` apart from start_x, and far enough apart for their labels. A station's own
        `x` wins; `gap` adds space before it, and `_push` is the room the push steps found it needs."""
        x, prev = start_x, None
        for st in self.lines[lid]["stations"]:
            if prev is not None:
                x = max(x, prev["_x"] + self.station_half_width(prev) + self.station_half_width(st) + 6)
            x = st.get("x", x + st.get("gap", 0) + st.get("_push", 0))
            st["_x"], st["_y"] = x, y
            self.positions[(lid, st["name"])] = (x, y)
            x += step
            prev = st

    def _place_trunk_line(self, lid):
        """A trunk line runs from the input to the split, then bends at 45 degrees to its own row."""
        ty, ry = self.trunk_line_y[lid], self.row_y(self.lines[lid]["row"])
        pts = [(self.trunk_start_x, ty), (self.split_x, ty)]
        if abs(ry - ty) > 0.5:
            pts.append((self.split_x + abs(ry - ty), ry))
        self._place_stations(lid, self.branch_start, ry, self.style["branch_spacing"])
        self.paths[lid] = pts

    def _place_branch(self, lid):
        """A branch leaves a station on its parent line at 45 degrees, then runs along its own row."""
        s, ln = self.style, self.lines[lid]
        ry, frm = self.row_y(ln["row"]), ln["from"]
        key = (frm["line"], frm["station"])
        if key not in self.positions:
            sys.exit(f"line '{lid}': from {frm} does not name a station on line '{frm['line']}'")
        sx, sy = self.positions[key]
        d = abs(ry - sy)
        self.paths[lid] = [(sx, sy)] + ([(sx + d, ry)] if d > 0.5 else [])
        start = sx + max(d + 60, s["branch_spacing"])
        # A sibling branch going further out on the same side runs its diagonal under this branch's labels (which
        # sit on the side away from the parent): start far enough right to clear it.
        first = ln["stations"][0] if ln["stations"] else None
        for o in self.branch_order:
            ob = self.lines[o]
            d2 = abs(self.row_y(ob["row"]) - sy)
            if (o != lid and first and (ob["from"]["line"], ob["from"]["station"]) == key
                    and (self.row_y(ob["row"]) - sy) * (ry - sy) > 0 and d2 > d):
                bottom = LABEL_OFFSET + 2 + (TOOL_OFFSET if first.get("tool") else 0) + 4   # the label's far edge
                start = max(start, sx + min(d2, d + bottom) + s["line_width"] / 2 + self.station_half_width(first) + 16)
        self._place_stations(lid, start, ry, s["branch_spacing"])

    def _place_side_line(self, lid):
        """A side line leaves the input icon or a trunk station straight up or down, then runs along its own row.
        Side lines usually span a long stretch, so their stations are spaced a little wider."""
        s, ln = self.style, self.lines[lid]
        ry, frm = self.row_y(ln["row"]), ln["from"]
        if frm == "input":
            ox = self.input_x + 16
            oy = self.trunk_y + (ICON_H / 2 + 5) * (1 if ry > self.trunk_y else -1)
        else:
            key = ("trunk", frm)
            if key not in self.positions:
                sys.exit(f"line '{lid}': from '{frm}' is not 'trunk', 'input', a trunk station name "
                         f"or {{line: <id>, station: <name>}}")
            ox = self.positions[key][0]
            oy = (self.trunk_bottom + 13) if ry > self.trunk_y else (self.trunk_top - 13)
        self.paths[lid] = [(ox, oy), (ox, ry)]
        self._place_stations(lid, ox + 1.5 * s["spacing"], ry, 1.1 * s["spacing"])

    def _station(self, lid, name):
        """The station called `name` on line `lid`, or None."""
        if lid not in self.lines:
            return None
        return next((st for st in self.lines[lid]["stations"] if st["name"] == name), None)

    def _push_join_targets(self):
        """Push right each joined station that its joining line would otherwise reach from behind. A station with
        its own `x` is never moved. Returns True if anything moved."""
        pushed = False
        for lid, ln in self.lines.items():
            to = ln.get("to")
            target = self._station(to.get("line"), to.get("station")) if isinstance(to, dict) else None
            if target is None or "x" in target:
                continue
            ry = self.row_y(ln["row"])
            behind = max([self.paths[lid][-1][0]] + [st["_x"] for st in ln["stations"]]) + 30
            need = behind + abs(target["_y"] - ry) + 8      # room to drop in at 45 degrees
            if target["_x"] < need - 0.5:
                target["_push"] = target.get("_push", 0) + need - target["_x"]
                pushed = True
        return pushed

    def _push_feed_targets(self):
        """Push right each `feeds:` target that is too close for both 45-degree legs of the connector. A station
        with its own `x` is never moved. Returns True if anything moved."""
        pushed = False
        for src, st in self.feeders:
            x1, y1 = self.positions[(src, st["name"])]
            for ref in st["feeds"]:
                target = self._station(ref.get("line"), ref.get("station"))
                if target is None or "x" in target:
                    continue
                need = x1 + abs(target["_y"] - y1) + FEED_LANE
                if target["_x"] < need - 0.5:
                    target["_push"] = target.get("_push", 0) + need - target["_x"]
                    pushed = True
        return pushed

    def place_terminus(self):
        """Put the end station to the right of every other station. Lines arriving from above or below come into its
        pill on vertical tracks, side by side; lines on its own row run straight into it."""
        term, lines = self.terminus, self.lines
        if not term:
            return
        self.terminus_x = term.get("x", max([p[0] for p in self.positions.values()] + [self.split_x]) + 100)
        self.terminus_y = ty = self.row_y(term.get("row", 0))
        into = [lid for lid, ln in lines.items() if ln["to"] == "terminus"]
        above = [lid for lid in into if self.row_y(lines[lid]["row"]) < ty - 0.5]
        below = [lid for lid in into if self.row_y(lines[lid]["row"]) > ty + 0.5]
        level = [lid for lid in into if lid not in above and lid not in below]
        above.sort(key=lambda l: lines[l]["row"])          # top line first -> rightmost track
        below.sort(key=lambda l: -lines[l]["row"])         # bottom line first -> rightmost track
        tracks = terminus_tracks(above, -7)
        tracks.update(terminus_tracks(below, 7))
        self.lines_into_terminus = into
        self.lines_level_with_terminus = level
        self.terminus_tracks = tracks
        self.terminus_width = max(34, 2 * max([abs(v) for v in tracks.values()] + [0]) + 22)
        self.terminus_half_height = 14 + 6 * max(len(level) - 1, 0)

    def finish_paths(self):
        """End each line's path: in the terminus, in a station on another line, or at its own last station."""
        for lid, ln in self.lines.items():
            pts = self.paths[lid]
            ry = self.row_y(ln["row"])
            last_x = ln["stations"][-1]["_x"] if ln["stations"] else pts[-1][0]
            if ln["to"] == "terminus":
                self._end_in_terminus(lid, pts, ry)
            elif isinstance(ln["to"], dict):
                self._end_in_station(lid, ln, pts, ry, last_x)
            else:
                pts.append((last_x, ry))

    def _end_in_terminus(self, lid, pts, ry):
        if not self.terminus:
            sys.exit(f"line '{lid}' goes to the terminus, but the spec has no terminus:")
        ty = self.terminus_y
        if lid in self.terminus_tracks:                    # from above or below: along the row, then down its track
            vx = self.terminus_x + self.terminus_tracks[lid]
            reach = self.terminus_half_height + self.terminus_width / 2 - 5
            pts += [(vx, ry), (vx, ty - reach if ry < ty else ty + reach)]
        else:                                              # on the terminus's own row: straight in
            pts.append((self.terminus_x - self.terminus_width / 2 + 4, ry))

    def _end_in_station(self, lid, ln, pts, ry, last_x):
        """Join a station on another line: drop in at 45 degrees if there is room, else run along to the station and
        drop in vertically. Joining lines get a white casing, so they read as bridging over what they cross."""
        to = ln["to"]
        key = (to["line"], to["station"])
        if key not in self.positions:
            sys.exit(f"line '{lid}': to {to} does not name a station on another line")
        sx, sy = self.positions[key]
        sgn = 1 if sy > ry else -1
        ex, ey = sx - 8, sy - 8 * sgn
        x_drop = ex - abs(ey - ry)
        behind = max(last_x, pts[-1][0]) + 30              # must leave after its own last station
        if x_drop >= behind:
            pts += [(x_drop, ry), (ex, ey)]
        elif sx >= behind:
            r_st = self.style["station_radius"]
            pts += [(sx, ry), (sx, sy - (r_st + 2) * sgn)]
        else:
            sys.exit(f"line '{lid}' joins '{to['station']}' (x={sx:.0f}), which is behind its own stations; "
                     f"move that station right (x:) or give this line's stations smaller x values")
        ln["_casing"] = True
        ln["_joins"] = key

    def route_feeds(self):
        """Route each `feeds:` connector, and note which feeds touch each station, and from which side (for the label
        sides and the overlap check)."""
        self.feeds = []
        self.feeds_touching = {}    # station key -> ids of the feeds that start or end there
        self.feed_ys = {}           # station key -> the y each of those feeds heads towards, right next to the station
        for src, st in self.feeders:
            for ref in st["feeds"]:
                self._route_feed(src, st, ref)

    def _route_feed(self, src, st, ref):
        """Leave the station at 45 degrees, run along a lane, and drop into the target at 45 degrees. If the stations
        are too close for that (because of a fixed x), go straight from one to the other."""
        s, lines = self.style, self.lines
        x1, y1 = self.positions[(src, st["name"])]
        if not isinstance(ref, dict) or self._station(ref.get("line"), ref.get("station")) is None:
            sys.exit(f"station '{st['name']}': feeds {ref} does not name a station on another line "
                     f"(use {{line: <id>, station: <name>}})")
        target = (ref["line"], ref["station"])
        x2, y2 = self.positions[target]
        if x2 <= x1 + 1:
            sys.exit(f"station '{st['name']}' feeds '{ref['station']}', which is not to its right; "
                     f"move one of them (x:)")
        sgn = 1 if y2 > y1 else -1
        if src == "trunk":          # leave from the top or bottom edge of the trunk pill
            sy = (self.trunk_bottom + 13) if y2 > self.trunk_y else (self.trunk_top - 13)
        else:
            sy = y1
        dy = abs(y2 - sy)
        d_in = min(s["row_height"] / 2, dy / 2)
        d_out = dy - d_in
        if d_out + d_in + 2 * s["corner"] > x2 - x1:
            pts = [(x1, sy), (x2, y2)]
        else:
            pts = [(x1, sy), (x1 + d_out, sy + sgn * d_out), (x2 - d_in, y2 - sgn * d_in), (x2, y2)]
        # the trunk has many colours, so a feed from it takes the receiving line's
        colour_from = lines[ref["line"]] if src == "trunk" else lines[src]
        fid = f"feed '{st['name']}' -> '{ref['station']}'"
        self.feeds.append((pts, colour_from["color"], bool(colour_from.get("optional")), fid))
        for key, y in (((src, st["name"]), pts[1][1]), (target, pts[-2][1])):
            self.feeds_touching.setdefault(key, []).append(fid)
            self.feed_ys.setdefault(key, []).append(y)

    # ==== Drawing ===================================================================================================

    def draw_title(self):
        s = self.style
        if self.spec.get("title"):
            self.cv.text(s["margin"], 56, self.spec["title"], 30, True, anchor="start")
        if self.spec.get("subtitle"):
            self.cv.text(s["margin"], 84, self.spec["subtitle"], 15, fill=s["muted"], anchor="start")

    def draw_lines(self):
        """Plain side lines first, then the trunk lines (bottom one first), then the lines that join a station, and
        the feeds on top of everything."""
        lines = self.lines
        order = ([l for l in lines if lines[l]["from"] != "trunk" and not lines[l].get("_casing")]
                 + list(reversed(self.trunk_lines))
                 + [l for l in lines if lines[l].get("_casing")])
        for lid in order:
            ln = lines[lid]
            # White "bridge" casing only on side lines: on a trunk line it would also eat into its parallel
            # neighbours. A branch's casing starts after its first bend, so it doesn't cut into the line it leaves.
            self.cv.polyline(self.paths[lid], ln["color"], lid, dashed=bool(ln.get("optional")),
                             casing=bool(ln.get("_casing")) and ln["from"] != "trunk",
                             casing_skip=1 if is_branch(ln) else 0)
        for pts, color, dashed, fid in self.feeds:       # bridged over everything they cross
            self.cv.polyline(pts, color, fid, dashed=dashed, casing=True, casing_pts=trim_path(pts, 18, 18))

    def _draw_label(self, x, y, st, above):
        """A station's bold name with its tool text under it, above or below the point (x, y)."""
        name, tool, muted = st["name"], tool_text(st), self.style["muted"]
        desc = f"label '{name}'"
        if above:
            self.cv.text(x, y - LABEL_OFFSET, name, 15, True, desc=desc)
            self.cv.text(x, y - LABEL_OFFSET + TOOL_OFFSET, tool, 12.5, fill=muted, desc=desc)
        else:
            self.cv.text(x, y + LABEL_OFFSET + 2, name, 15, True, desc=desc)
            self.cv.text(x, y + LABEL_OFFSET + 2 + TOOL_OFFSET, tool, 12.5, fill=muted, desc=desc)

    def draw_trunk_stations(self):
        """Trunk stations are pills spanning all the trunk lines."""
        lines = self.lines
        for st in self.trunk_stations:
            key = ("trunk", st["name"])
            leaving = [l for l in lines if lines[l]["from"] == st["name"]]
            above = self._trunk_label_above(st, key, leaving)
            self.cv.pill(st["_x"], self.trunk_top, self.trunk_bottom,
                         self.trunk_lines + leaving + self.feeds_touching.get(key, []), desc=f"station '{st['name']}'")
            self._draw_label(st["_x"], self.trunk_top if above else self.trunk_bottom, st, above)

    def _trunk_label_above(self, st, key, leaving):
        """Trunk labels go below the trunk (or above, with `labels: above`), and switch sides if a line or a feed
        leaves the station on that side. An explicit `label: above|below` wins."""
        above = self.trunk_labels_above
        if "label" in st:
            return st["label"] == "above"
        if (any((self.row_y(self.lines[l]["row"]) < self.trunk_y) == above for l in leaving)
                or any((y < self.trunk_y) == above for y in self.feed_ys.get(key, []))):
            return not above
        return above

    def draw_line_stations(self):
        """Every other station is a circle. This also notes which side each label went on, and which sides joining
        lines arrive from, for placing the output icons."""
        lines = self.lines
        for lid, ln in lines.items():
            for st in ln["stations"]:
                key = (lid, st["name"])
                joiners = [l for l, o in lines.items() if o.get("_joins") == key]
                leavers = [l for l, o in lines.items()
                           if is_branch(o) and (o["from"]["line"], o["from"]["station"]) == key]
                self.cv.station(st["_x"], st["_y"], {lid, *joiners, *leavers, *self.feeds_touching.get(key, [])},
                                st.get("optional", False), desc=f"station '{st['name']}'")
                above = self._line_label_above(ln, st, key, joiners + leavers)
                st["_label_above"] = above
                st["_joined_above"] = any(self.row_y(lines[j]["row"]) < st["_y"] for j in joiners)
                st["_joined_below"] = any(self.row_y(lines[j]["row"]) > st["_y"] for j in joiners)
                self._draw_label(st["_x"], st["_y"], st, above)

    def _line_label_above(self, ln, st, key, meeting):
        """Labels go on the side away from the trunk; a branch's go on the side away from its parent line. They
        switch sides if a line in `meeting`, or a feed, meets the station on that side. An explicit
        `label: above|below` wins."""
        above = st["_y"] < self.trunk_y - 0.5
        if is_branch(ln):
            above = ln["row"] < self.lines[ln["from"]["line"]]["row"]
        if "label" in st:
            return st["label"] == "above"
        if (any((self.row_y(self.lines[j]["row"]) < st["_y"]) == above for j in meeting)
                or any((y < st["_y"]) == above for y in self.feed_ys.get(key, []))):
            return not above
        return above

    def draw_terminus(self):
        term = self.terminus
        if not term:
            return
        tx, ty, w, half = self.terminus_x, self.terminus_y, self.terminus_width, self.terminus_half_height
        desc = f"label '{term['name']}'"
        self.cv.pill(tx, ty - half, ty + half, self.lines_into_terminus, w=w, desc=f"station '{term['name']}'")
        self.cv.terminus = f"station '{term['name']}'"
        self.cv.text(tx + w / 2 + 13, ty - 4, term["name"], 17, True, anchor="start", desc=desc)
        self.cv.text(tx + w / 2 + 13, ty + 15, term.get("sublabel", ""), 12.5, fill=self.style["muted"],
                     anchor="start", desc=desc)

    def draw_input(self):
        """The input file icon at the start of the trunk, labelled above it (or underneath, if a side line leaves
        the input upwards)."""
        inp = self.input
        if not inp:
            return
        x, y = self.input_x, self.trunk_y
        self.cv.file_icon(x, y, inp.get("file", "IN"), inp.get("color", "#57606a"), "input icon")
        if any(l["from"] == "input" and self.row_y(l["row"]) < y for l in self.lines.values()):
            label_y, sublabel_y = y + ICON_H / 2 + 22, y + ICON_H / 2 + 38
        else:
            label_y, sublabel_y = y - 58, y - 42
        self.cv.text(x, label_y, inp.get("label", "Input"), 15, True, desc="input label")
        self.cv.text(x, sublabel_y, inp.get("sublabel", ""), 12.5, fill=self.style["muted"], desc="input label")

    def draw_outputs(self):
        """File icons for each station's `outputs`, on the side away from its label."""
        lines, s = self.lines, self.style
        mid_color = lines[self.trunk_lines[len(self.trunk_lines) // 2]]["color"] if self.trunk_lines else s["ink"]
        trunk_edge = self.trunk_top if not self.trunk_labels_above else self.trunk_bottom
        for st in self.trunk_stations:
            for o in st.get("outputs") or []:
                self._draw_output(o, st["_x"], trunk_edge, "trunk", mid_color, 14)
        for lid, ln in lines.items():
            for i, st in enumerate(ln["stations"]):
                for o in st.get("outputs") or []:
                    at_end = i == len(ln["stations"]) - 1 and ln["to"] == "none"
                    # "above" = the station's label is above, so the icon goes below it (and "below" the other way)
                    kind = "end" if at_end else ("above" if st["_label_above"] else "below")
                    # joining lines arrive from the left; if one comes in on the icon's side, move the icon right
                    taken = {"above": st["_joined_below"], "below": st["_joined_above"]}.get(kind, False)
                    self._draw_output(o, st["_x"], st["_y"], kind, ln["color"], s["station_radius"] + 2,
                                      shift=60 if taken else 0)
        term = self.terminus
        if term:
            level, into = self.lines_level_with_terminus, self.lines_into_terminus
            level_color = lines[level[0]]["color"] if level else (lines[into[0]]["color"] if into else s["ink"])
            for o in term.get("outputs") or ([{"file": term["file"]}] if term.get("file") else []):
                self._draw_output(o, self.terminus_x, self.terminus_y, "terminus", level_color,
                                  self.terminus_half_height + self.terminus_width / 2 + 4)

    def _draw_output(self, o, sx, sy, kind, color, edge, shift=0):
        """One output icon, its label, and a dotted connector from the station at (sx, sy).

        kind (trunk | above | below | end | terminus) picks the default place for the icon; `dx` / `dy` in the spec
        override it. shift moves the default sideways. edge is how far from the station centre the connector starts."""
        dx, dy, side = {"trunk": (-75, -(sy - self.trunk_top) - 69, "left"),
                        "above": (0, 62, "right"),
                        "below": (0, -62, "right"),
                        "end": (100, 0, "right"),
                        "terminus": (74, 84, "right")}[kind]
        dx, dy = o.get("dx", dx + shift), o.get("dy", dy)
        side = o.get("label_side", side)
        ix, iy = sx + dx, sy + dy
        vx, vy = ix - sx, iy - sy
        dist = math.hypot(vx, vy) or 1
        ux, uy = vx / dist, vy / dist
        # stop the connector at the icon's edge (the box's half-extent along the direction)
        t_icon = min((ICON_W / 2 + 4) / abs(ux) if ux else math.inf, (ICON_H / 2 + 4) / abs(uy) if uy else math.inf)
        if dist > edge + t_icon:
            self.cv.connector(sx + ux * edge, sy + uy * edge, ix - ux * t_icon, iy - uy * t_icon)
        self.cv.file_icon(ix, iy, o.get("file", "OUT"), o.get("color", color), f"output icon '{o.get('file')}'")
        muted, desc = self.style["muted"], f"output label '{o.get('label')}'"
        for k, part in enumerate(two_lines(o.get("label", ""))):
            if side == "left":
                self.cv.text(ix - ICON_W / 2 - 11, iy + 4 + 16 * k, part, 12.5, fill=muted, anchor="end", desc=desc)
            else:
                self.cv.text(ix + ICON_W / 2 + 11, iy - 4 + 16 * k, part, 12.5, fill=muted, anchor="start", desc=desc)

    def draw_legend(self, width):
        """A rule under the map, one legend entry per line (wrapping onto more rows if needed), the station
        symbols, and the footnote. Returns the map's height."""
        s, cv, m = self.style, self.cv, self.style["margin"]
        ly = cv.ymax + 62
        cv.out.append(f'<line x1="{m}" y1="{ly - 36:.1f}" x2="{width - m:.1f}" y2="{ly - 36:.1f}" stroke="{s["rule"]}" '
                      f'stroke-width="1.5"/>')
        lx = m
        for kind, color, opt, name in self._legend_items():
            w_item = (58 if kind == "line" else 27) + text_width(name, 14) + 30
            if lx + w_item > width - m and lx > m:
                lx, ly = m, ly + 30
            if kind == "line":
                da = f' stroke-dasharray="{s["dash"]}"' if opt else ""
                cv.out.append(f'<line x1="{lx}" y1="{ly:.1f}" x2="{lx + 46}" y2="{ly:.1f}" stroke="{color}" '
                              f'stroke-width="{s["line_width"]}" stroke-linecap="round"{da}/>')
                cv.text(lx + 58, ly + 5, name, 14, anchor="start", track=False)
            else:
                da = ' stroke-dasharray="4 3"' if opt else ""
                cv.out.append(f'<circle cx="{lx + 10}" cy="{ly:.1f}" r="9" fill="#ffffff" stroke="{s["ink"]}" '
                              f'stroke-width="3"{da}/>')
                cv.text(lx + 27, ly + 5, name, 14, anchor="start", track=False)
            lx += w_item
        fy = ly + 34
        if self.spec.get("footnote"):
            for line in wrap_words(self.spec["footnote"], int((width - 2 * m) / (12.5 * 0.53))):
                cv.text(m, fy, line, 12.5, fill=s["muted"], anchor="start", track=False)
                fy += 18
        return self.spec.get("height") or fy + 12

    def _legend_items(self):
        """(kind, colour, dashed, text) for each legend entry. A branch shares its parent's entry."""
        items = []
        for ln in self.lines.values():
            name = ln.get("legend", ln["name"])
            if ln.get("optional") and "optional" not in name.lower():
                name += " (optional)"
            item = ("line", ln["color"], bool(ln.get("optional")), name)
            if item not in items:
                items.append(item)
        items.append(("station", None, False, "Step"))
        all_stations = [st for ln in self.lines.values() for st in ln["stations"]] + self.trunk_stations
        if any(st.get("optional") for st in all_stations):
            items.append(("station", None, True, "Optional step"))
        return items
