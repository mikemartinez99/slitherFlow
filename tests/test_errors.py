"""Bad specs and bad rule graphs stop with a message that says what to fix, instead of a traceback."""
import copy

import pytest

import slitherflow

BASE = {
    "trunk": {"stations": [{"name": "Trimming"}, {"name": "Alignment"}], "lines": ["main"]},
    "lines": {
        "main": {"row": 0, "stations": [{"name": "Counts"}, {"name": "Report"}]},
        "qc": {"from": "Alignment", "row": 1, "stations": [{"name": "Stats"}, {"name": "Plots"}]},
    },
}


def broken(change):
    spec = copy.deepcopy(BASE)
    change(spec)
    return spec


def test_base_spec_is_valid():
    slitherflow.render(copy.deepcopy(BASE))


@pytest.mark.parametrize("change, message", [
    (lambda s: s["trunk"]["lines"].append("missing"),
     "trunk.lines names 'missing'"),
    (lambda s: s["lines"]["qc"].update({"from": "Nowhere"}),
     "is not 'trunk', 'input', a trunk station name"),
    (lambda s: s["lines"].update({"b": {"from": {"line": "nope", "station": "X"}, "row": 2, "stations": [{"name": "B"}]}}),
     "naming another line"),
    (lambda s: s["lines"].update({"b": {"from": {"line": "main", "station": "Nope"}, "row": 2, "stations": [{"name": "B"}]}}),
     "does not name a station on line 'main'"),
    (lambda s: s["lines"].update({
        "b": {"from": {"line": "c", "station": "C"}, "row": 2, "stations": [{"name": "B"}]},
        "c": {"from": {"line": "b", "station": "B"}, "row": 3, "stations": [{"name": "C"}]}}),
     "branch from each other in a loop"),
    (lambda s: s["lines"]["qc"].update({"to": "terminus"}),
     "the spec has no terminus"),
    (lambda s: s["lines"]["qc"].update({"to": {"line": "main", "station": "Nope"}}),
     "does not name a station on another line"),
    (lambda s: s["lines"]["qc"]["stations"][0].update({"feeds": [{"line": "main", "station": "Nope"}]}),
     "does not name a station on another line"),
    # a target without `x` would just be pushed right, so pin both ends
    (lambda s: (s["lines"]["main"]["stations"][0].update({"x": 700}),
                s["lines"]["qc"]["stations"][1].update({"x": 900, "feeds": [{"line": "main", "station": "Counts"}]})),
     "which is not to its right"),
])
def test_bad_spec_stops_with_a_clear_message(change, message):
    with pytest.raises(SystemExit, match=message):
        slitherflow.render(broken(change))


@pytest.mark.parametrize("palette, message", [
    ("rainbow", "palette 'rainbow' is not one of: okabe-ito"),
    ([], "non-empty list of colours"),
    (["#000000", 3], "non-empty list of colours"),
    ({"a": "#000000"}, "non-empty list of colours"),
])
def test_bad_palette_stops_with_a_clear_message(palette, message):
    with pytest.raises(SystemExit, match=message):
        slitherflow.render(dict(copy.deepcopy(BASE), palette=palette))


def test_empty_rulegraph():
    with pytest.raises(SystemExit, match="no rules found"):
        slitherflow.spec_from_rulegraph("this is not a rule graph")


def test_rulegraph_that_is_all_cycle():
    """No rule is a source, so the loop is broken at the first rule: a -> b is drawn, b -> a is listed as left
    out (before, this stopped with "no source rule")."""
    dot = '0[label = "a"];\n1[label = "b"];\n0 -> 1\n1 -> 0\n'
    text = slitherflow.spec_from_rulegraph(dot)
    assert "#   - b -> a" in text


def test_rulegraph_with_no_rules_but_all():
    with pytest.raises(SystemExit, match="no source rule"):
        slitherflow.spec_from_rulegraph('0[label = "all"];\n')
