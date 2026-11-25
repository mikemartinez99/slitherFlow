"""Build a rule graph by reading a project's Snakefile and .smk files, without running Snakemake.

`snakemake --rulegraph` only shows the rules the current config switches on: a rule in a file that is included
conditionally, or one that only some settings ask for, is missing from it. Reading the files instead finds every
rule, whatever the config. The price is that file paths have to be worked out without running any code:

- every `rule` / `checkpoint` block in every Snakefile and .smk file under the project is read, including ones
  inside `if` blocks;
- `input:` and `output:` are parsed as Python, and each value is reduced to the path patterns it could produce.
  Variables (all of their assignments, on every branch, and `+=`), `expand()`, f-strings, `temp()`-style
  wrappers, `multiext()`, `os.path.join()`, simple helper functions (`def f(): return f"..."`) and
  `rules.<name>.output` / `rules.<name>.input` references are followed. Anything that depends on the config or
  the sample sheet becomes "could be anything", like a wildcard;
- an input is joined to every rule whose output (or log / benchmark file) pattern could name the same file.
  Like most Snakemake workflows, wildcards are assumed not to span folders ({sample} never contains a /).

It is a best effort: input functions that build paths from data, Snakemake modules (`use rule ... from`) and
paths assembled in other ways can't be followed, so a connection may be missing (or, rarely, extra).

Rules that only exist for some configs are marked `optional = true` in the graph (and drawn dashed): a rule
defined inside an `if` / `elif` / `else` block, or in a file that is only included inside one. A rule defined on
both the `if` and the `else` side of the same test exists either way, so it is not marked. Rules that always
exist but that `rule all` only asks for under some settings are not marked either.
"""
import ast
import itertools
import re
import string
import sys
import textwrap
from pathlib import Path

ANY = "\x00"                     # stands for any text we can't work out (config values, sample sheet lookups)
MAX_VALUES = 64                  # cap on the patterns one expression can expand to
SKIP_DIRS = {".snakemake", ".git", "test", "tests", ".test", ".tests", "__pycache__", "node_modules"}

DIRECTIVES = {
    "input", "output", "params", "log", "benchmark", "threads", "resources", "priority", "version", "message",
    "shell", "run", "script", "notebook", "wrapper", "cwl", "conda", "container", "singularity", "envmodules",
    "shadow", "group", "wildcard_constraints", "cache", "handover", "default_target", "localrule", "retries",
    "name", "template_engine", "pathvars",
}
# functions that wrap a path without changing which file it names
PASS_THROUGH = {"expand", "directory", "temp", "temporary", "protected", "ancient", "touch", "pipe", "service",
                "ensure", "report", "local", "unpack", "str", "storage", "update", "before_update", "lookup"}

RULE_RE = re.compile(r"^(\s*)(rule|checkpoint)\s+([A-Za-z_]\w*)\s*:")
DEF_RE = re.compile(r"^(\s*)def\s+([A-Za-z_]\w*)\s*\(")
ASSIGN_RE = re.compile(r"^\s*([A-Za-z_]\w*)\s*(\+=|=)(?!=)\s*(.*)$")
INCLUDE_RE = re.compile(r"""^\s*include\s*:\s*(['"])(.+?)\1""")
DIRECTIVE_RE = re.compile(r"^(\s+)([A-Za-z_]\w*)\s*:(.*)$")
IF_RE = re.compile(r"^(\s*)(if|elif|else)\b")
APPEND_RE = re.compile(r"^\s*([A-Za-z_]\w*)\.(append|extend)\s*\(")


def snakemake_files(project):
    """The project's Snakefiles and .smk files: the main Snakefile first, then included files in the order they
    are included, then any others (sorted). Hidden folders, .snakemake and test folders are skipped."""
    project = Path(project)
    found = sorted(p for p in project.rglob("*")
                   if p.is_file() and (p.name == "Snakefile" or p.suffix == ".smk")
                   and not any(part in SKIP_DIRS or part.startswith(".")
                               for part in p.relative_to(project).parts[:-1]))
    mains = [p for p in (project / "Snakefile", project / "workflow" / "Snakefile") if p in found]
    ordered = []

    def visit(path):
        if path in ordered or path not in found:
            return
        ordered.append(path)
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            m = INCLUDE_RE.match(line)
            if m:
                visit((path.parent / m.group(2)).resolve())

    found = [p.resolve() for p in found]
    for m in mains:
        visit(m.resolve())
    return ordered + [p for p in found if p not in ordered]


