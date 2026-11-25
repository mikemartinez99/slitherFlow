# Quick start

## Draw your first map

Point slitherFlow at the folder you normally run Snakemake from:

```shell
slitherflow auto /path/to/my-pipeline --png
```

That writes three files to your current folder:

| File | What it is |
|---|---|
| `my-pipeline_subway.yaml` | The draft map, which you'll edit |
| `my-pipeline_subway.svg` | The map |
| `my-pipeline_subway.png` | The map as an image |

If your pipeline needs a particular config file or profile to build its graph, put Snakemake's arguments after `--`:

```shell
slitherflow auto /path/to/my-pipeline --png -- --configfile config/test.yaml
```

Then edit the YAML and re-draw it. See [Customizing your map](guide/customizing.md).

```shell
slitherflow render my-pipeline_subway.yaml --png --pdf
```

!!! note "Your edits are safe"
    Running `auto` again won't overwrite your edits. It only writes a new draft if the YAML file doesn't exist yet, or if you pass `--overwrite-spec`.

## Show every optional step

Snakemake's rule graph only includes the rules your current config uses. If rRNA removal is switched off, for example, the rRNA step won't be on the map. To draw every rule no matter how the pipeline is configured, use `--scan`:

```shell
slitherflow auto /path/to/my-pipeline --png --scan
```

Instead of running Snakemake, this reads every `Snakefile` and `.smk` file in the project (hidden and `test`/`tests` folders are skipped). It works out which rules connect by matching each rule's inputs against other rules' outputs, the same way Snakemake does. It follows variables, `expand()`, f-strings, helper functions, input functions, `rules.X.output` and `rules.X.input`, and anything that depends on the config is treated like a wildcard. Only rules that lead to `rule all` are kept, so helper rules for building references don't clutter the map.

A scanned map shows every path the pipeline can take, so it's usually busier than the default one. Rules defined inside an `if` block, or in a file that's only included inside one (`if config["dedup"]: include: "rules/dedup.smk"`), are marked [`optional: true`](guide/customizing.md#mark-optional-steps) and drawn dashed. A rule defined on both sides of an `if`/`else` exists either way, so it isn't marked. Rules that are always defined but only asked for under some settings can't be spotted from the files alone, for example `expand(...) if config["validate"] else []` in `rule all`, or an input function that adds a file for one backend. To catch those, add `--compare`:

```shell
slitherflow auto /path/to/my-pipeline --png --scan --compare -- --configfile config/config.yaml
```

This also runs `snakemake --rulegraph` (with any Snakemake arguments after `--`) and marks every rule your current config doesn't use as optional. It needs Snakemake and a config that resolves, like the default mode.

!!! warning "Best effort"
    Paths built from the sample sheet at run time, or rules imported with `use rule ... from`, can't always be followed. If a connection is missing, compare with `snakemake --rulegraph`, or add it yourself with [`feeds`](guide/customizing.md#connect-lines-together).

### If the scanned map is nearly empty

`--scan` only keeps rules that lead to `rule all`. If `rule all` builds its list of targets in a way the scan can't follow, such as a function imported from another module (`input: final_targets(config)`), most or all of the pipeline drops out. slitherFlow warns you when that happens:

- **"none of the N rules found lead to `rule all`, so there is nothing to draw"**: nothing connects to `rule all` at all. The draft then stops with "the rule graph has no source rule".
- **"only K of the N rules found lead to `rule all`"**: on a pipeline with 8 or more rules, fewer than a quarter of them made it onto the map.

Either way, compare with the default mode (`slitherflow auto /path/to/my-pipeline`), which asks Snakemake for the rule graph and so sees the real targets. If Snakemake can't run there, save its graph somewhere it can (`snakemake --rulegraph > rulegraph.dot`) and pass it with `--rulegraph rulegraph.dot`.

## Try it on the bundled example

The repository includes a saved rule graph from the GDSC miRNA-seq pipeline, so you can try slitherFlow without Snakemake or the pipeline itself. Download it and draw the map:

```shell
curl -LO https://raw.githubusercontent.com/mikemartinez99/slitherFlow/main/examples/mirnaseq/rulegraph.dot
slitherflow auto GDSC-miRNAseq-analysis-pipeline --rulegraph rulegraph.dot --png
```

In a clone, skip the download and pass `--rulegraph examples/mirnaseq/rulegraph.dot` from the `slitherFlow` folder.

The result looks like this:

![miRNA-seq draft map](examples/mirnaseq/mirnaseq_draft.png)

It's a reasonable start, but names like "Mirbase padded aln" come straight from the rule names, and there are no tools or output files yet. [Customizing your map](guide/customizing.md) covers how to fix that.
