"""The renderer: example maps stay pixel-for-pixel the same, and hand-written specs draw cleanly."""

import pytest
import yaml

import slitherflow
from conftest import EXAMPLES

SPECS = sorted(EXAMPLES.glob("*/*.yaml"))


@pytest.mark.parametrize("spec_path", SPECS, ids=[p.stem for p in SPECS])
def test_example_matches_committed_svg(spec_path):
    """Rendering each example spec reproduces its committed SVG byte for byte. If a rendering change is
    intended, re-render the examples (`slitherflow render examples/<name>/<name>.yaml --png --pdf`), look at
    the new images, and commit them."""
    svg, _ = slitherflow.render(yaml.safe_load(spec_path.read_text(encoding="utf-8")))
    assert svg == spec_path.with_suffix(".svg").read_text(encoding="utf-8"), f"{spec_path.name} no longer renders the same"


@pytest.mark.parametrize("spec_path", SPECS, ids=[p.stem for p in SPECS])
def test_example_has_no_overlaps(spec_path):
    _, cv = slitherflow.render(yaml.safe_load(spec_path.read_text(encoding="utf-8")))
    assert slitherflow.check_overlaps(cv) == []


def readme_spec():
    """The full spec example in the docs' spec reference, so the documentation can't drift from what the tool
    accepts."""
    text = (EXAMPLES.parent / "docs" / "reference" / "spec.md").read_text(encoding="utf-8")
    blocks = text.split("```yaml\n")[1:]
    block = next(b.split("```")[0] for b in blocks if b.startswith('title: "My pipeline"'))
    return yaml.safe_load(block)


def test_readme_spec_renders_cleanly():
    _, cv = slitherflow.render(readme_spec())
    assert slitherflow.check_overlaps(cv) == []


def test_branch_inherits_parent_colour_and_legend_entry():
    svg, _ = slitherflow.render(readme_spec())
    qc_colour = slitherflow.PALETTE[1]                 # second non-branch line without its own colour
    assert svg.count(">Quality control<") == 1          # one legend entry for qc and its branch
    assert qc_colour in svg


def test_explicit_x_is_never_moved():
    spec = readme_spec()
    spec["lines"]["peaks"]["stations"][1]["x"] = 1234
    _, cv = slitherflow.render(spec)
    assert spec["lines"]["peaks"]["stations"][1]["_x"] == 1234


def test_overlap_check_reports_a_real_overlap():
    """Two stations pinned to the same spot must be reported, so a clean result means something."""
    spec = readme_spec()
    spec["lines"]["qc"]["stations"] = [{"name": "Fingerprints", "x": 900}, {"name": "Fingerprints 2", "x": 905}]
    spec["lines"]["fragments"]["from"]["station"] = "Fingerprints"
    _, cv = slitherflow.render(spec)
    assert any("Fingerprints" in p for p in slitherflow.check_overlaps(cv))


def test_terminus_with_nothing_going_in_is_reported():
    """A terminus that no line reaches would sit on the map on its own; the check says so (and --strict fails)."""
    spec = {"trunk": {"stations": [{"name": "A"}]},
            "lines": {"main": {"row": 0, "to": "none", "stations": [{"name": "B"}]}},
            "terminus": {"name": "Report"}}
    _, cv = slitherflow.render(spec)
    assert any(p.startswith("station 'Report' has no lines going into it") for p in slitherflow.check_overlaps(cv))


def test_a_lone_trunk_station_is_not_reported():
    """A one-rule pipeline is just a trunk station with no lines: nothing is wrong with that."""
    _, cv = slitherflow.render({"trunk": {"stations": [{"name": "Build"}]}, "lines": {}})
    assert slitherflow.check_overlaps(cv) == []


def line_colours(svg):
    """Stroke colours of the legend's line swatches, in legend order."""
    import re
    return re.findall(r'<line x1="[^"]+" y1="[^"]+" x2="[^"]+" y2="[^"]+" stroke="(#[0-9A-Fa-f]{6})" stroke-width="[^"]+" stroke-linecap', svg)


def test_default_palette_is_okabe_ito():
    svg, _ = slitherflow.render(readme_spec())
    assert slitherflow.PALETTE == slitherflow.PALETTES["okabe-ito"]
    assert line_colours(svg)[1] == slitherflow.PALETTES["okabe-ito"][1]     # qc: second line, no colour of its own


@pytest.mark.parametrize("name", sorted(slitherflow.PALETTES))
def test_named_palette_colours_the_lines(name):
    spec = readme_spec()
    spec["palette"] = name
    svg, cv = slitherflow.render(spec)
    colours = slitherflow.PALETTES[name]
    # peaks keeps its own colour; qc and spike take the palette's 2nd and 3rd colours; the branch shares qc's
    assert line_colours(svg)[:3] == ["#009E73", colours[1], colours[2]]
    assert slitherflow.check_overlaps(cv) == []


def test_palette_name_ignores_case():
    spec = readme_spec()
    spec["palette"] = "Tol-Bright"
    svg, _ = slitherflow.render(spec)
    assert line_colours(svg)[1] == slitherflow.PALETTES["tol-bright"][1]


def test_custom_palette_list_is_used_and_repeats():
    spec = readme_spec()
    spec["palette"] = ["#111111", "#222222"]
    svg, _ = slitherflow.render(spec)
    assert line_colours(svg)[:3] == ["#009E73", "#222222", "#111111"]    # third colourless line wraps round


@pytest.mark.parametrize("name", sorted(slitherflow.PALETTES))
def test_palette_preview_is_up_to_date(name):
    """Every palette has a preview in examples/palettes/ (shown in the docs), and it matches what the renderer
    draws today. Rebuild them with the loop in docs/examples.md."""
    spec = yaml.safe_load((EXAMPLES / "cutrun" / "cutrun_draft.yaml").read_text(encoding="utf-8"))
    spec["palette"] = name
    svg, _ = slitherflow.render(spec)
    preview = EXAMPLES / "palettes" / f"{name}.svg"
    assert preview.with_suffix(".png").exists(), f"no preview image for palette '{name}'"
    assert svg == preview.read_text(encoding="utf-8"), f"examples/palettes/{name}.svg is out of date"