def block(lines, start, indent):
    """Index just past the block that starts at lines[start] (lines indented deeper than `indent`)."""
    i = start + 1
    while i < len(lines):
        line = lines[i]
        if line.strip() and len(line) - len(line.lstrip()) <= indent:
            break
        i += 1
    return i


def parse_expr(text):
    """A directive's value (e.g. `"a", b="c"`) as an ast.Call whose arguments are the values, or None."""
    try:
        return ast.parse(f"_(\n{text}\n)", mode="eval").body
    except SyntaxError:
        return None


class Project:
    """Everything read from the files: rules (name -> inputs/outputs), variables and helper functions."""

    def __init__(self, files):
        self.rules = {}          # name -> {"input": [ast], "output": [ast], "order": n, "defs": [...]}
        self.variables = {}      # name -> [ast expressions assigned to it, anywhere]
        self.functions = {}      # name -> [ast.FunctionDef] (a helper may be defined in more than one file)
        self.includes = []       # (including file, included file, inside an if block?)
        self.n_tests = 0         # each if / elif / else chain gets its own number
        for path in files:
            self.read(path.read_text(encoding="utf-8", errors="replace").splitlines(), Path(path).resolve())
        self.memo = {}

    def read(self, lines, path=None):
        i = 0
        tests = []               # the if / elif / else blocks the current line is inside: (indent, test number, kind)
        while i < len(lines):
            line = lines[i]
            if line.strip() and not line.lstrip().startswith("#"):
                indent = len(line) - len(line.lstrip())
                closed = None
                while tests and tests[-1][0] >= indent:
                    closed = tests.pop()
                m = IF_RE.match(line)
                if m:
                    kind = m.group(2)
                    if kind != "if" and closed and closed[0] == indent:    # elif / else: same test as the if
                        tests.append((indent, closed[1], kind))
                    else:
                        self.n_tests += 1
                        tests.append((indent, self.n_tests, kind))
                    i += 1
                    continue
            m = INCLUDE_RE.match(line)
            if m and path is not None:
                self.includes.append((path, (path.parent / m.group(2)).resolve(), bool(tests)))
            m = RULE_RE.match(line)
            if m:
                end = block(lines, i, len(m.group(1)))
                self.read_rule(m.group(3), lines[i:end])
                where = (tests[-1][1], tests[-1][2]) if tests else None
                self.rules[m.group(3)]["defs"].append((path, where))
                i = end
                continue
            m = DEF_RE.match(line)
            if m:
                end = block(lines, i, len(m.group(1)))
                try:
                    fn = ast.parse(textwrap.dedent("\n".join(lines[i:end]))).body[0]
                    self.functions.setdefault(m.group(2), []).append(fn)
                except (SyntaxError, IndexError):
                    pass
                i = end
                continue
            m = APPEND_RE.match(line)
            if m:                                         # TARGETS.append(x) / .extend(xs): like TARGETS += [x]
                text, j, call = line.strip(), i, None
                while j < len(lines) and j - i < 40:
                    try:
                        call = ast.parse(text, mode="eval").body
                        break
                    except SyntaxError:
                        j += 1
                        if j < len(lines):
                            text += "\n" + lines[j]
                if isinstance(call, ast.Call):
                    self.variables.setdefault(m.group(1), []).extend(call.args)
                    i = j + 1
                    continue
            m = ASSIGN_RE.match(line)
            if m:
                text, j = m.group(3), i
                expr = None
                while j < len(lines) and j - i < 40:      # a value may continue over several lines
                    try:
                        expr = ast.parse(text.strip() or "None", mode="eval").body
                        break
                    except SyntaxError:
                        j += 1
                        if j < len(lines):
                            text += "\n" + lines[j]
                if expr is not None:
                    self.variables.setdefault(m.group(1), []).append(expr)
                    i = j + 1
                    continue
            i += 1

    def read_rule(self, name, lines):
        rule = self.rules.setdefault(name, {"input": [], "output": [], "order": len(self.rules), "defs": []})
        # Snakemake connects rules through log and benchmark files too, so they count as outputs here
        body_indent = None
        i = 1
        while i < len(lines):
            m = DIRECTIVE_RE.match(lines[i])
            indent = len(m.group(1)) if m else None
            if m and m.group(2) in DIRECTIVES and (body_indent is None or indent == body_indent):
                body_indent = indent
                end = block(lines, i, indent)
                kind = {"input": "input", "output": "output", "log": "output", "benchmark": "output"}.get(m.group(2))
                if kind:
                    call = parse_expr("\n".join([m.group(3)] + lines[i + 1:end]))
                    if call is not None:
                        rule[kind] += list(call.args) + [k.value for k in call.keywords]
                i = end
                continue
            i += 1

    def conditional_rules(self):
        """Rules that only exist for some configs: each definition sits inside an if / elif / else block, or in a
        file that is only included inside one. A rule defined on both the if and the else side of one test (in
        a file that is always read) exists either way, so it is left out."""
        included = {dst for _, dst, _ in self.includes}
        files = {p for r in self.rules.values() for p, _ in r["defs"]} | {src for src, _, _ in self.includes}
        always = {f for f in files if f not in included} | {None}    # main Snakefiles, and files nothing includes
        todo = list(always)
        while todo:                                                   # ... and what they include outside an if
            a = todo.pop()
            for src, dst, cond in self.includes:
                if src == a and not cond and dst not in always:
                    always.add(dst)
                    todo.append(dst)
        out = set()
        for name, rule in self.rules.items():
            defs = [(where, path in always) for path, where in rule["defs"]]
            if not defs or any(where is None and read for where, read in defs):
                continue
            sides = {}
            for where, read in defs:
                if where is not None and read:
                    sides.setdefault(where[0], set()).add(where[1])
            if any({"if", "else"} <= kinds for kinds in sides.values()):
                continue
            out.add(name)
        return out

    # ---- what can an expression evaluate to? -------------------------------------------------------------------
    # A set of path patterns (strings; ANY marks unknown text) and rule references (("rule", name) tuples).
    def values(self, node, env=None, stack=()):
        env = env or {}
        v = self._values(node, env, stack)
        return set(itertools.islice(v, MAX_VALUES))

    def _values(self, node, env, stack):
        if isinstance(node, ast.Constant):
            return {node.value} if isinstance(node.value, str) else set()
        if isinstance(node, ast.JoinedStr):
            parts = []
            for piece in node.values:
                if isinstance(piece, ast.Constant):
                    parts.append({str(piece.value)})
                else:
                    strs = {s for s in self.values(piece.value, env, stack) if isinstance(s, str)}
                    parts.append(strs or {ANY})
            return {"".join(p) for p in itertools.islice(itertools.product(*parts), MAX_VALUES)}
        if isinstance(node, ast.Name):
            if node.id in env:
                return env[node.id]
            if node.id in stack:
                return set()
            if node.id not in self.variables and node.id in self.functions:   # `input: get_input` (an input
                return self.call_function(node.id, [], [], env, stack)          # function passed by name)
            if node.id not in self.memo:
                out = set()
                for expr in self.variables.get(node.id, []):
                    out |= self.values(expr, {}, stack + (node.id,))
                self.memo[node.id] = out
            return self.memo[node.id]
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            return set().union(*(self.values(e, env, stack) for e in node.elts)) if node.elts else set()
        if isinstance(node, ast.Starred):
            return self.values(node.value, env, stack)
        if isinstance(node, ast.Dict):
            return set().union(*(self.values(v, env, stack) for v in node.values)) if node.values else set()
        if isinstance(node, ast.IfExp):
            return self.values(node.body, env, stack) | self.values(node.orelse, env, stack)
        if isinstance(node, ast.BoolOp):
            return set().union(*(self.values(v, env, stack) for v in node.values))
        if isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp)):
            return self.values(node.elt, env, stack)
        if isinstance(node, ast.Lambda):
            return self.values(node.body, env, stack)
        if isinstance(node, ast.BinOp):
            left, right = self.values(node.left, env, stack), self.values(node.right, env, stack)
            if isinstance(node.op, ast.Mod):
                return left
            if isinstance(node.op, ast.Add):
                listy = (ast.List, ast.Tuple, ast.ListComp)
                if isinstance(node.left, listy) or isinstance(node.right, listy) or not (left and right):
                    return left | right
                strs = lambda s: {x for x in s if isinstance(x, str)}
                return {a + b for a, b in itertools.islice(itertools.product(strs(left), strs(right)), MAX_VALUES)}
            return set()
        if isinstance(node, (ast.Attribute, ast.Subscript, ast.Call)):
            ref = rule_reference(node)
            if ref:
                return {("rule", ref)}
            ref = rule_input_reference(node)
            if ref:                                   # rules.x.input: whatever rule x reads
                key = ("rules", ref, "input")
                if ref not in self.rules or key in stack:
                    return set()
                return set().union(*(self.values(e, {}, stack + (key,)) for e in self.rules[ref]["input"]))
        if isinstance(node, ast.Subscript):
            return self.values(node.value, env, stack)
        if isinstance(node, ast.Call):
            return self.call(node, env, stack)
        return set()

    def call(self, node, env, stack):
        func = node.func
        name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else None
        args = [self.values(a, env, stack) for a in node.args]
        if name == "expand" and args:
            return self.expand(args[0], node.keywords, env, stack)
        if name in PASS_THROUGH:
            return args[0] if args else set()
        if name == "format" and isinstance(func, ast.Attribute):      # "x/{sample}.bam".format(sample=s): the
            return self.values(func.value, env, stack)                  # pattern still names the same files
        if name == "multiext" and args:
            exts = set().union(*args[1:]) if len(args) > 1 else {""}
            return {p + e for p in args[0] if isinstance(p, str) for e in exts if isinstance(e, str)}
        if name == "join" and isinstance(func, ast.Attribute) and args:        # os.path.join(a, b, ...)
            strs = [{s for s in a if isinstance(s, str)} or {ANY} for a in args]
            return {"/".join(p) for p in itertools.islice(itertools.product(*strs), MAX_VALUES)}
        if name in self.functions and name not in stack:
            return self.call_function(name, args, node.keywords, env, stack)
        return set().union(*args) if args else set()                  # unknown function: whatever went into it

    def expand(self, patterns, keywords, env, stack):
        """expand("model/{name}.parquet", name=["nodes", "edges"]): fill in every combination of the keyword
        values we can work out (as `product` does; `zip` gives a subset of these). A keyword we can't work out
        (config, sample sheet), or a {field} with no keyword, stays a wildcard; {{x}} becomes the wildcard {x}."""
        fill = {}
        for kw in keywords:
            if kw.arg is None or kw.arg == "allow_missing":
                continue
            vals = {v for v in self.values(kw.value, env, stack) if isinstance(v, str)}
            if vals:
                fill[kw.arg] = sorted(vals)
        out = set()
        for pattern in patterns:
            if not isinstance(pattern, str):
                out.add(pattern)                      # a rule reference: keep it as it is
                continue
            try:
                parts = list(string.Formatter().parse(pattern))
            except ValueError:                        # not a format string we can read: keep the pattern
                out.add(pattern)
                continue
            fields = sorted({f for _, f, _, _ in parts if f in fill})
            for combo in itertools.islice(itertools.product(*(fill[f] for f in fields)), MAX_VALUES):
                values = dict(zip(fields, combo))
                text = ""
                for literal, field, spec, conv in parts:
                    text += literal                   # Formatter has already turned {{ }} into { }
                    if field is None:
                        continue
                    if field not in values:
                        text += "{" + field + "}"     # no value we know: stays a wildcard
                        continue
                    try:
                        text += format(values[field], spec or "")
                    except ValueError:
                        text += values[field]
                out.add(text)
        return set(itertools.islice(out, MAX_VALUES))

    def call_function(self, name, args, keywords, env, stack):
        """What a helper function defined in the project could return, given what its arguments could be
        (arguments we don't know become ANY)."""
        out = set()
        for fn in self.functions[name]:
            params = [a.arg for a in fn.args.args]
            defaults = dict(zip(params[len(params) - len(fn.args.defaults):], fn.args.defaults))
            local = {}
            for k, p in enumerate(params):
                if k < len(args):
                    local[p] = args[k] or {ANY}
                elif p in defaults:
                    local[p] = self.values(defaults[p], env, stack) or {ANY}
                else:
                    local[p] = {ANY}
            for kw in keywords:
                if kw.arg in params:
                    local[kw.arg] = self.values(kw.value, env, stack) or {ANY}
            # local variables: every value assigned to them (`x = ...`, `x += ...`, `x["key"] = ...`,
            # `x.append(...)`, `x.extend(...)`); twice over, so a variable built from another one picks up its values
            assigned = {}
            for sub in ast.walk(fn):
                if (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute)
                        and sub.func.attr in ("append", "extend") and isinstance(sub.func.value, ast.Name)
                        and sub.func.value.id not in params):
                    assigned.setdefault(sub.func.value.id, []).extend(sub.args)
                if isinstance(sub, (ast.Assign, ast.AugAssign)):
                    for t in (sub.targets if isinstance(sub, ast.Assign) else [sub.target]):
                        t = t.value if isinstance(t, ast.Subscript) else t
                        if isinstance(t, ast.Name) and t.id not in params:
                            assigned.setdefault(t.id, []).append(sub.value)
            for _ in range(2):
                for var, exprs in assigned.items():
                    local[var] = set().union(*(self.values(e, local, stack + (name,)) for e in exprs)) or {ANY}
            for sub in ast.walk(fn):
                if isinstance(sub, ast.Return) and sub.value is not None:
                    out |= self.values(sub.value, local, stack + (name,))
        return out


