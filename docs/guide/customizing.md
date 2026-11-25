# Customizing your map

To customize the map, edit the YAML file and re-render it:

```shell
slitherflow render my-pipeline_subway.yaml --png --pdf
```

The examples below take pieces of the miRNA-seq draft and improve them. For every option, see the [spec reference](../reference/spec.md).

## Rename steps and add tools

Every station has a `name` and a `tool`. The tool is shown in smaller grey text under the name.

```yaml
  isomirs:
    name: "Isomir quantification"      # the name shown in the legend
    row: 1
    stations:
      - {name: "Collapse reads", tool: "seqcluster"}
      - {name: "Hairpin alignment", tool: "Bowtie"}
      - {name: "Isomir annotation", tool: "miRtop"}
```

You can rename line IDs too (`line2` → `isomirs`). Just update every place that refers to them.

## Show output files

Add `outputs` to a station to draw a file icon connected to it:

```yaml
      - name: "Isomir table"
        tool: "R"
        outputs: [{file: "TSV", label: "Isomir counts"}]
```

If an icon lands in an awkward spot, nudge it with `dx` and `dy`.

## Mark optional steps

A station with `optional: true` is drawn with a dashed circle. A line with `optional: true` is drawn dashed, and "(optional)" is added to its legend entry.

```yaml
      - {name: "PCA", tool: "R", optional: true}

  fastqc_config:
    name: "FastQC config"
    optional: true
    from: input            # starts from the raw input instead of the trunk
    row: 1.6
    stations: [{name: "Make config", tool: "Python"}]
```

## Change colours

Lines use the colour-blind-friendly [Okabe-Ito palette](../reference/spec.md#colour-palettes) by default. To recolour every line at once, pick another palette (or list your own colours):

```yaml
palette: tol-bright      # okabe-ito, tol-bright, tol-vibrant, tol-muted, ibm or tab10
```

To try one without editing the spec, use `slitherflow render my-pipeline_subway.yaml --palette tol-vibrant`.

Here's the CUT&RUN draft in each palette:

=== "okabe-ito"

    ![CUT&RUN draft drawn with the okabe-ito palette](../examples/palettes/okabe-ito.png)

=== "tol-bright"

    ![CUT&RUN draft drawn with the tol-bright palette](../examples/palettes/tol-bright.png)

=== "tol-vibrant"

    ![CUT&RUN draft drawn with the tol-vibrant palette](../examples/palettes/tol-vibrant.png)

=== "tol-muted"

    ![CUT&RUN draft drawn with the tol-muted palette](../examples/palettes/tol-muted.png)

=== "ibm"

    ![CUT&RUN draft drawn with the ibm palette](../examples/palettes/ibm.png)

=== "tab10"

    ![CUT&RUN draft drawn with the tab10 palette](../examples/palettes/tab10.png)

`okabe-ito`, the `tol-` palettes and `ibm` are colour-blind safe; `tab10` isn't. See [Colour palettes](../reference/spec.md#colour-palettes) for every colour in each one.

Set `color` on a line to give just that line its own colour:

```yaml
  genome:
    name: "Alignment"
    color: "#0072B2"
```

## Branches

A branch splits off a station partway along another line. It uses its parent line's colour and legend entry, unless you give it its own `name` and `color`.

```yaml
  mature:
    from: {line: genome, station: "miRBase alignment"}
    row: -0.6
    stations: [{name: "Mature stats", tool: "samtools"}]
```

## Connect lines together

By default a line just stops at its last station. Use `to` to send it somewhere:

- `to: terminus`: the line runs into the end station.
- `to: {line: peaks, station: "Peak filtering"}`: the line joins a station on another line.

When a step also feeds into a station on a different line, add `feeds` to that step. This one is from the CUT&RUN draft, where the filtered alignments also go straight into the FRiP calculation:

```yaml
    - {name: "Filter alignment", tool: "", feeds: [{line: line1, station: "Calc frip"}]}
```

## The end station

The terminus is the big station at the right edge of the map, usually something like a MultiQC report. Add `file` to give it an output icon:

```yaml
terminus: {name: "MultiQC", sublabel: "QC report", row: 1, file: "HTML"}
```

## Titles, notes and style

```yaml
title: "GDSC miRNA-seq pipeline"
subtitle: "v1.0  ·  Snakemake"
input: {label: "Input", sublabel: "Single-end", file: "FASTQ"}
footnote: "PCA runs only when there are enough samples."

style: {font: "Helvetica", line_width: 8}
```

## Before and after

For a complete before-and-after, compare the CUT&RUN draft ([`cutrun_draft.yaml`](https://github.com/mikemartinez99/slitherFlow/blob/main/examples/cutrun/cutrun_draft.yaml)) with the finished map ([`cutrun.yaml`](https://github.com/mikemartinez99/slitherFlow/blob/main/examples/cutrun/cutrun.yaml)).

=== "Draft, straight from `auto`"

    ![CUT&RUN draft](../examples/cutrun/cutrun_draft.png)

=== "After editing"

    ![CUT&RUN finished](../examples/cutrun/cutrun.png)
