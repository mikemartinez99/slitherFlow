"""Turn a `snakemake --rulegraph` (DOT) into a starter YAML spec, from the graph's shape alone."""
import re
import sys

from .style import DEFAULT_PALETTE, PALETTES


def pretty(rule):
    words = rule.replace("-", "_").split("_")
    return " ".join([words[0].capitalize()] + words[1:]) if words else rule


def find_terminus(succ, pred):
    """The rule where the pipeline converges, read from the graph shape alone (rule names are ignored).

    Candidates are sink rules (nothing downstream except `all`) that collect from two or more rules. The one with
    the most direct inputs wins (the most lines end there); ties go to the one with the most upstream rules, then
    to the earlier rule in the rule graph. Returns None if no sink merges branches."""
    def ancestors(i):
        seen, stack = set(), list(pred[i])
        while stack:
            j = stack.pop()
            if j not in seen:
                seen.add(j)
                stack.extend(pred[j])
        return seen

    sinks = [i for i in succ if not succ[i] and len(pred[i]) >= 2]
    if not sinks:
        return None
    order = {i: k for k, i in enumerate(succ)}
    return max(sinks, key=lambda i: (len(pred[i]), len(ancestors(i)), -order[i]))


def drop_loops(succ, pred):
    """Remove the connections that close a loop, so the rest of the graph can be laid out left to right.

    A rule graph can loop even though Snakemake's job graph can't: a rule whose job for one wildcard value reads
    the output of the same rule for another value (warm starts, parent and child scenarios) shows up as
    `run -> run`, or as `run -> scenario -> run` through other rules. Walking forward from the source rules,
    a connection back to a rule that is still on the path being walked closes a loop and is dropped. Loops no
    source leads to (e.g. two rules that only feed each other, when `--scan` can't see what else feeds them) are
    then walked from their first rule in the graph. Returns the dropped (from, to) pairs."""
    dropped = []
    state = {}                                          # 1 = on the current path, 2 = done
    for src in [i for i in succ if not pred[i]] + list(succ):
        if src in state:
            continue
        state[src] = 1
        stack = [(src, iter(list(succ[src])))]
        while stack:
            i, children = stack[-1]
            j = next(children, None)
            if j is None:
                state[i] = 2
                stack.pop()
            elif state.get(j) == 1:
                dropped.append((i, j))
            elif j not in state:
                state[j] = 1
                stack.append((j, iter(list(succ[j]))))
    for a, b in dropped:
        succ[a].remove(b)
        pred[b].remove(a)
    return dropped