def rule_reference(node):
    """'x' for rules.x.output..., checkpoints.x.get(...).output..., else None."""
    parts = reference_parts(node)
    if parts and len(parts) >= 3 and parts[0] in ("rules", "checkpoints") and "output" in parts[2:]:
        return parts[1]
    return None


def rule_input_reference(node):
    """'x' for rules.x.input... (a target rule that gathers another rule's inputs, e.g. `rule all: input:
    rules.figures.input`), else None."""
    parts = reference_parts(node)
    if parts and len(parts) >= 3 and parts[0] == "rules" and parts[2] == "input":
        return parts[1]
    return None


def reference_parts(node):
    """['rules', 'x', 'output', ...] for an attribute chain like rules.x.output[0] or rules.x.output.y, else None."""
    parts = []
    while True:
        if isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        elif isinstance(node, ast.Subscript):
            node = node.value
        elif isinstance(node, ast.Call):
            node = node.func
        elif isinstance(node, ast.Name):
            parts.append(node.id)
            break
        else:
            return None
    parts.reverse()
    return parts


WILDCARD = re.compile(r"\{[^{}]*(\{[^{}]*\}[^{}]*)*\}")      # {sample} or {sample,[a-z]{2}}


def tokens(pattern):
    """A path pattern as a tuple of literal characters, with None for each wildcard / unknown stretch."""
    out = []
    for piece in re.split(f"({WILDCARD.pattern}|{ANY}+)", pattern):
        if piece is None or piece == "":
            continue
        if piece.startswith("{") or piece.startswith(ANY):
            if not out or out[-1] is not None:
                out.append(None)
        else:
            out.extend(piece)
    return tuple(out)


