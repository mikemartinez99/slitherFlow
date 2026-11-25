# Citing slitherFlow

If you use slitherFlow in your work, please cite it:

> Martinez, M. (2026). *slitherFlow: subway maps for Snakemake pipelines* (Version 1.1.0) [Computer software]. https://github.com/mikemartinez99/slitherFlow

```bibtex
@software{slitherflow,
  author  = {Martinez, Mike},
  title   = {slitherFlow: subway maps for Snakemake pipelines},
  version = {1.1.0},
  year    = {2026},
  url     = {https://github.com/mikemartinez99/slitherFlow}
}
```

The citation details are also in [`CITATION.cff`](https://github.com/mikemartinez99/slitherFlow/blob/main/CITATION.cff), so the **Cite this repository** button in the sidebar of the [GitHub repository](https://github.com/mikemartinez99/slitherFlow) gives the same reference in other formats.

## Acknowledgements

slitherFlow was inspired by [nf-metro](https://github.com/pinin4fjords/nf-metro), which draws metro-map diagrams for Nextflow and nf-core pipelines. slitherFlow brings the same kind of figure to Snakemake.

## Thank you to our contributors

- [Bryn Pickering](https://github.com/brynpickering), for pixi packaging and cross-platform CI ([#2](https://github.com/mikemartinez99/slitherFlow/pull/2))
- [Yassine Abdelouadoud](https://github.com/YassineAbdelouadoud), for handling rule-graph loops ([#10](https://github.com/mikemartinez99/slitherFlow/pull/10)) and following `rules.<name>.input` in `--scan` ([#11](https://github.com/mikemartinez99/slitherFlow/pull/11))
