"""The drafter: from a saved `snakemake --rulegraph`, every rule gets a station and no connection is lost."""
import re

import yaml

import slitherflow
from conftest import EXAMPLES, parse_rulegraph, drawn_connections


def test_every_rule_is_placed(rulegraph):
    rules, _ = parse_rulegraph(rulegraph["dot"])
    spec = rulegraph["spec"]
    stations = [st["name"] for st in spec.get("trunk", {}).get("stations", [])]
    stations += [st["name"] for ln in spec["lines"].values() for st in ln["stations"]]
    if spec.get("terminus"):
        stations.append(spec["terminus"]["name"])
    assert sorted(stations) == sorted(slitherflow.pretty(r) for r in rules)
    assert "could not place" not in rulegraph["spec_text"].lower()


def test_terminus_is_chosen_from_the_graph(rulegraph):
    expected = rulegraph["terminus"]
    terminus = rulegraph["spec"].get("terminus")
    if expected is None:
        assert terminus is None
    else:
        assert terminus["name"] == slitherflow.pretty(expected)


def test_every_connection_is_drawn_except_into_the_terminus(rulegraph):
    _, edges = parse_rulegraph(rulegraph["dot"])
    spec = rulegraph["spec"]
    term = (spec.get("terminus") or {}).get("name")
    drawn = drawn_connections(spec)
    missing = [(a, b) for a, b in edges
               if (slitherflow.pretty(a), slitherflow.pretty(b)) not in drawn and slitherflow.pretty(b) != term]
    assert missing == []


def test_draft_renders_without_overlaps(rulegraph):
    _, cv = slitherflow.render(rulegraph["spec"])
    assert slitherflow.check_overlaps(cv) == []


def test_drafts_match_committed_examples():
    """The example drafts are exactly what `draft` writes today. If a drafter change is intended, rebuild them
    with the commands in docs/examples.md and commit the new files."""
    for name, project in [("cutrun", "GDSC-CUT-RUN-pipeline"), ("mirnaseq", "GDSC-miRNAseq-analysis-pipeline")]:
        dot = (EXAMPLES / name / "rulegraph.dot").read_text(encoding="utf-8")
        committed = (EXAMPLES / name / f"{name}_draft.yaml").read_text(encoding="utf-8")
        assert slitherflow.spec_from_rulegraph(dot, title=project) == committed, f"{name}_draft.yaml is out of date"


def test_side_line_sits_on_the_side_it_feeds():
    """CUT&RUN: the spike-in line feeds 'Generate signal tracks', which is below the trunk, so it runs below."""
    dot = (EXAMPLES / "cutrun" / "rulegraph.dot").read_text(encoding="utf-8")
    spec = yaml.safe_load(slitherflow.spec_from_rulegraph(dot))
    spike = next(ln for ln in spec["lines"].values()
                 if any(st["name"] == "Spikein alignment" for st in ln["stations"]))
    assert spike["row"] > 0


def test_branches_from_one_station_share_a_side():
    """DAC RNA-seq with every option on: RSEM and featureCounts both leave 'Alignment', on the same side as the
    pre-alignment line that joins it, so the station's label keeps one side free."""
    from conftest import DATA
    spec = yaml.safe_load(slitherflow.spec_from_rulegraph((DATA / "dac_rnaseq_all_options.dot").read_text(encoding="utf-8")))
    lines = spec["lines"]
    leaving = [ln for ln in lines.values() if isinstance(ln.get("from"), dict)
               and ln["from"]["station"] == "Alignment"]
    joining = [ln for ln in lines.values() if isinstance(ln.get("to"), dict) and ln["to"]["station"] == "Alignment"]
    parent_row = lines[leaving[0]["from"]["line"]]["row"]
    sides = {ln["row"] > parent_row for ln in leaving + joining}
    assert len(leaving) == 2 and len(sides) == 1


def test_warnings_around_the_graph_are_ignored():
    """Snakemake can print warnings before the graph; only node and edge lines matter."""
    dot = (EXAMPLES / "mirnaseq" / "rulegraph.dot").read_text(encoding="utf-8")
    noisy = "Building DAG of jobs...\nImportError: something unrelated\n" + dot + "\nDone.\n"
    assert slitherflow.spec_from_rulegraph(noisy) == slitherflow.spec_from_rulegraph(dot)


