# Commands

```text
slitherflow auto   PROJECT [-o map.svg]   [--scan [--compare] | --rulegraph FILE.dot] [--palette NAME] [--png] [--pdf] [--strict] [-- SNAKEMAKE ARGS]
slitherflow draft  PROJECT [-o spec.yaml] [--scan [--compare] | --rulegraph FILE.dot] [--palette NAME] [-- SNAKEMAKE ARGS]
slitherflow render SPEC    [-o map.svg]   [--palette NAME] [--png] [--pdf] [--strict]
slitherflow --version
```

| Command | What it does |
|---|---|
| `auto` | Writes a draft spec (if there isn't one yet) and renders it, in one step |
| `draft` | Only writes the draft spec |
| `render` | Renders a YAML spec |

## Getting the rule graph (`auto`, `draft`)

| Option | Meaning |
|---|---|
| `PROJECT` | The Snakemake project folder (where you normally run `snakemake`). Its name becomes the map's title. |
| *(default)* | Runs `snakemake --rulegraph --nolock` in `PROJECT`, so it's safe to use while the pipeline is running. |
| `--scan` | Reads the Snakefiles directly instead of running Snakemake, so every optional rule shows up. See [Show every optional step](../quickstart.md#show-every-optional-step). |
| `--compare` | With `--scan`: also runs `snakemake --rulegraph` and marks the rules your current config doesn't use as optional. See [Show every optional step](../quickstart.md#show-every-optional-step). |
| `--rulegraph FILE.dot` | Uses a saved `snakemake --rulegraph` output instead of running Snakemake. `PROJECT` is then only used for the title. |
| `--save-rulegraph FILE.dot` | Keeps a copy of the rule graph that was used, from Snakemake or from `--scan`. |
| `--snakemake PATH` | Uses a specific Snakemake executable (default: `snakemake` on your `PATH`). |
| `-- ARGS…` | Everything after `--` is passed to Snakemake, e.g. `-- --configfile config/test.yaml`. With `--scan`, only together with `--compare`. |

`--scan` and `--rulegraph` can't be used together.

## Output (`auto`, `draft`, `render`)

| Option | Commands | Meaning |
|---|---|---|
| `-o`, `--output` | `auto` | The map `.svg` (default: `<project>_subway.svg`). The spec is written next to it with a `.yaml` suffix. |
| `-o`, `--output` | `draft` | The spec `.yaml` (default: `<project>_subway.yaml`). |
| `-o`, `--output` | `render` | The map `.svg` (default: next to the spec). |
| `--overwrite-spec` | `auto` | Replace an existing spec. By default `auto` keeps it, so your edits are safe. |
| `--palette NAME` | `auto`, `draft`, `render` | Line colours: `okabe-ito` (default), `tol-bright`, `tol-vibrant`, `tol-muted`, `ibm` or `tab10`. A new draft gets `palette: NAME`; on `render` (and `auto` with a kept spec) it overrides the spec's `palette:` without changing the file. See [Colour palettes](spec.md#colour-palettes). |
| `--png` | `auto`, `render` | Also write a PNG at 3× resolution. Needs `rsvg-convert`. |
| `--pdf` | `auto`, `render` | Also write a vector PDF. Needs `rsvg-convert`. |
| `--strict` | `auto`, `render` | Exit with an error if the [overlap check](../guide/layout.md#overlap-check) finds anything. Useful in CI. |