def literal_length(toks):
    return sum(1 for t in toks if t is not None)


def can_match_same_file(p, q):
    """Is there a file name that both patterns match? (None = any text, as in a glob's *)."""
    n, m = len(p), len(q)
    memo = {}

    def go(i, j):
        if (i, j) in memo:
            return memo[i, j]
        if i == n and j == m:
            r = True
        elif i < n and p[i] is None:          # a wildcard takes nothing more, or one more character (not a /)
            r = go(i + 1, j) or (j < m and q[j] != "/" and go(i, j + 1))
        elif j < m and q[j] is None:
            r = go(i, j + 1) or (i < n and p[i] != "/" and go(i + 1, j))
        else:
            r = i < n and j < m and p[i] == q[j] and go(i + 1, j + 1)
        memo[i, j] = r
        return r

    limit = sys.getrecursionlimit()
    sys.setrecursionlimit(max(limit, (n + m) * 2 + 100))
    try:
        return go(0, 0)
    finally:
        sys.setrecursionlimit(limit)


def mark_not_run(scan_dot, run_dot):
    """`--scan --compare`: mark every rule in the scanned graph that `snakemake --rulegraph` (run_dot, for the
    current config) leaves out as `optional = true`. Returns (new DOT text, names of the rules newly marked).

    This catches rules that are always defined but only asked for under some settings, which reading the files
    can't see: `expand(...) if <setting> else []` in `rule all`, or an input function that adds a file only for
    some settings."""
    run = set(re.findall(r'\[\s*label\s*=\s*"([^"]+)"', run_dot))
    marked, out = [], []
    for line in scan_dot.splitlines():
        m = re.match(r'(\s*\d+\s*\[\s*label\s*=\s*"([^"]+)")(.*)$', line)
        if m and m.group(2) != "all" and m.group(2) not in run and "optional" not in m.group(3):
            line = m.group(1) + ", optional = true" + m.group(3)
            marked.append(m.group(2))
        out.append(line)
    return "\n".join(out) + "\n", marked


