"""--scan: build the rule graph by reading Snakefiles and .smk files, without running Snakemake.

tests/data/scan_project is a made-up workflow that uses each pattern the scanner follows; each test below names
the pattern it checks."""
import re

import pytest
import yaml

import slitherflow
from conftest import DATA, parse_rulegraph
from slitherflow.scan import can_match_same_file, rulegraph_from_files, tokens

PROJECT = DATA / "scan_project"


@pytest.fixture(scope="module")
def graph():
    """(rules, edges), keeping rule `all` and the edges into it (parse_rulegraph drops those)."""
    dot = rulegraph_from_files(PROJECT)
    names = dict(re.findall(r'(\d+)\s*\[\s*label\s*=\s*"([^"]+)"', dot))
    edges = {(names[a], names[b]) for a, b in re.findall(r"(\d+)\s*->\s*(\d+)", dot)}
    return set(names.values()), edges


def test_conditionally_included_rules_are_found(graph):
    rules, _ = graph
    assert "dedup" in rules                       # rules/dedup.smk is only included when `dedup` is on


def test_rules_that_never_lead_to_all_are_left_out(graph):
    rules, _ = graph
    assert "unused_helper" not in rules


def test_test_folders_are_skipped(graph):
    rules, _ = graph
    assert "make_test_data" not in rules


@pytest.mark.parametrize("edge, pattern", [
    (("trim", "filter"), "plain string input, temp() output"),
    (("trim", "align"), "variable set on both branches of an if/else"),
    (("filter", "align"), "f-string with a variable that has two possible values"),
    (("build_index", "align"), "keyword input"),
    (("align", "count"), "input function via unpack(), helper function, .format()"),
    (("dedup", "count"), "dict entry overwritten under an if inside the input function"),
    (("align", "dedup"), "helper function with a default argument"),
    (("trim", "trim_stats"), "log files count as outputs"),
    (("trim_stats", "report"), "rules.<name>.output"),
    (("report", "all"), "rules.<name>.output.<key> inside a list added with +="),
    (("dedup", "all"), "expand() added to a list under an if"),
])
def test_connection_is_found(graph, edge, pattern):
    _, edges = graph
    assert edge in edges, pattern


def test_no_extra_connections(graph):
    _, edges = graph
    expected = {("trim", "filter"), ("trim", "align"), ("filter", "align"), ("build_index", "align"),
                ("align", "count"), ("dedup", "count"), ("align", "dedup"), ("trim", "trim_stats"),
                ("trim_stats", "report"), ("count", "report"), ("count", "all"), ("report", "all"),
                ("dedup", "all")}
    assert edges == expected


def test_scanned_graph_drafts_and_renders():
    spec = yaml.safe_load(slitherflow.spec_from_rulegraph(rulegraph_from_files(PROJECT)))
    stations = [st["name"] for st in spec.get("trunk", {}).get("stations", [])]
    stations += [st["name"] for ln in spec["lines"].values() for st in ln["stations"]]
    if spec.get("terminus"):
        stations.append(spec["terminus"]["name"])
    rules, _ = parse_rulegraph(rulegraph_from_files(PROJECT))
    assert sorted(stations) == sorted(slitherflow.pretty(r) for r in rules)
    slitherflow.render(spec)


@pytest.mark.parametrize("a, b, same", [
    ("aligned/{sample}.bam", "aligned/{sample}.bam", True),
    ("aligned/{sample}.bam", "aligned/x.bam", True),
    ("aligned/{sample}.bam", "aligned/{sample}.bam.bai", False),
    ("peak-calling/{sample}_peaks.narrowPeak", "peak-calling/filtered/{s}_peaks.filtered.{t}", False),  # not across /
    ("peak-calling/filtered/{s}_peaks.filtered.{t}", "peak-calling/filtered/{x}_peaks.filtered.narrowPeak", True),
    ("qc/{sample}", "qc/{sample}", True),
    ("{sample,[A-Z]{2}}.txt", "AB.txt", True),
])
def test_patterns_match_the_same_file(a, b, same):
    assert can_match_same_file(tokens(a), tokens(b)) is same


