# How the first draft is built

slitherFlow only looks at the shape of the rule graph. It never guesses from rule names, so it works the same way on any pipeline.

| Part of the map | How it's chosen |
|---|---|
| **Trunk** | The steps every run goes through, drawn as pill-shaped stations across several lines. It follows the longest chain from the input, and stops where the pipeline splits three or more ways. |
| **Lines** | Each branch after the trunk becomes its own line, alternating above and below. |
| **Side lines** | Steps that start from the raw input, or leave the trunk early, become side lines. They're drawn solid, with a commented-out `# optional: true` you can switch on if they only run for some configs. |
| **Optional steps** | Only marked when the scan can tell. With `--scan`, a rule defined inside an `if` block, or in a file that's only included inside one, is drawn dashed. A plain `snakemake --rulegraph` only lists rules your config runs, so nothing in it is marked optional. Add `--compare` to `--scan` to also dash the rules your current config doesn't run. |
| **Branches** | Steps that split off partway along a line are drawn as branches. Branches leaving the same station go to the same side, so the station's label stays readable. |
| **Extra connections** | Any link in the rule graph that isn't already part of a line is drawn as a `feeds` connector. The exception is inputs to the end station, since drawing every QC file going into MultiQC would clutter the map. |
| **Loops** | A rule can feed itself, or an earlier rule, for another wildcard value (a warm start, or a child scenario built from its parent). Snakemake's rule graph then has a loop, which can't be drawn left to right, so the draft leaves out each connection that loops back and lists it in a comment at the end of the spec. |
| **Colours** | Lines take the [Okabe-Ito palette](../reference/spec.md#colour-palettes) in order. The draft writes `palette: okabe-ito` near the top, so you can recolour the whole map in one place; `--palette NAME` picks a different one when drafting. |
| **End station** | The final rule that collects from the most other rules. If no final rule merges branches, the map has no end station, and each line just stops. |

This works the same whether the graph came from Snakemake or from `--scan`.

!!! info "Rule `all` is always skipped"
    If your pipeline runs MultiQC inside rule `all` (as the miRNA-seq pipeline does), MultiQC won't be in the rule graph and won't be on the draft map. You can add it back as the [terminus](customizing.md#the-end-station) yourself.
