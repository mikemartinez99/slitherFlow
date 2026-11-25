"""slitherFlow: subway maps for Snakemake pipelines.

    slitherflow auto   PROJECT_DIR [-o map.svg] [--scan [--compare] | --rulegraph FILE.dot] [--palette NAME] [--png] [--pdf] [-- SNAKEMAKE ARGS]
    slitherflow draft  PROJECT_DIR [-o spec.yaml] [--scan [--compare] | --rulegraph FILE.dot] [--palette NAME] [-- SNAKEMAKE ARGS]
    slitherflow render SPEC.yaml   [-o map.svg] [--palette NAME] [--png] [--pdf] [--strict]

By default `auto` and `draft` run `snakemake --rulegraph --nolock` inside PROJECT_DIR, which shows the rules your
current config uses; anything after `--` is passed to Snakemake (e.g. `-- --configfile config/test.yaml`).
With --scan they read every Snakefile and .smk file instead, so optional rules show up whatever the config,
and Snakemake isn't needed. Add --compare to also run `snakemake --rulegraph` and dash the rules your current
config doesn't use. Needs Python 3 + PyYAML; --png/--pdf need rsvg-convert.
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

from . import __version__
from .draft import spec_from_rulegraph
from .overlaps import check_overlaps
from .render import render
from .rulegraph import rulegraph_from_project
from .scan import mark_not_run, rulegraph_from_files
from .style import DEFAULT_PALETTE, PALETTES


def write_draft(dot_text, project_name, out, palette=None):
    spec_text = spec_from_rulegraph(dot_text, title=project_name, palette=palette or DEFAULT_PALETTE)
    Path(out).write_text(spec_text, encoding="utf-8")
    print(f"wrote {out}")


def render_file(spec_path, out, png=False, pdf=False, strict=False, palette=None):
    spec = yaml.safe_load(Path(spec_path).read_text(encoding="utf-8"))
    if palette:                             # --palette wins over the spec's own `palette:`
        spec["palette"] = palette
    svg, cv = render(spec)
    out = Path(out) if out else Path(spec_path).with_suffix(".svg")
    out.write_text(svg, encoding="utf-8")
    print(f"wrote {out}")
    for flag, args, suffix in [(png, ["-z", "3"], ".png"), (pdf, ["-f", "pdf"], ".pdf")]:
        if not flag:
            continue
        if not shutil.which("rsvg-convert"):
            print(f"rsvg-convert not found: cannot write {suffix} (install librsvg, e.g. `brew install librsvg` "
                  f"or `apt install librsvg2-bin`)", file=sys.stderr)
            continue
        dest = out.with_suffix(suffix)
        subprocess.run(["rsvg-convert", *args, str(out), "-o", str(dest)], check=True)
        print(f"wrote {dest}")
    problems = check_overlaps(cv)
    if problems:
        print(f"\n{len(problems)} possible overlap(s):", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        print("Move stations with x: / gap:, change row:, or nudge outputs with dx:/dy: in the spec.", file=sys.stderr)
        if strict:
            sys.exit(1)
    else:
        print("no overlaps found")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    extra = []
    if "--" in argv:                        # everything after `--` goes to snakemake
        k = argv.index("--")
        argv, extra = argv[:k], argv[k + 1:]

    ap = argparse.ArgumentParser(prog="slitherflow", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="version", version=f"slitherflow {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def palette_opt(p):
        p.add_argument("--palette", choices=list(PALETTES), metavar="NAME",
                       help=f"line colours: {', '.join(PALETTES)} (default: the spec's `palette:`, else "
                            f"{DEFAULT_PALETTE})")

    def render_opts(p):
        p.add_argument("--png", action="store_true", help="also write a PNG (3x) with rsvg-convert")
        p.add_argument("--pdf", action="store_true", help="also write a vector PDF with rsvg-convert")
        p.add_argument("--strict", action="store_true", help="exit 1 if any overlaps are found (for CI)")

    def project_opts(p):
        p.add_argument("project", help="Snakemake project directory (where `snakemake` normally runs)")
        p.add_argument("--snakemake", default="snakemake", help="snakemake executable (default: on PATH)")
        source = p.add_mutually_exclusive_group()
        source.add_argument("--rulegraph", metavar="DOT", help="use a saved `snakemake --rulegraph` file instead of running it")
        source.add_argument("--scan", action="store_true",
                            help="read every Snakefile and .smk file under PROJECT instead of running Snakemake: "
                                 "shows every rule, whatever the config (best effort; see the docs)")
        p.add_argument("--compare", action="store_true",
                       help="with --scan: also run `snakemake --rulegraph` (with any Snakemake arguments after `--`) "
                            "and mark the rules it leaves out as optional")
        p.add_argument("--save-rulegraph", metavar="DOT", help="also save the rule graph that was used (DOT format)")

    p = sub.add_parser("auto", help="rule graph -> starter spec -> map, in one step")
    project_opts(p)
    p.add_argument("-o", "--output", help="map .svg (default: <project>_subway.svg); the spec is written next to it")
    p.add_argument("--overwrite-spec", action="store_true", help="replace an existing spec (default: keep your edits)")
    palette_opt(p)
    render_opts(p)

    p = sub.add_parser("draft", help="write a starter spec from the project's rule graph")
    project_opts(p)
    p.add_argument("-o", "--output", help="spec .yaml (default: <project>_subway.yaml)")
    palette_opt(p)

    p = sub.add_parser("render", help="draw a map from a spec")
    p.add_argument("spec", help="YAML spec")
    p.add_argument("-o", "--output", help="map .svg (default: next to the spec)")
    palette_opt(p)
    render_opts(p)

    a = ap.parse_args(argv)
    if a.cmd == "render":
        render_file(a.spec, a.output, a.png, a.pdf, a.strict, a.palette)
        return

    if a.compare and not a.scan:
        sys.exit("--compare only works with --scan")
    name = Path(a.project).resolve().name
    if a.rulegraph:
        dot = Path(a.rulegraph).read_text(encoding="utf-8")
    elif a.scan:
        if extra and not a.compare:
            sys.exit("--scan doesn't run Snakemake, so it can't take Snakemake arguments after `--` "
                     "(add --compare to run it as well)")
        dot = rulegraph_from_files(a.project)
        if a.compare:
            dot, marked = mark_not_run(dot, rulegraph_from_project(a.project, a.snakemake, extra))
            print(f"--compare: {len(marked)} rule(s) found by --scan aren't used by the current config, marked "
                  f"optional" + (": " + ", ".join(marked) if marked else ""), file=sys.stderr)
    else:
        dot = rulegraph_from_project(a.project, a.snakemake, extra)
    if a.save_rulegraph:
        Path(a.save_rulegraph).write_text(dot, encoding="utf-8")
        print(f"wrote {a.save_rulegraph}")
    if a.cmd == "draft":
        write_draft(dot, name, a.output or f"{name}_subway.yaml", a.palette)
        return
    svg_out = Path(a.output or f"{name}_subway.svg")
    spec_out = svg_out.with_suffix(".yaml")
    if spec_out.exists() and not a.overwrite_spec:
        print(f"keeping existing spec {spec_out} (use --overwrite-spec to redraft it)")
    else:
        write_draft(dot, name, spec_out, a.palette)
    render_file(spec_out, svg_out, a.png, a.pdf, a.strict, a.palette)
