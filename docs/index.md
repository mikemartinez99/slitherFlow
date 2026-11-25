---
hide:
  - navigation
---

# slitherFlow <img src="logo/slitherflow_hex.png" alt="slitherFlow logo" align="right" width="140"/>

**Subway maps for Snakemake pipelines.**

slitherFlow turns a Snakemake pipeline into a subway-map figure, in the style of the nf-core pipeline diagrams. It reads your pipeline's rule graph, writes a first draft of the map as a YAML file, and draws it as an SVG (plus PNG or PDF if you want them). You then edit the YAML until the map is to your liking.

[![Subway map of the GDSC miRNA-seq pipeline: isomiR, alignment, QC, UMI and spike-in lines run from the input FASTQ to a MultiQC report](examples/mirnaseq/mirnaseq.png)](examples/mirnaseq/mirnaseq.png)

*The [GDSC miRNA-seq pipeline](https://github.com/Dartmouth-Data-Analytics-Core/GDSC-miRNAseq-analysis-pipeline), drawn with slitherFlow. Click to enlarge.*

## What slitherFlow does

<div class="grid cards" markdown>

- **Drafts the map for you**

    ---

    From your pipeline's rule graph, with no setup.

- **Shows every optional step**

    ---

    With [`--scan`](quickstart.md#show-every-optional-step) or whatever your pipeline config passes.

- **Keeps maps as plain YAML**

    ---

    So the map is fully flexible and [customizable](guide/customizing.md).

- **Writes SVG, PNG, and PDF**

    ---

    With fully editable vector text.

</div>

## In three commands

```shell
pixi global install -c conda-forge -c bioconda --git https://github.com/mikemartinez99/slitherFlow.git --expose slitherflow
slitherflow auto /path/to/my-pipeline --png        # draft a map
slitherflow render my-pipeline_subway.yaml --png   # re-draw after editing the YAML
```

No pixi? See [Installation](installation.md) for installing with pip.

## Where to next

<div class="grid cards" markdown>

- **[Installation](installation.md)**: install slitherFlow and the optional tools it uses.
- **[Quick start](quickstart.md)**: draw your first map, or try the bundled example.
- **[Customizing your map](guide/customizing.md)**: rename steps, add tools and outputs, connect lines, change colours.
- **[Spec reference](reference/spec.md)**: every option the YAML file accepts.
- **[Citing slitherFlow](citing.md)**: how to cite it, and who helped build it.

</div>
