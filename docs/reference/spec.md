# Spec reference

A map is described by a YAML file, called the spec. `slitherflow draft` writes a starter spec for you; this page lists everything it can contain.

## Example

Here's a small spec that uses most of the options. Everything except `lines` is optional.

```yaml
title: "My pipeline"
subtitle: "v1.0  ·  Snakemake"
input: {label: "Input", sublabel: "Paired-end", file: "FASTQ"}

trunk:
  stations:
    - {name: "Trimming", tool: "cutadapt"}
    - {name: "Alignment", tool: "Bowtie2", outputs: [{file: "BAM", label: "Aligned reads"}]}
  lines: [peaks, qc]           # lines that run along the trunk, top to bottom

lines:
  peaks:
    name: "Peak calling"
    color: "#009E73"
    row: -1
    to: terminus
    stations:
      - {name: "Peak calling", tool: "MACS3"}
      - {name: "Peak filtering", tool: "bedtools", outputs: [{file: "BED", label: "Filtered peaks"}]}
  qc:
    name: "Quality control"
    row: 1
    to: terminus
    stations: [{name: "Fingerprints", tool: "deepTools"}]
  spike:
    name: "Spike-in normalization"
    optional: true
    from: "Trimming"           # leaves a trunk station (or use `input`)
    row: -1.6
    to: {line: peaks, station: "Peak filtering"}
    stations: [{name: "Spike-in alignment", tool: "Bowtie2"}]
  fragments:
    from: {line: qc, station: "Fingerprints"}   # a branch
    row: 1.6
    stations: [{name: "Fragment sizes", tool: "deepTools"}]

terminus: {name: "MultiQC", sublabel: "QC report", row: 1, file: "HTML"}
footnote: "One line of explanation under the legend."
```

## Top level