def test_cli_scan_and_save_rulegraph(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    slitherflow.main(["auto", str(PROJECT), "--scan", "--save-rulegraph", "graph.dot"])
    assert (tmp_path / "scan_project_subway.svg").read_text(encoding="utf-8").startswith("<svg")
    assert "dedup" in (tmp_path / "graph.dot").read_text(encoding="utf-8")


def test_cli_scan_refuses_snakemake_arguments(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit, match="can't take Snakemake arguments"):
        slitherflow.main(["draft", str(PROJECT), "--scan", "--", "--configfile", "x.yaml"])


ENERGY = DATA / "energy_project"


def optional_rules(dot):
    return set(re.findall(r'label = "([^"]+)", optional = true', dot))


def test_only_rules_under_an_if_are_marked_optional():
    """scan_project: rules/dedup.smk is only included under `if USE_DEDUP:`; every other rule always exists."""
    assert optional_rules(rulegraph_from_files(PROJECT)) == {"dedup"}


def test_energy_model_marks_conditional_rules_not_independent_sources():
    """The shape from the issue: four weather / hydrology downloads that don't depend on `download_data` run
    every time, so they stay solid. The heat-demand rule (inside an `if`) and the validation file (included
    under an `if`) are the optional ones. Their targets are added with TARGETS.append(...)."""
    dot = rulegraph_from_files(ENERGY)
    assert optional_rules(dot) == {"build_heat_demand", "validate_results"}
    spec = yaml.safe_load(slitherflow.spec_from_rulegraph(dot))
    lines = spec["lines"]
    downloads = [ln for ln in lines.values() if ln.get("from") == "input"]
    assert len(downloads) == 4 and not any(ln.get("optional") for ln in downloads)
    station = {st["name"]: (lid, st) for lid, ln in lines.items() for st in ln["stations"]}
    heat_line, heat = station["Build heat demand"]
    assert heat.get("optional") or lines[heat_line].get("optional")
    val_line, val = station["Validate results"]
    assert val.get("optional") or lines[val_line].get("optional")
    others = [n for n in station if n not in {"Build heat demand", "Validate results"}]
    assert not any(station[n][1].get("optional") or lines[station[n][0]].get("optional") for n in others)


def test_rule_defined_on_both_sides_of_an_if_is_not_optional(tmp_path):
    (tmp_path / "Snakefile").write_text(
        'rule all:\n    input: "out/a.txt", "out/b.txt", "out/c.txt"\n\n'
        'if config["aligner"] == "fast":\n'
        '    rule align:\n        output: "out/a.txt"\n        shell: "fast"\n'
        'elif config["aligner"] == "slow":\n'
        '    rule align:\n        output: "out/a.txt"\n        shell: "slow"\n'
        'else:\n'
        '    rule align:\n        output: "out/a.txt"\n        shell: "default"\n\n'
        'if config.get("extra"):\n'
        '    rule extra:\n        output: "out/b.txt"\n        shell: "x"\n'
        'else:\n'
        '    rule plain:\n        output: "out/c.txt"\n        shell: "y"\n\n'
        'rule always:\n    input: "out/a.txt"\n    output: "out/d.txt"\n    shell: "z"\n', encoding="utf-8")
    assert optional_rules(rulegraph_from_files(tmp_path)) == {"extra", "plain"}


def test_file_included_both_ways_is_not_optional(tmp_path):
    """A file included under an `if` but also unconditionally (here from another included file) always exists."""
    (tmp_path / "rules").mkdir()
    (tmp_path / "Snakefile").write_text('include: "rules/common.smk"\nif config["x"]:\n    include: "rules/a.smk"\n'
                                        'rule all:\n    input: "out/a.txt"\n', encoding="utf-8")
    (tmp_path / "rules" / "common.smk").write_text('include: "a.smk"\n', encoding="utf-8")
    (tmp_path / "rules" / "a.smk").write_text('rule a:\n    output: "out/a.txt"\n    shell: "a"\n', encoding="utf-8")
    assert optional_rules(rulegraph_from_files(tmp_path)) == set()


def scanned_edges(project):
    dot = rulegraph_from_files(project)
    names = dict(re.findall(r'(\d+)\s*\[\s*label\s*=\s*"([^"]+)"', dot))
    return set(names.values()), {(names[a], names[b]) for a, b in re.findall(r"(\d+)\s*->\s*(\d+)", dot)}


def test_expand_fills_in_known_keyword_values(tmp_path):
    """Issue: expand("model/{name}.parquet", name=["nodes", "edges"]) was read as model/{name}.parquet, so `all`
    seemed to ask for every file in model/, pulling in a rule it never needs."""
    (tmp_path / "Snakefile").write_text(
        'rule all:\n    input:\n        expand("model/{name}.parquet", name=["nodes", "edges"]),\n\n'
        'rule build:\n    output:\n        "model/nodes.parquet",\n        "model/edges.parquet",\n'
        '    shell: "touch {output}"\n\n'
        'rule attribute:\n    input:\n        "model/nodes.parquet",\n    output:\n'
        '        "model/attribution.parquet",\n    shell: "touch {output}"\n', encoding="utf-8")
    assert scanned_edges(tmp_path) == ({"all", "build"}, {("build", "all")})


def test_expand_keeps_unknown_keywords_and_escapes_as_wildcards(tmp_path):
    """sample comes from the config (unknown: stays a wildcard); kind and part are known lists, so the rules for
    other values aren't connected; {{sample}} is Snakemake's escape for a wildcard left for the rule to fill."""
    (tmp_path / "Snakefile").write_text(
        'SAMPLES = config["samples"]\n'
        'rule all:\n    input:\n'
        '        expand("counts/{sample}.{kind}.tsv", sample=SAMPLES, kind=["genes"]),\n'
        '        "aligned/s1.bam",\n'
        'rule count_genes:\n    output: "counts/{sample}.genes.tsv"\n    shell: "x"\n'
        'rule count_exons:\n    output: "counts/{sample}.exons.tsv"\n    shell: "x"\n'
        'rule merge:\n    input: expand("aligned/{{sample}}.{part}.bam", part=["a", "b"])\n'
        '    output: "aligned/{sample}.bam"\n    shell: "x"\n'
        'rule align_a:\n    output: "aligned/{sample}.a.bam"\n    shell: "x"\n'
        'rule align_b:\n    output: "aligned/{sample}.b.bam"\n    shell: "x"\n'
        'rule align_c:\n    output: "aligned/{sample}.c.bam"\n    shell: "x"\n', encoding="utf-8")
    _, edges = scanned_edges(tmp_path)
    assert edges == {("count_genes", "all"), ("merge", "all"), ("align_a", "merge"), ("align_b", "merge")}


def test_rules_input_reference_is_followed(tmp_path):
    """Issue: `rule all: input: rules.reports.input` (a target rule gathering another target rule's inputs) was
    not followed, so everything behind it was dropped as "not leading to rule all"."""
    (tmp_path / "Snakefile").write_text(
        'rule make:\n    output: "results/{x}.txt"\n    shell: "touch {output}"\n\n'
        'rule reports:\n    input:\n        "results/a.txt",\n        "results/b.txt",\n\n'
        'rule all:\n    default_target: True\n    input:\n        rules.reports.input,\n', encoding="utf-8")
    assert scanned_edges(tmp_path) == ({"all", "make"}, {("make", "all")})


def test_rules_input_reference_chains_and_loops(tmp_path):
    """rules.x.input can point at a rule whose inputs are themselves rules.y.input or rules.z.output; a pair of
    rules referring to each other's inputs must not recurse forever."""
    (tmp_path / "Snakefile").write_text(
        'rule fit:\n    output: "fit/model.pkl"\n    shell: "x"\n'
        'rule plot:\n    output: "figs/plot.pdf"\n    shell: "x"\n'
        'rule figures:\n    input: "figs/plot.pdf", rules.models.input\n'
        'rule models:\n    input: rules.fit.output, rules.figures.input\n'
        'rule all:\n    default_target: True\n    input: rules.figures.input\n', encoding="utf-8")
    assert scanned_edges(tmp_path) == ({"all", "fit", "plot"}, {("fit", "all"), ("plot", "all")})


def test_warns_when_few_rules_lead_to_all(tmp_path, capsys):
    """A near-empty map is easy to mistake for a result: say how many rules were found but left out."""
    rules = "".join(f'rule r{k}:\n    output: "out/r{k}.txt"\n    shell: "x"\n' for k in range(9))
    (tmp_path / "Snakefile").write_text('rule all:\n    input: "out/r0.txt"\n' + rules, encoding="utf-8")
    rulegraph_from_files(tmp_path)
    assert "only 1 of the 9 rules found lead to `rule all`" in capsys.readouterr().err
    rulegraph_from_files(PROJECT)
    assert "warning" not in capsys.readouterr().err
BACKEND = DATA / "backend_project"
# `snakemake --rulegraph` for backend_project's config (backends: ["default"]): validate and fast_correction
# are defined, but only used for the "reference" and "fast" backends
BACKEND_RUN = 'digraph snakemake_dag {\n\t0[label = "all"];\n\t1[label = "summarize"];\n\t2[label = "simulate"];\n' \
              '\t1 -> 0\n\t2 -> 1\n}\n'


def test_append_inside_an_input_function_is_followed():
    """backend_project's summary_inputs() adds fast_correction's output with inputs.append(...)."""
    _, edges = scanned_edges(BACKEND)
    assert ("fast_correction", "summarize") in edges and ("validate", "all") in edges


def test_scan_alone_cannot_tell_these_rules_are_optional():
    """Both rules are defined outside any `if`: reading the files can't see that they only run for some backends."""
    assert optional_rules(rulegraph_from_files(BACKEND)) == set()


def test_compare_marks_rules_the_config_does_not_run():
    from slitherflow.scan import mark_not_run
    dot, marked = mark_not_run(rulegraph_from_files(BACKEND), BACKEND_RUN)
    assert sorted(marked) == ["fast_correction", "validate"]
    assert optional_rules(dot) == {"fast_correction", "validate"}
    again, marked_again = mark_not_run(dot, BACKEND_RUN)          # already marked: left as they are
    assert again == dot and marked_again == []


def test_cli_scan_compare(tmp_path, monkeypatch):
    """`draft --scan --compare` runs Snakemake (here: a recorded rule graph) with the arguments after `--`, and
    dashes the rules it leaves out."""
    import slitherflow.cli as cli
    calls = []
    monkeypatch.setattr(cli, "rulegraph_from_project", lambda project, exe, extra: calls.append(extra) or BACKEND_RUN)
    monkeypatch.chdir(tmp_path)
    slitherflow.main(["draft", str(BACKEND), "--scan", "--compare", "-o", "spec.yaml", "--", "--configfile", "x.yaml"])
    assert calls == [["--configfile", "x.yaml"]]
    spec = yaml.safe_load((tmp_path / "spec.yaml").read_text(encoding="utf-8"))
    optional = set()
    for ln in spec["lines"].values():
        for st in ln["stations"]:
            if ln.get("optional") or st.get("optional"):
                optional.add(st["name"])
    assert optional == {"Fast correction", "Validate"}


def test_cli_compare_needs_scan(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit, match="--compare only works with --scan"):
        slitherflow.main(["draft", str(BACKEND), "--compare"])