def spec_from_rulegraph(dot_text, title="My pipeline", palette=DEFAULT_PALETTE):
    """A starter spec (YAML text) from a rule graph in `snakemake --rulegraph` (DOT) form.

    Lines and stations are marked optional only when the graph says so: `--scan` adds `optional = true` to the
    rules it finds defined under an `if` (or in a file only included under one). A plain `snakemake --rulegraph`
    only holds rules the current config runs, so nothing in it is marked optional."""
    names, edges, conditional = {}, [], set()
    for line in dot_text.splitlines():
        m = re.match(r'\s*(\d+)\s*\[\s*label\s*=\s*"([^"]+)"(.*)', line)
        if m:
            names[m.group(1)] = m.group(2)
            if re.search(r'\boptional\s*=\s*"?true\b', m.group(3)):
                conditional.add(m.group(1))
            continue
        m = re.match(r"\s*(\d+)\s*->\s*(\d+)", line)
        if m:
            edges.append((m.group(1), m.group(2)))
    if not names:
        sys.exit("no rules found: is this the output of `snakemake --rulegraph`?")
    rules = {i: n for i, n in names.items() if n != "all"}
    succ = {i: [] for i in rules}
    pred = {i: [] for i in rules}
    loops = []
    for a, b in edges:
        if a == b and a in rules:
            if (a, b) not in loops:
                loops.append((a, b))            # a rule feeding itself (for another wildcard value)
        elif a in rules and b in rules and b not in succ[a]:
            succ[a].append(b)
            pred[b].append(a)
    loops += drop_loops(succ, pred)
    term = find_terminus(succ, pred)
    feeds_term = set(pred[term]) if term else set()
    nodes = [i for i in rules if i != term]
    S = {i: [j for j in succ[i] if j != term] for i in nodes}
    P = {i: [j for j in pred[i] if j != term] for i in nodes}

    def descendants(i, seen=None):
        seen = set() if seen is None else seen
        for j in S[i]:
            if j not in seen:
                seen.add(j)
                descendants(j, seen)
        return seen

    memo = {}

    def longest_path(i):
        if i not in memo:
            memo[i] = [i] + max((longest_path(j) for j in S[i]), key=len, default=[])
        return memo[i]

    # topological order, and each rule's depth (longest path from a source): a rough stand-in for its x position
    order, indeg = [], {i: len(P[i]) for i in nodes}
    ready = [i for i in nodes if not indeg[i]]
    while ready:
        i = ready.pop(0)
        order.append(i)
        for j in S[i]:
            indeg[j] -= 1
            if not indeg[j]:
                ready.append(j)
    depth = {}
    for i in order:
        depth[i] = max((depth[j] + 1 for j in P[i]), default=0)

    sources = [i for i in nodes if not P[i]]
    if not sources:
        sys.exit("the rule graph has no source rule")
    main = max(sources, key=lambda i: len(descendants(i)))
    # trunk: follow the longest path while the next rule has a single input; stop after a hub (3+ successors)
    trunk, path = [], longest_path(main)
    for k, i in enumerate(path):
        trunk.append(i)
        nxt = path[k + 1] if k + 1 < len(path) else None
        if nxt is None or len(S[i]) >= 3 or len(P[nxt]) != 1:
            break
    # If the trunk reached the end of the pipeline (nothing left to leave its last station), there would be no
    # lines to draw along it: cut it back to the last rule that splits, or to the first rule if none does.
    if len(trunk) > 1 and not [j for j in S[trunk[-1]] if j not in trunk]:
        splits = [k for k, i in enumerate(trunk[:-1]) if len(S[i]) >= 2]
        trunk = trunk[:splits[-1] + 1] if splits else trunk[:1]
    assigned = {i: ("trunk", None) for i in trunk}

    def chain(start):
        """Rules for one line: follow the longest path; rules it passes by become branches later."""
        c, i = [], start
        while i is not None and i not in assigned:
            c.append(i)
            assigned[i] = None
            nxt = [j for j in S[i] if j not in assigned]
            i = max(nxt, key=lambda j: len(longest_path(j))) if nxt else None
        return c

    def tail_target(c, lid):
        last = c[-1]
        if last in feeds_term:
            return "terminus"
        for j in S[last]:
            if assigned.get(j) and assigned[j][0] != "trunk" and assigned[j][0] != lid:
                return {"line": assigned[j][0], "station": pretty(rules[j])}
        return "none"

    lines, row_cycle = {}, [-1, 1, 0, -2, 2, -3, 3]
    hub = trunk[-1]
    for k, j in enumerate(S[hub]):
        if j in assigned:
            continue
        c = chain(j)
        lid = f"line{len(lines) + 1}"
        for i in c:
            assigned[i] = (lid, None)
        lines[lid] = {"name": pretty(rules[c[0]]), "row": row_cycle[len(lines) % len(row_cycle)], "_chain": c,
                      "_start": depth[hub], "_origin": hub}
    for t in trunk[:-1]:
        for j in S[t]:
            if j in assigned:
                continue
            c = chain(j)
            lid = f"side{len(lines) + 1}"
            for i in c:
                assigned[i] = (lid, None)
            lines[lid] = {"name": pretty(rules[c[0]]), "from": pretty(rules[t]), "_chain": c,
                          "_start": depth[t], "_origin": t}
    for src in sources:
        if src in assigned:
            continue
        c = chain(src)
        lid = f"side{len(lines) + 1}"
        for i in c:
            assigned[i] = (lid, None)
        lines[lid] = {"name": pretty(rules[c[0]]), "from": "input", "_chain": c, "_start": -1, "_origin": None}
    # every rule still unplaced branches off the station of its latest placed input
    for j in order:
        if j in assigned:
            continue
        p = max((p for p in P[j] if assigned.get(p)), key=lambda p: depth[p], default=None)
        if p is None:
            continue
        c = chain(j)
        lid = f"branch{len(lines) + 1}"
        for i in c:
            assigned[i] = (lid, None)
        par = assigned[p][0]
        frm = pretty(rules[p]) if par == "trunk" else {"line": par, "station": pretty(rules[p])}
        lines[lid] = {"name": pretty(rules[c[0]]), "from": frm, "_chain": c, "_start": depth[p], "_origin": p}
    # Only a line whose last rule feeds the terminus is drawn into it. If none does (every terminus input sits
    # partway along a line that carries on), the terminus would be drawn with nothing going in: cut the line with
    # the most terminus inputs after its last one, and the rest of it becomes a branch leaving that station.
    if term and not any(ln["_chain"][-1] in feeds_term for ln in lines.values()):
        fed = [(sum(i in feeds_term for i in ln["_chain"]), lid) for lid, ln in lines.items()]
        n, cut_lid = max(fed, key=lambda f: f[0], default=(0, None))
        if n:
            ln = lines[cut_lid]
            k = max(k for k, i in enumerate(ln["_chain"]) if i in feeds_term)
            stop, rest = ln["_chain"][k], ln["_chain"][k + 1:]
            ln["_chain"] = ln["_chain"][:k + 1]
            lid = f"branch{len(lines) + 1}"
            for i in rest:
                assigned[i] = (lid, None)
            par = assigned[stop][0]
            lines[lid] = {"name": pretty(rules[rest[0]]), "from": {"line": par, "station": pretty(rules[stop])},
                          "_chain": rest, "_start": depth[stop], "_origin": stop}
    end_depth = max(depth.values(), default=0) + 1
    for lid, ln in lines.items():
        ln["to"] = to = tail_target(ln["_chain"], lid)
        end = max(depth[i] for i in ln["_chain"])
        if to == "terminus":
            end = end_depth
        elif isinstance(to, dict):
            end = max([end] + [depth[j] for j in S[ln["_chain"][-1]] if assigned[j][0] == to["line"]])
        ln["_end"] = end
    # connections the lines already show; every other one (except inputs to the terminus) becomes a `feeds:`
    drawn = set(zip(trunk, trunk[1:]))
    for ln in lines.values():
        c = ln["_chain"]
        drawn |= set(zip(c, c[1:]))
        if ln["_origin"] is not None:
            drawn.add((ln["_origin"], c[0]))
        to = ln["to"]
        if isinstance(to, dict):
            drawn |= {(c[-1], j) for j in S[c[-1]] if assigned.get(j) and assigned[j][0] == to["line"]
                      and pretty(rules[j]) == to["station"]}
    feeds = {i: [j for j in S[i] if (i, j) not in drawn and assigned.get(j) and assigned[j][0] != "trunk"]
             for i in nodes if i in assigned}
    # side-line rows: just outside the line they join; otherwise outside all main lines on the side of the lines
    # they feed, or alternating above and below
    main_rows = [ln["row"] for ln in lines.values() if "from" not in ln] or [0]
    used = set(main_rows)
    outside = max(abs(r) for r in main_rows) + 0.6
    flip = -1
    for lid, ln in lines.items():
        if "from" not in ln or isinstance(ln["from"], dict):
            continue
        to = ln["to"]
        if isinstance(to, dict) and "row" in lines.get(to["line"], {}):
            base = lines[to["line"]]["row"]
            direction = 1 if base >= 0 else -1
            row = base + 0.6 * direction
        else:
            fed = [lines[assigned[j][0]]["row"] for i in ln["_chain"] for j in feeds.get(i, [])
                   if "row" in lines[assigned[j][0]]]
            if fed:
                direction = 1 if sum(fed) >= 0 else -1
            elif ln["from"] == "input":
                direction = 1
            else:
                direction, flip = flip, -flip
            row = outside * direction
        while round(row, 1) in used:
            row += 0.5 * direction
        ln["row"] = round(row, 1)
        used.add(ln["row"])
    # branch rows: the nearest row next to the parent line (outwards first) that keeps 0.6 rows clear of every
    # line covering the same stretch of the pipeline (stretch = rule depth, a stand-in for x)
    def joins(ln):
        to = ln.get("to")
        return (to["line"], to["station"]) if isinstance(to, dict) else None
    occupied = [(0, -1, depth[hub], None)] + [(ln["row"], ln["_start"], ln["_end"], joins(ln))
                                              for ln in lines.values() if "row" in ln]
    flip = 1
    # (line, station) -> side its branches take: the side a line joins it from, else the side its first branch took
    sides = {}
    for ln in lines.values():
        if joins(ln) and "row" in ln and "row" in lines.get(ln["to"]["line"], {}):
            sides.setdefault(joins(ln), 1 if ln["row"] > lines[ln["to"]["line"]]["row"] else -1)
    for lid, ln in lines.items():
        if not isinstance(ln.get("from"), dict):
            continue
        pr, a, b = lines[ln["from"]["line"]]["row"], ln["_start"], ln["_end"]
        src = (ln["from"]["line"], ln["from"]["station"])
        if src in sides:                      # branches leaving the same station go to the same side, so its
            out_dir = sides[src]              # label keeps one side free
        elif pr:
            out_dir = 1 if pr > 0 else -1
        else:
            out_dir, flip = flip, -flip
        def clear(r):
            for q, a2, b2, j in occupied:
                if a < b2 and a2 < b and abs(r - q) < 0.59:        # share a stretch: keep 0.6 rows apart
                    return False
                if a <= b2 and a2 <= b and abs(r - q) < 0.01 and j != src:   # one ends where the other starts
                    return False                                 # (fine if it joins the station this one leaves)
            return True
        same_side = [round(pr + out_dir * 0.6 * k, 1) for k in range(1, 4)] if src in sides else []
        ln["row"] = next(r for r in same_side + [r for k in range(1, 100) for r in (round(pr + out_dir * 0.6 * k, 1),
                                                                                   round(pr - out_dir * 0.6 * k, 1))]
                         if clear(r))
        occupied.append((ln["row"], a, b, joins(ln)))
        sides.setdefault(src, 1 if ln["row"] > pr else -1)
    unplaced = [rules[i] for i in nodes if i not in assigned]
    # a line is optional when every rule on it is; other optional rules become optional stations
    for ln in lines.values():
        ln["optional"] = all(i in conditional for i in ln["_chain"])

    # ---- write YAML with comments ----
    q = lambda v: '"' + str(v).replace('"', '\\"') + '"'
    out = ["# Starter slitherFlow spec generated from `snakemake --rulegraph`.",
           "# Rename stations, add tools/outputs, regroup lines and tune rows, then render with:",
           "#   slitherflow render this.yaml -o map.svg --png --pdf",
           "",
           f'title: {q(title)}',
           'subtitle: "v1.0  ·  Snakemake"',
           f"palette: {palette}" + " " * max(1, 22 - len(palette))
           + f"# line colours: {', '.join(PALETTES)}, or a list of colours",
           'input: {label: "Input", sublabel: "", file: "IN"}   # file: text on the input icon, e.g. "FASTQ", "CSV", "NC"',
           "",
           "trunk:                      # steps every run goes through",
           "  stations:"]
    ref = lambda v: q(v) if isinstance(v, str) else "{line: " + v["line"] + ", station: " + q(v["station"]) + "}"

    def station(i, on_optional_line=False):
        extra = ", optional: true" if i in conditional and not on_optional_line else ""
        if feeds.get(i):
            extra = ", feeds: [" + ", ".join(ref({"line": assigned[j][0], "station": pretty(rules[j])})
                                             for j in feeds[i]) + "]"
        return f"{{name: {q(pretty(rules[i]))}, tool: \"\"{extra}}}"

    out += [f"    - {station(i)}" for i in trunk]
    trunk_ids = sorted((l for l, v in lines.items() if "from" not in v), key=lambda l: lines[l]["row"])
    out += ["  lines: [" + ", ".join(trunk_ids) + "]   # top -> bottom on the trunk",
            "", "lines:" if lines else "lines: {}"]
    for lid, ln in lines.items():
        branch = isinstance(ln.get("from"), dict)
        if branch:   # no name: it shares its parent's colour and legend entry
            out.append(f"  {lid}:                    # branch of {ln['from']['line']} (same colour and legend entry)")
        else:
            out.append(f"  {lid}:")
            out.append(f"    name: {q(ln['name'])}")
        if "from" in ln:
            out.append(f"    from: {ref(ln['from'])}")
        out.append(f"    row: {ln['row']}" + ("            # negative = above the trunk" if ln['row'] < 0 else ""))
        parent_optional = branch and lines[ln["from"]["line"]]["optional"]
        if ln["optional"] and not parent_optional:
            out.append("    optional: true         # dashed: these steps only run for some configs")
        elif not ln["optional"] and parent_optional:
            out.append("    optional: false        # its parent line is optional, but these steps always run")
        elif not ln["optional"] and "from" in ln and not branch:
            out.append("    # optional: true       # uncomment to draw it dashed, if these steps only run for some configs")
        out.append(f"    to: {ref(ln['to'])}")
        out.append("    stations:")
        out += [f"      - {station(i, ln['optional'])}" for i in ln["_chain"]]
    if term:
        feeding = [ln["row"] for ln in lines.values() if ln["to"] == "terminus" and "from" not in ln]
        trow = min(feeding, key=abs) if feeding else 0
        out += ["", f"# terminus: rule '{rules[term]}', the end rule that collects from the most rules "
                    f"({len(pred[term])} inputs)",
                f'terminus: {{name: {q(pretty(rules[term]))}, sublabel: "", row: {trow}}}'
                '   # add file: "<type>" for an output icon']
    out += ["", 'footnote: ""']
    if unplaced:
        out += ["", "# Rules not placed automatically (add them to a line by hand):"] + [f"#   - {r}" for r in unplaced]
    if loops:
        out += ["", "# Connections left out because they loop back (a rule feeding itself or an earlier rule,"
                    " for another", "# wildcard value):"]
        out += [f"#   - {rules[a]} -> {rules[b]}" for a, b in loops]
    return "\n".join(out) + "\n"