def rulegraph_from_files(project, min_literal=3):
    """Read every Snakefile / .smk under `project` and return a rule graph in `snakemake --rulegraph` (DOT) form.
    Only rules that lead to `rule all` are kept when the project has one (so helper rules for building
    references or test data don't clutter the map)."""
    files = snakemake_files(project)
    if not files:
        raise SystemExit(f"no Snakefile or .smk files found under {project}")
    proj = Project(files)
    names = sorted(proj.rules, key=lambda r: proj.rules[r]["order"])
    if not names:
        raise SystemExit(f"no rules found in the Snakefile / .smk files under {project}")

    outputs = {}
    for r in names:
        pats = {s for e in proj.rules[r]["output"] for s in proj.values(e) if isinstance(s, str)}
        outputs[r] = [t for t in (tokens(p) for p in pats) if literal_length(t) >= min_literal]

    edges = set()
    for r in names:
        for expr in proj.rules[r]["input"]:
            for v in proj.values(expr):
                if isinstance(v, tuple):
                    if v[1] in proj.rules and v[1] != r:
                        edges.add((v[1], r))
                    continue
                t = tokens(v)
                if literal_length(t) < min_literal:
                    continue
                for src in names:
                    if src != r and any(can_match_same_file(t, o) for o in outputs[src]):
                        edges.add((src, r))

    keep = set(names)
    if "all" in proj.rules:                            # only rules that lead to `rule all`
        keep, todo = {"all"}, ["all"]
        while todo:
            b = todo.pop()
            for a, bb in edges:
                if bb == b and a not in keep:
                    keep.add(a)
                    todo.append(a)
        found, kept = len(names) - 1, len(keep) - 1
        if found >= 8 and kept < found / 4:
            print(f"warning: only {kept} of the {found} rules found lead to `rule all`, so the map leaves most of the "
                  "pipeline out. If that's wrong, `rule all` may build its inputs in a way --scan can't follow; "
                  "compare with `snakemake --rulegraph`.", file=sys.stderr)
    ids ={r: k for k, r in enumerate(r for r in names if r in keep)}
    conditional = proj.conditional_rules() - {"all"}
    out = ["digraph snakemake_dag {"]
    out += [f'\t{i}[label = "{r}"{", optional = true" if r in conditional else ""}];' for r, i in ids.items()]
    out += [f"\t{ids[a]} -> {ids[b]}" for a, b in sorted(edges, key=lambda e: (ids.get(e[1], 0), ids.get(e[0], 0)))
            if a in ids and b in ids]
    out.append("}")
    return "\n".join(out) + "\n"