def small_dot(edges):
    names = sorted({n for e in edges for n in e} | {"all"})
    ids = {n: k for k, n in enumerate(names)}
    lines = [f'{ids[n]}[label = "{n}"];' for n in names]
    lines += [f"{ids[a]} -> {ids[b]}" for a, b in edges]
    return "\n".join(lines) + "\n"


def trunk_and_lines(dot):
    spec = yaml.safe_load(slitherflow.spec_from_rulegraph(dot))
    trunk = [st["name"] for st in spec["trunk"]["stations"]]
    lines = sorted([st["name"] for st in ln["stations"]] for ln in spec["lines"].values())
    return trunk, lines, spec


def test_trunk_stops_where_a_small_pipeline_splits():
    """SnakeBat's shape: one rule fans out two ways and never splits 3 ways. The trunk used to run to the end
    of the longest chain, leaving no lines to draw along it."""
    trunk, lines, spec = trunk_and_lines(small_dot([("calc", "combine"), ("combine", "plot"), ("calc", "collate")]))
    assert trunk == ["Calc"]
    assert lines == [["Collate"], ["Combine", "Plot"]]
    assert spec["trunk"]["lines"]                      # something is drawn along the trunk
    slitherflow.render(spec)


def test_pipeline_that_never_splits_keeps_one_line():
    trunk, lines, spec = trunk_and_lines(small_dot([("a", "b"), ("b", "c")]))
    assert trunk == ["A"] and lines == [["B", "C"]]
    assert spec["trunk"]["lines"]


def test_rulegraph_drafts_mark_nothing_optional():
    """Issue: every side line was drawn optional. A plain `snakemake --rulegraph` only holds rules the config runs,
    so an energy model's four independent weather / hydrology downloads (side lines from the input) stay solid,
    with a commented-out hint instead."""
    from conftest import DATA
    text = slitherflow.spec_from_rulegraph((DATA / "energy_default.dot").read_text(encoding="utf-8"))
    spec = yaml.safe_load(text)
    from_input = [ln for ln in spec["lines"].values() if ln.get("from") == "input"]
    assert sorted(ln["stations"][0]["name"] for ln in from_input) == [
        "Download cerra", "Download efas discharge", "Download efas static", "Download era5"]
    assert not any(ln.get("optional") for ln in spec["lines"].values())
    stations = spec["trunk"]["stations"] + [st for ln in spec["lines"].values() for st in ln["stations"]]
    assert not any(st.get("optional") for st in stations)
    assert text.count("# optional: true") == len(from_input)


def with_optional(dot, marked):
    """Mark rules the way `--scan` does: `N[label = "rule", optional = true];`."""
    return re.sub(r'(\d+)\[label = "([^"]+)"\]',
                  lambda m: m.group(0)[:-1] + (", optional = true]" if m.group(2) in marked else "]"), dot)


def test_optional_rules_in_the_graph_become_optional_lines_and_stations():
    """`--scan` marks conditional rules with `optional = true`: a line whose rules are all optional is dashed, an
    optional rule on a solid line is a dashed station, and a solid branch of a dashed line is set back to solid
    (branches inherit their parent's dashing)."""
    dot = small_dot([("a", "b"), ("b", "c"), ("b", "d"), ("b", "e"), ("c", "end"), ("d", "end"), ("e", "end"),
                     ("c", "opt"), ("opt", "back"),
                     ("x", "y"), ("y", "w"), ("w", "v"), ("v", "end"), ("y", "z")])
    text = slitherflow.spec_from_rulegraph(with_optional(dot, {"opt", "x", "y", "w", "v"}))
    spec = yaml.safe_load(text)
    lines = spec["lines"]
    line_of = {st["name"]: lid for lid, ln in lines.items() for st in ln["stations"]}
    station = {st["name"]: st for ln in lines.values() for st in ln["stations"]}

    side, branch = lines[line_of["X"]], lines[line_of["Z"]]
    assert [st["name"] for st in side["stations"]] == ["X", "Y", "W", "V"]
    assert side["optional"] is True and not any(st.get("optional") for st in side["stations"])
    assert branch["from"] == {"line": line_of["X"], "station": "Y"} and branch["optional"] is False
    assert station["Opt"]["optional"] is True and not lines[line_of["Opt"]].get("optional")
    solid = [n for n in station if n not in {"Opt", "X", "Y", "W", "V"}]
    assert not any(station[n].get("optional") for n in solid)
    assert not any(st.get("optional") for st in spec["trunk"]["stations"])
    slitherflow.render(spec)


