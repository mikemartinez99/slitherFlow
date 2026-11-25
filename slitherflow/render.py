"""Lay out a spec (trunk, lines, branches, joins, feeds, terminus) and draw it as SVG."""
import math
import sys

from .canvas import Canvas, trim_path, two_lines, wrap_words
from .style import FEED_LANE, ICON_H, ICON_W, LABEL_OFFSET, STYLE, TOOL_OFFSET, palette_colours, text_width


def render(spec):
    s = dict(STYLE, **(spec.get("style") or {}))
    cv = Canvas(s)
    m, lw, gap, rh = s["margin"], s["line_width"], s["gap"], s["row_height"]
    palette = palette_colours(spec.get("palette"))

    lines = spec.get("lines") or {}
    is_branch = lambda ln: isinstance(ln.get("from"), dict)   # from: {line: <id>, station: <name>}
    k = 0
    for lid, ln in lines.items():
        ln.setdefault("stations", [])
        if not is_branch(ln):
            ln.setdefault("name", lid)
            ln.setdefault("color", palette[k % len(palette)])
            k += 1

    def parent_of(lid):
        frm = lines[lid]["from"]
        if frm.get("line") not in lines or "station" not in frm:
            sys.exit(f"line '{lid}': from {frm} must be {{line: <id>, station: <name>}} naming another line")
        return frm["line"]

    # branches inherit their parent line's colour, legend name and dashing, so resolve parents first
    branch_order, pending = [], [lid for lid, ln in lines.items() if is_branch(ln)]
    while pending:
        ready = [lid for lid in pending if parent_of(lid) not in pending]
        if not ready:
            sys.exit(f"lines {', '.join(pending)} branch from each other in a loop")
        for lid in ready:
            ln, par = lines[lid], lines[parent_of(lid)]
            ln.setdefault("name", par["name"])
            ln.setdefault("color", par["color"])
            if par.get("optional"):
                ln.setdefault("optional", True)
            pending.remove(lid)
        branch_order += ready
    trunk = spec.get("trunk") or {}
    trunk_stations = trunk.get("stations") or []
    trunk_lines = trunk.get("lines") or [lid for lid, ln in lines.items() if ln.get("from", "trunk") == "trunk"]
    for lid in trunk_lines:
        if lid not in lines:
            sys.exit(f"trunk.lines names '{lid}', which is not under lines:")
        lines[lid]["from"] = "trunk"
    for k, lid in enumerate(trunk_lines):  # default rows: spread trunk lines -1, 0, +1, ...
        lines[lid].setdefault("row", k - (len(trunk_lines) - 1) / 2)
    # stack trunk lines by the row they branch to (top row first), so they never cross when they split
    trunk_lines = sorted(trunk_lines, key=lambda lid: lines[lid]["row"])
    for lid, ln in lines.items():
        ln.setdefault("row", 0)
        ln.setdefault("to", "none")
    term = spec.get("terminus")

    # ---- vertical placement ----
    rows = [ln["row"] for ln in lines.values()] + ([term.get("row", 0)] if term else [])
    min_row = min(rows + [0])
    y0 = max(250, 160 - min_row * rh)
    if spec.get("title") is None:
        y0 -= 60
    ntl = max(len(trunk_lines), 1)
    trunk_y = {lid: y0 + (k - (ntl - 1) / 2) * gap for k, lid in enumerate(trunk_lines)}
    trunk_top, trunk_bot = y0 - (ntl - 1) / 2 * gap, y0 + (ntl - 1) / 2 * gap
    row_y = lambda row: y0 + row * rh

    # ---- trunk stations (x) ----
    inp = spec.get("input")
    x_in = m + 64 if inp else m
    input_cx = m + 22
    pos = {}  # (line id or 'trunk', station name) -> (x, y)
    x = x_in + 0.8 * s["spacing"]
    for st in trunk_stations:
        x = st.get("x", x + st.get("gap", 0))
        st["_x"] = x
        pos[("trunk", st["name"])] = (x, y0)
        x += s["spacing"]
    last_trunk_x = trunk_stations[-1]["_x"] if trunk_stations else x_in
    if trunk_stations:
        st = trunk_stations[-1]
        half_label = max(text_width(st["name"], 15, True), text_width(st.get("tool", "") or "", 12.5)) / 2
        auto_gap = max(30, half_label - 14)
    else:
        auto_gap = 30
    split_x = last_trunk_x + trunk.get("split_gap", auto_gap)

    def half_label(st):
        tool = st.get("tool", "") or ""
        if st.get("optional"):
            tool = f"{tool} · optional" if tool else "optional"
        return max(text_width(st["name"], 15, True), text_width(tool, 12.5)) / 2

    def place(lid, start_x, y, step):
        x, prev = start_x, None
        for st in lines[lid]["stations"]:
            if prev is not None:   # automatic spacing also leaves room for both labels
                x = max(x, prev["_x"] + half_label(prev) + half_label(st) + 6)
            x = st.get("x", x + st.get("gap", 0) + st.get("_push", 0))
            st["_x"], st["_y"] = x, y
            pos[(lid, st["name"])] = (x, y)
            x += step
            prev = st

    def station_of(lid, name):
        return next((st for st in lines[lid]["stations"] if st["name"] == name), None) if lid in lines else None

    widest_bend = max([abs(row_y(lines[l]["row"]) - trunk_y[l]) for l in trunk_lines] + [0])
    first_labels = [max(text_width(lines[l]["stations"][0]["name"], 15, True),
                        text_width(lines[l]["stations"][0].get("tool", "") or "", 12.5)) / 2
                    for l in trunk_lines if lines[l]["stations"]]
    branch_start = split_x + widest_bend + trunk.get("branch_gap", max([60] + [h - 20 for h in first_labels]))
    side_lines = [l for l, ln in lines.items() if ln["from"] != "trunk" and not is_branch(ln)] + branch_order
    # stations whose output also goes to a station on another line: (line id or 'trunk', station)
    feeders = ([("trunk", st) for st in trunk_stations if st.get("feeds")]
               + [(lid, st) for lid, ln in lines.items() for st in ln["stations"] if st.get("feeds")])

    # Place every line, then push right any automatically placed station that a joining line would otherwise
    # reach from behind, and place again (a push also moves the stations after it and the branches leaving them).
    for _ in range(100):
        geo = {}
        # ---- main (trunk) lines ----
        for lid in trunk_lines:
            ty, ry = trunk_y[lid], row_y(lines[lid]["row"])
            pts = [(x_in, ty), (split_x, ty)]
            if abs(ry - ty) > 0.5:
                pts.append((split_x + abs(ry - ty), ry))
            place(lid, branch_start, ry, s["branch_spacing"])
            geo[lid] = pts
        # ---- side lines (from the input or a trunk station), then branches (from a station on another line) ----
        for lid in side_lines:
            ln = lines[lid]
            ry, frm = row_y(ln["row"]), ln["from"]
            if is_branch(ln):
                key = (frm["line"], frm["station"])
                if key not in pos:
                    sys.exit(f"line '{lid}': from {frm} does not name a station on line '{frm['line']}'")
                sx, sy = pos[key]
                d = abs(ry - sy)                      # leave the station at 45 degrees
                geo[lid] = [(sx, sy)] + ([(sx + d, ry)] if d > 0.5 else [])
                start = sx + max(d + 60, s["branch_spacing"])
                # a sibling branch going further out on the same side runs its diagonal under this branch's
                # labels (which sit on the side away from the parent): start far enough right to clear it
                first = ln["stations"][0] if ln["stations"] else None
                for o in branch_order:
                    ob = lines[o]
                    d2 = abs(row_y(ob["row"]) - sy)
                    if (o != lid and first and (ob["from"]["line"], ob["from"]["station"]) == key
                            and (row_y(ob["row"]) - sy) * (ry - sy) > 0 and d2 > d):
                        bottom = LABEL_OFFSET + 2 + (TOOL_OFFSET if first.get("tool") else 0) + 4  # label's far edge
                        start = max(start, sx + min(d2, d + bottom) + s["line_width"] / 2 + half_label(first) + 16)
                place(lid, start, ry, s["branch_spacing"])
                continue
            if frm == "input":
                ox = input_cx + 16
                oy = y0 + (ICON_H / 2 + 5) * (1 if ry > y0 else -1)
            else:
                key = ("trunk", frm)
                if key not in pos:
                    sys.exit(f"line '{lid}': from '{frm}' is not 'trunk', 'input', a trunk station name "
                             f"or {{line: <id>, station: <name>}}")
                ox = pos[key][0]
                oy = (trunk_bot + 13) if ry > y0 else (trunk_top - 13)
            geo[lid] = [(ox, oy), (ox, ry)]
            # side lines usually span a long stretch, so their stations are spaced a little wider
            place(lid, ox + 1.5 * s["spacing"], ry, 1.1 * s["spacing"])
        # ---- joins that arrive from behind: push the target station right ----
        pushed = False
        for lid, ln in lines.items():
            to = ln.get("to")
            target = station_of(to.get("line"), to.get("station")) if isinstance(to, dict) else None
            if target is None or "x" in target:
                continue
            ry = row_y(ln["row"])
            behind = max([geo[lid][-1][0]] + [st["_x"] for st in ln["stations"]]) + 30
            need = behind + abs(target["_y"] - ry) + 8      # room to drop in at 45 degrees
            if target["_x"] < need - 0.5:
                target["_push"] = target.get("_push", 0) + need - target["_x"]
                pushed = True
        for src, st in feeders:                             # feeds need room for both 45-degree legs
            x1, y1 = pos[(src, st["name"])]
            for ref in st["feeds"]:
                target = station_of(ref.get("line"), ref.get("station"))
                if target is None or "x" in target:
                    continue
                need = x1 + abs(target["_y"] - y1) + FEED_LANE
                if target["_x"] < need - 0.5:
                    target["_push"] = target.get("_push", 0) + need - target["_x"]
                    pushed = True
        if not pushed:
            break

    # ---- terminus ----
    all_station_x = [p[0] for p in pos.values()]
    if term:
        tx = term.get("x", max(all_station_x + [split_x]) + 100)
        ty = row_y(term.get("row", 0))
        into = [lid for lid, ln in lines.items() if ln["to"] == "terminus"]
        above = [lid for lid in into if row_y(lines[lid]["row"]) < ty - 0.5]
        below = [lid for lid in into if row_y(lines[lid]["row"]) > ty + 0.5]
        level = [lid for lid in into if lid not in above and lid not in below]
        above.sort(key=lambda l: lines[l]["row"])                 # top line first -> rightmost track
        below.sort(key=lambda l: -lines[l]["row"])                # bottom line first -> rightmost track

        def tracks(group, single):
            if len(group) == 1:
                return {group[0]: single}
            return {lid: ((len(group) - 1) / 2 - i) * 12 for i, lid in enumerate(group)}
        offs = tracks(above, -7)
        offs.update(tracks(below, 7))
        pill_w = max(34, 2 * max([abs(v) for v in offs.values()] + [0]) + 22)
        half = 14 + 6 * max(len(level) - 1, 0)
    # ---- finish line geometry ----
    for lid, ln in lines.items():
        pts = geo[lid]
        ry = row_y(ln["row"])
        last_x = ln["stations"][-1]["_x"] if ln["stations"] else pts[-1][0]
        to = ln["to"]
        if to == "terminus":
            if not term:
                sys.exit(f"line '{lid}' goes to the terminus, but the spec has no terminus:")
            if lid in offs:
                vx = tx + offs[lid]
                pts += [(vx, ry), (vx, ty - (half + pill_w / 2 - 5) if ry < ty else ty + (half + pill_w / 2 - 5))]
            else:
                pts.append((tx - pill_w / 2 + 4, ry))
        elif isinstance(to, dict):
            key = (to["line"], to["station"])
            if key not in pos:
                sys.exit(f"line '{lid}': to {to} does not name a station on another line")
            sx, sy = pos[key]
            sgn = 1 if sy > ry else -1
            ex, ey = sx - 8, sy - 8 * sgn
            x_drop = ex - abs(ey - ry)
            behind = max(last_x, pts[-1][0]) + 30           # must leave after its own last station
            if x_drop >= behind:
                pts += [(x_drop, ry), (ex, ey)]
            elif sx >= behind:                               # no room for 45 degrees: run along, drop in vertically
                r_st = s["station_radius"]
                pts += [(sx, ry), (sx, sy - (r_st + 2) * sgn)]
            else:
                sys.exit(f"line '{lid}' joins '{to['station']}' (x={sx:.0f}), which is behind its own stations; "
                         f"move that station right (x:) or give this line's stations smaller x values")
            ln["_casing"] = True
            ln["_joins"] = key
        else:
            pts.append((last_x, ry))

    # ---- feeds: leave the station at 45 degrees, run along a lane, drop into the target at 45 degrees ----
    feeds = []            # (points, colour, dashed, id)
    touching = {}         # station key -> ids of feeds that start or end there (for the overlap check)
    feed_ys = {}          # station key -> y the feed heads towards right next to the station (for label sides)
    for src, st in feeders:
        x1, y1 = pos[(src, st["name"])]
        for ref in st["feeds"]:
            if not isinstance(ref, dict) or station_of(ref.get("line"), ref.get("station")) is None:
                sys.exit(f"station '{st['name']}': feeds {ref} does not name a station on another line "
                         f"(use {{line: <id>, station: <name>}})")
            tkey = (ref["line"], ref["station"])
            x2, y2 = pos[tkey]
            if x2 <= x1 + 1:
                sys.exit(f"station '{st['name']}' feeds '{ref['station']}', which is not to its right; "
                         f"move one of them (x:)")
            sgn = 1 if y2 > y1 else -1
            sy = y1 if src != "trunk" else ((trunk_bot + 13) if y2 > y0 else (trunk_top - 13))
            dy = abs(y2 - sy)
            d_in = min(rh / 2, dy / 2)
            d_out = dy - d_in
            if d_out + d_in + 2 * s["corner"] > x2 - x1:   # no room for a clean lane (fixed x): go straight
                pts = [(x1, sy), (x2, y2)]
            else:
                pts = [(x1, sy), (x1 + d_out, sy + sgn * d_out), (x2 - d_in, y2 - sgn * d_in), (x2, y2)]
            if src == "trunk":                       # the trunk has many colours: use the receiving line's
                color, dashed = lines[ref["line"]]["color"], bool(lines[ref["line"]].get("optional"))
            else:
                color, dashed = lines[src]["color"], bool(lines[src].get("optional"))
            fid = f"feed '{st['name']}' -> '{ref['station']}'"
            feeds.append((pts, color, dashed, fid))
            for key, y in (((src, st["name"]), pts[1][1]), (tkey, pts[-2][1])):
                touching.setdefault(key, []).append(fid)
                feed_ys.setdefault(key, []).append(y)

    # ---- draw: title ----
    if spec.get("title"):
        cv.text(m, 56, spec["title"], 30, True, anchor="start")
    if spec.get("subtitle"):
        cv.text(m, 84, spec["subtitle"], 15, fill=s["muted"], anchor="start")

    # ---- draw: lines (plain side lines first, main lines, then side lines that bridge into a station) ----
    order = ([l for l in lines if lines[l]["from"] != "trunk" and not lines[l].get("_casing")]
             + list(reversed(trunk_lines))
             + [l for l in lines if lines[l].get("_casing")])
    for lid in order:
        ln = lines[lid]
        # white "bridge" casing only on side lines: on a trunk line it would also eat into its parallel neighbours
        # a branch's halo starts after its first bend, so it doesn't cut into the line it leaves
        cv.polyline(geo[lid], ln["color"], lid, dashed=bool(ln.get("optional")),
                    casing=bool(ln.get("_casing")) and ln["from"] != "trunk", casing_skip=1 if is_branch(ln) else 0)
    for pts, color, dashed, fid in feeds:   # drawn last, bridged over everything they cross
        cv.polyline(pts, color, fid, dashed=dashed, casing=True, casing_pts=trim_path(pts, 18, 18))

    # ---- draw: stations + labels ----
    def label(x, y, st, above):
        name = st["name"]
        tool = st.get("tool", "") or ""
        if st.get("optional"):
            tool = f"{tool} · optional" if tool else "optional"
        if above:
            cv.text(x, y - LABEL_OFFSET, name, 15, True, desc=f"label '{name}'")
            cv.text(x, y - LABEL_OFFSET + TOOL_OFFSET, tool, 12.5, fill=s["muted"], desc=f"label '{name}'")
        else:
            cv.text(x, y + LABEL_OFFSET + 2, name, 15, True, desc=f"label '{name}'")
            cv.text(x, y + LABEL_OFFSET + 2 + TOOL_OFFSET, tool, 12.5, fill=s["muted"], desc=f"label '{name}'")

    # Label side: explicit `label: above|below` wins; otherwise the default side, flipped when a line leaves or
    # arrives at the station on that side (so the line would cut through the label).
    trunk_above = trunk.get("labels", "below") == "above"
    for st in trunk_stations:
        x = st["_x"]
        leaving = [l for l in lines if lines[l]["from"] == st["name"]]
        above = trunk_above
        if "label" in st:
            above = st["label"] == "above"
        elif (any((row_y(lines[l]["row"]) < y0) == above for l in leaving)
              or any((y < y0) == above for y in feed_ys.get(("trunk", st["name"]), []))):
            above = not above
        cv.pill(x, trunk_top, trunk_bot, trunk_lines + leaving + touching.get(("trunk", st["name"]), []),
                desc=f"station '{st['name']}'")
        label(x, trunk_top if above else trunk_bot, st, above)

    for lid, ln in lines.items():
        for st in ln["stations"]:
            key = (lid, st["name"])
            joiners = [l for l, o in lines.items() if o.get("_joins") == key]
            leavers = [l for l, o in lines.items() if is_branch(o) and (o["from"]["line"], o["from"]["station"]) == key]
            cv.station(st["_x"], st["_y"], {lid, *joiners, *leavers, *touching.get(key, [])},
                       st.get("optional", False), desc=f"station '{st['name']}'")
            above = st["_y"] < y0 - 0.5
            if is_branch(ln):                     # a branch's labels go on the side away from its parent line
                above = ln["row"] < lines[ln["from"]["line"]]["row"]
            if "label" in st:
                above = st["label"] == "above"
            elif (any((row_y(lines[j]["row"]) < st["_y"]) == above for j in joiners + leavers)
                  or any((y < st["_y"]) == above for y in feed_ys.get(key, []))):
                above = not above
            st["_label_above"] = above
            st["_joined_above"] = any(row_y(lines[j]["row"]) < st["_y"] for j in joiners)
            st["_joined_below"] = any(row_y(lines[j]["row"]) > st["_y"] for j in joiners)
            label(st["_x"], st["_y"], st, above)

    if term:
        cv.pill(tx, ty - half, ty + half, into, w=pill_w, desc=f"station '{term['name']}'")
        cv.terminus = f"station '{term['name']}'"
        cv.text(tx + pill_w / 2 + 13, ty - 4, term["name"], 17, True, anchor="start", desc=f"label '{term['name']}'")
        cv.text(tx + pill_w / 2 + 13, ty + 15, term.get("sublabel", ""), 12.5, fill=s["muted"], anchor="start",
                desc=f"label '{term['name']}'")

    # ---- draw: input ----
    if inp:
        cv.file_icon(input_cx, y0, inp.get("file", "IN"), inp.get("color", "#57606a"), "input icon")
        up = any(l["from"] == "input" and row_y(l["row"]) < y0 for l in lines.values())
        if up:   # a side line leaves the input upwards: put the input labels underneath
            cv.text(input_cx, y0 + ICON_H / 2 + 22, inp.get("label", "Input"), 15, True, desc="input label")
            cv.text(input_cx, y0 + ICON_H / 2 + 38, inp.get("sublabel", ""), 12.5, fill=s["muted"], desc="input label")
        else:
            cv.text(input_cx, y0 - 58, inp.get("label", "Input"), 15, True, desc="input label")
            cv.text(input_cx, y0 - 42, inp.get("sublabel", ""), 12.5, fill=s["muted"], desc="input label")

    # ---- draw: output icons ----
    def output(o, sx, sy, kind, color, edge, shift=0):
        """kind: trunk | above | below | end | terminus -> default icon placement relative to the station.
        shift moves the default sideways (used when a joining line already arrives on the icon's side)."""
        dx, dy, side = {"trunk": (-75, -(sy - trunk_top) - 69, "left"),
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
        # stop the connector at the icon's edge (box half-extent along the direction)
        t_icon = min((ICON_W / 2 + 4) / abs(ux) if ux else math.inf, (ICON_H / 2 + 4) / abs(uy) if uy else math.inf)
        if dist > edge + t_icon:
            cv.connector(sx + ux * edge, sy + uy * edge, ix - ux * t_icon, iy - uy * t_icon)
        cv.file_icon(ix, iy, o.get("file", "OUT"), o.get("color", color), f"output icon '{o.get('file')}'")
        for k, part in enumerate(two_lines(o.get("label", ""))):
            if side == "left":
                cv.text(ix - ICON_W / 2 - 11, iy + 4 + 16 * k, part, 12.5, fill=s["muted"], anchor="end",
                        desc=f"output label '{o.get('label')}'")
            else:
                cv.text(ix + ICON_W / 2 + 11, iy - 4 + 16 * k, part, 12.5, fill=s["muted"], anchor="start",
                        desc=f"output label '{o.get('label')}'")

    mid_color = lines[trunk_lines[len(trunk_lines) // 2]]["color"] if trunk_lines else s["ink"]
    for st in trunk_stations:
        for o in st.get("outputs") or []:
            output(o, st["_x"], trunk_top if trunk_above is False else trunk_bot, "trunk", mid_color, 14)
    for lid, ln in lines.items():
        for i, st in enumerate(ln["stations"]):
            for o in st.get("outputs") or []:
                terminal = i == len(ln["stations"]) - 1 and ln["to"] == "none"
                # icon goes on the side opposite the label ("above" kind = station whose label is above -> icon below)
                kind = "end" if terminal else ("above" if st["_label_above"] else "below")
                # joining lines arrive from the left; if one comes in on the icon's side, move the icon right
                taken = st["_joined_below"] if kind == "above" else st["_joined_above"] if kind == "below" else False
                output(o, st["_x"], st["_y"], kind, ln["color"], s["station_radius"] + 2, shift=60 if taken else 0)
    if term:
        level_color = lines[level[0]]["color"] if level else (lines[into[0]]["color"] if into else s["ink"])
        for o in term.get("outputs") or ([{"file": term["file"]}] if term.get("file") else []):
            output(o, tx, ty, "terminus", level_color, half + pill_w / 2 + 4)

    # ---- legend + footnote ----
    width = spec.get("width") or max(cv.xmax + m, 900)
    ly = cv.ymax + 62
    cv.out.append(f'<line x1="{m}" y1="{ly - 36:.1f}" x2="{width - m:.1f}" y2="{ly - 36:.1f}" stroke="{s["rule"]}" stroke-width="1.5"/>')
    items = []
    for lid, ln in lines.items():
        name = ln.get("legend", ln["name"])
        if ln.get("optional") and "optional" not in name.lower():
            name += " (optional)"
        item = ("line", ln["color"], bool(ln.get("optional")), name)
        if item not in items:      # a branch shares its parent's legend entry
            items.append(item)
    items.append(("station", None, False, "Step"))
    if any(st.get("optional") for ln in lines.values() for st in ln["stations"]) or any(st.get("optional") for st in trunk_stations):
        items.append(("station", None, True, "Optional step"))
    lx = m
    for kind, color, opt, name in items:
        w_item = (58 if kind == "line" else 27) + text_width(name, 14) + 30
        if lx + w_item > width - m and lx > m:
            lx, ly = m, ly + 30
        if kind == "line":
            da = f' stroke-dasharray="{s["dash"]}"' if opt else ""
            cv.out.append(f'<line x1="{lx}" y1="{ly:.1f}" x2="{lx + 46}" y2="{ly:.1f}" stroke="{color}" '
                          f'stroke-width="{lw}" stroke-linecap="round"{da}/>')
            cv.text(lx + 58, ly + 5, name, 14, anchor="start", track=False)
        else:
            da = ' stroke-dasharray="4 3"' if opt else ""
            cv.out.append(f'<circle cx="{lx + 10}" cy="{ly:.1f}" r="9" fill="#ffffff" stroke="{s["ink"]}" stroke-width="3"{da}/>')
            cv.text(lx + 27, ly + 5, name, 14, anchor="start", track=False)
        lx += w_item
    fy = ly + 34
    if spec.get("footnote"):
        for line in wrap_words(spec["footnote"], int((width - 2 * m) / (12.5 * 0.53))):
            cv.text(m, fy, line, 12.5, fill=s["muted"], anchor="start", track=False)
            fy += 18
    height = spec.get("height") or fy + 12

    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.0f} {height:.0f}" '
           f'width="{width:.0f}" height="{height:.0f}">', f'<rect width="{width:.0f}" height="{height:.0f}" fill="#ffffff"/>']
    return "\n".join(svg + cv.out + ["</svg>"]), cv