| Key | Meaning |
|---|---|
| `title`, `subtitle` | Text at the top of the map |
| `input` | The start of the map: `{label, sublabel, file}`. `file` is the text on the input icon, such as `"FASTQ"`, `"CSV"` or `"NC"` (default `"IN"`) |
| `trunk` | The shared steps every run goes through (see [below](#trunk)) |
| `lines` | **Required.** A mapping of line ID → line (see [below](#lines)) |
| `terminus` | The end station (see [below](#terminus)) |
| `footnote` | One line of explanation under the legend |
| `palette` | Line colours: a palette name such as `tol-bright`, or a list of colours (see [below](#colour-palettes)) |
| `style` | Overrides for the default look (see [below](#style)) |

## Trunk

| Key | Meaning |
|---|---|
| `stations` | The trunk's stations, drawn as pills spanning its lines |
| `lines` | The line IDs that run along the trunk, top to bottom |
| `labels: above` | Put the trunk's station labels above it |
| `split_gap` | Extra space before the lines split apart |
| `branch_gap` | Extra space before the first station after the split |

## Lines

| Key | Meaning |
|---|---|
| `name` | The name shown in the legend (defaults to the line ID) |
| `color` | Line colour (defaults to the next [palette](#colour-palettes) colour) |
| `row` | Vertical position. Negative is above the trunk, positive below, and fractions are fine |
| `optional: true` | Draw the line dashed, and add "(optional)" to its legend entry |
| `from` | Where the line starts: a trunk station's name, `input`, or `{line, station}` to make it a branch |
| `to` | Where the line ends: `terminus`, or `{line, station}` to join another line. By default it just stops |
| `stations` | The line's stations, left to right |

## Stations

| Key | Meaning |
|---|---|
| `name`, `tool` | The label, and the smaller grey text under it |
| `optional: true` | Dashed station circle, with "optional" added to the tool text |
| `x` | Exact horizontal position |
| `gap` | Extra space before this station |
| `label: above` / `below` | Which side the label goes on. By default it goes away from the trunk (or, on a branch, away from its parent line), and moves to the other side if a line is in the way |
| `outputs` | File icons: a list of `{file, label, color, dx, dy, label_side}` |
| `feeds` | A list of `{line, station}` that this step also feeds into. The target has to be further right, on a different line |

## Terminus

| Key | Meaning |
|---|---|
| `name`, `sublabel` | The end station's label |
| `row` | Vertical position |
| `file` | Draw an output icon with this file type |
| `x` | Exact horizontal position |
| `outputs` | Extra file icons, as for stations |

## Style

Anything under `style` overrides these defaults:

| Key | Default | Meaning |
|---|---|---|
| `font` | `'Helvetica Neue', Helvetica, Arial, sans-serif` | Font family |
| `line_width` | `7` | Width of every line |
| `gap` | `10` | Spacing between parallel lines on the trunk |
| `spacing` | `170` | Distance between trunk stations |
| `branch_spacing` | `140` | Distance between stations on a branch |
| `row_height` | `130` | Vertical distance per row |
| `corner` | `22` | Corner radius of 90° bends |
| `dash` | `16 9` | Dash pattern for optional lines |
| `margin` | `48` | Space around the map |

## Colour palettes

Lines without their own `color` take the palette's colours in order, starting again from the first if there are more lines than colours. Branches share their parent line's colour. Pick a palette by name:

```yaml
palette: tol-bright
```

| Name | Colours | Notes |
|---|---|---|
| `okabe-ito` | <span style="color:#009E73">■</span> <span style="color:#E69F00">■</span> <span style="color:#CC79A7">■</span> <span style="color:#D55E00">■</span> <span style="color:#56B4E9">■</span> <span style="color:#0072B2">■</span> <span style="color:#F0E442">■</span> <span style="color:#000000">■</span> | **Default.** Colour-blind safe ([Okabe & Ito](https://jfly.uni-koeln.de/color/)) |
| `tol-bright` | <span style="color:#4477AA">■</span> <span style="color:#EE6677">■</span> <span style="color:#228833">■</span> <span style="color:#CCBB44">■</span> <span style="color:#66CCEE">■</span> <span style="color:#AA3377">■</span> <span style="color:#BBBBBB">■</span> | Colour-blind safe ([Paul Tol](https://personal.sron.nl/~pault/)) |
| `tol-vibrant` | <span style="color:#0077BB">■</span> <span style="color:#EE7733">■</span> <span style="color:#009988">■</span> <span style="color:#CC3311">■</span> <span style="color:#33BBEE">■</span> <span style="color:#EE3377">■</span> <span style="color:#BBBBBB">■</span> | Colour-blind safe ([Paul Tol](https://personal.sron.nl/~pault/)) |
| `tol-muted` | <span style="color:#332288">■</span> <span style="color:#88CCEE">■</span> <span style="color:#44AA99">■</span> <span style="color:#117733">■</span> <span style="color:#999933">■</span> <span style="color:#DDCC77">■</span> <span style="color:#CC6677">■</span> <span style="color:#882255">■</span> <span style="color:#AA4499">■</span> | Colour-blind safe ([Paul Tol](https://personal.sron.nl/~pault/)); softer, with nine colours |
| `ibm` | <span style="color:#648FFF">■</span> <span style="color:#DC267F">■</span> <span style="color:#FE6100">■</span> <span style="color:#785EF0">■</span> <span style="color:#FFB000">■</span> | Colour-blind safe (IBM Design Library). Only five colours, so on a map with more lines some share a colour |
| `tab10` | <span style="color:#1F77B4">■</span> <span style="color:#FF7F0E">■</span> <span style="color:#2CA02C">■</span> <span style="color:#D62728">■</span> <span style="color:#9467BD">■</span> <span style="color:#8C564B">■</span> <span style="color:#E377C2">■</span> <span style="color:#7F7F7F">■</span> <span style="color:#BCBD22">■</span> <span style="color:#17BECF">■</span> | matplotlib's default colours. Familiar, but **not** colour-blind safe |

To see each one on a real map, look at the [palette previews](../guide/customizing.md#change-colours).

Or give your own colours, in the order lines should use them:

```yaml
palette: ["#1b9e77", "#d95f02", "#7570b3"]
```

`slitherflow render --palette NAME` (and `auto`/`draft --palette NAME`) picks a named palette from the command line. On `render` it overrides the spec's `palette:` without changing the file.