def test_draft_does_not_assume_bioinformatics():
    """Issue: drafts hardcoded a FASTQ input icon and "every sample" wording, which is wrong for, say, an energy
    model. The input icon now says "IN" (with a comment suggesting others) and the wording is domain-neutral."""
    from conftest import DATA
    text = slitherflow.spec_from_rulegraph((DATA / "energy_default.dot").read_text(encoding="utf-8"))
    assert yaml.safe_load(text)["input"]["file"] == "IN"
    assert "FASTQ" not in text.replace('e.g. "FASTQ"', "")
    assert "sample" not in text.lower()


def test_terminus_always_has_a_line_going_in():
    """Issue: `report` is fed by fetch, build and export, but export also feeds a later rule, so the line ran on
    past it and no line ended at the terminus: it was drawn with nothing going in. The line is now cut after
    its last terminus input, and the rest leaves that station as a branch."""
    dot = small_dot([("fetch", "build"), ("build", "export"), ("export", "extra"),
                     ("fetch", "report"), ("build", "report"), ("export", "report"), ("report", "all"),
                     ("extra", "all")])
    trunk, lines, spec = trunk_and_lines(dot)
    assert spec["terminus"]["name"] == "Report"
    into = [ln for ln in spec["lines"].values() if ln["to"] == "terminus"]
    assert [[st["name"] for st in ln["stations"]] for ln in into] == [["Build", "Export"]]
    extra = next(ln for ln in spec["lines"].values() if ln["stations"][0]["name"] == "Extra")
    assert extra["from"]["station"] == "Export"
    _, cv = slitherflow.render(spec)
    assert slitherflow.check_overlaps(cv) == []


def test_rule_feeding_itself_is_left_out_not_a_crash():
    """Issue: a rule whose job for one wildcard value reads its own output for another shows up in the rule graph
    as `solve -> solve`. The drafter recursed along it until RecursionError. The loop is now left out and listed
    in the spec, and the rest of the map is drawn as usual."""
    dot = small_dot([("prepare", "solve"), ("solve", "solve"), ("solve", "report"), ("report", "all")])
    text = slitherflow.spec_from_rulegraph(dot)
    spec = yaml.safe_load(text)
    stations = [st["name"] for st in spec["trunk"]["stations"]]
    stations += [st["name"] for ln in spec["lines"].values() for st in ln["stations"]]
    assert sorted(stations) == ["Prepare", "Report", "Solve"]
    assert "#   - solve -> solve" in text
    _, cv = slitherflow.render(spec)
    assert slitherflow.check_overlaps(cv) == []


def test_longer_loop_drops_only_the_connection_that_closes_it():
    """A child scenario built from its parent's run: `scenario -> run` and `run -> scenario` in the rule graph.
    Walking forward from the inputs, `run -> scenario` is the one that goes back, so only it is left out."""
    dot = small_dot([("data", "scenario"), ("scenario", "run"), ("run", "scenario"), ("run", "summary"),
                     ("run", "figures"), ("summary", "all"), ("figures", "all")])
    text = slitherflow.spec_from_rulegraph(dot)
    spec = yaml.safe_load(text)
    assert "#   - run -> scenario" in text
    assert "scenario -> run" not in text
    assert ("Scenario", "Run") in drawn_connections(spec)
    slitherflow.render(spec)


def test_loop_no_source_leads_to_is_broken_too():
    """`--scan` on a real pipeline: run and scenario only fed each other (the input that feeds run from the data
    is built at run time, which the scan can't see), and a figure rule read from both them and the data rule.
    The loop wasn't reachable from any source, so it stayed, and the figure rule had no depth (KeyError)."""
    dot = small_dot([("run", "scenario"), ("scenario", "run"), ("data", "figure"), ("run", "figure"),
                     ("scenario", "figure"), ("figure", "all")])
    text = slitherflow.spec_from_rulegraph(dot)
    assert "#   - scenario -> run" in text
    slitherflow.render(yaml.safe_load(text))
