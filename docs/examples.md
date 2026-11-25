# Examples

Each example folder includes the pipeline's saved rule graph, so you can rebuild any of these maps without Snakemake.

## miRNA-seq

Started from `--scan`, with optional steps dashed. Spec: [`mirnaseq.yaml`](https://github.com/mikemartinez99/slitherFlow/blob/main/examples/mirnaseq/mirnaseq.yaml).

![miRNA-seq finished](examples/mirnaseq/mirnaseq.png)

??? example "The untouched draft"
    Lots of branches, and an end station that isn't MultiQC. Spec: [`mirnaseq_draft.yaml`](https://github.com/mikemartinez99/slitherFlow/blob/main/examples/mirnaseq/mirnaseq_draft.yaml).

    ![miRNA-seq draft](examples/mirnaseq/mirnaseq_draft.png)

## CUT&RUN

The CUT&RUN draft after editing. Spec: [`cutrun.yaml`](https://github.com/mikemartinez99/slitherFlow/blob/main/examples/cutrun/cutrun.yaml).

![CUT&RUN finished](examples/cutrun/cutrun.png)

??? example "The untouched draft"
    Exactly what `draft` writes. Includes two `feeds` connectors. Spec: [`cutrun_draft.yaml`](https://github.com/mikemartinez99/slitherFlow/blob/main/examples/cutrun/cutrun_draft.yaml).

    ![CUT&RUN draft](examples/cutrun/cutrun_draft.png)

## Rebuild the examples

From the cloned `slitherFlow` folder (with pixi, put `pixi run` in front of each command):

```shell
slitherflow draft GDSC-CUT-RUN-pipeline --rulegraph examples/cutrun/rulegraph.dot -o examples/cutrun/cutrun_draft.yaml
slitherflow render examples/cutrun/cutrun_draft.yaml --png --pdf

slitherflow draft GDSC-miRNAseq-analysis-pipeline --rulegraph examples/mirnaseq/rulegraph.dot -o examples/mirnaseq/mirnaseq_draft.yaml
slitherflow render examples/mirnaseq/mirnaseq_draft.yaml --png --pdf
```

The palette previews in [Customizing your map](guide/customizing.md#change-colours) are the CUT&RUN draft in each palette. Rebuild them with one command per palette:

```shell
for p in okabe-ito tol-bright tol-vibrant tol-muted ibm tab10; do
  slitherflow render examples/cutrun/cutrun_draft.yaml -o examples/palettes/$p.svg --palette $p --png
done
```

`examples/mirnaseq/rulegraph_scan.dot` is the graph `--scan` found for the miRNA-seq pipeline, which the finished map started from. Pass it to `--rulegraph` the same way to see that draft.

When you use `--rulegraph`, the project name is only used for the map's title.
