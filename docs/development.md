# Development

## Running the tests

From a [clone](installation.md#from-a-clone-for-development):

```shell
pixi run -e test-py314 test
```

Use `test-py39` to test on the oldest supported Python version. Without pixi, run:

```shell
pip install ".[test]"
pytest
```

The tests don't need Snakemake or rsvg-convert. They check that:

- the example maps still render exactly as committed;
- every rule in each saved rule graph gets a station, and no connection is dropped;
- the right end station is picked;
- nothing overlaps;
- bad specs fail with a useful message;
- `--scan` follows each pattern it claims to, using the small made-up workflow in `tests/data/scan_project`.

If you change how maps are drawn on purpose, re-render the examples (see [Rebuild the examples](examples.md#rebuild-the-examples)), look at the new images, and commit them along with your change. The same tests run on GitHub for every push, on Linux, macOS and Windows, with Python 3.9 and 3.14.

## Building these docs

The site is built with [MkDocs](https://www.mkdocs.org/) and the [Material](https://squidfunk.github.io/mkdocs-material/) theme, and published to GitHub Pages on every push to `main`.

```shell
pip install ".[docs]"
mkdocs serve        # live preview at http://127.0.0.1:8000
```

The pages live in `docs/`. The `examples/` and `logo/` folders are symlinked into it, so the site always shows the same images the tests check.

## How the code is organized

The code lives in the `slitherflow/` package, one file per job:

| File | What it does |
|---|---|
| `cli.py` | The `slitherflow` command: `auto`, `draft` and `render` |
| `rulegraph.py` | Runs `snakemake --rulegraph` in a project |
| `scan.py` | `--scan`: builds the rule graph by reading Snakefiles and `.smk` files |
| `draft.py` | Turns a rule graph into a starter YAML spec (trunk, lines, branches, end station) |
| `render.py` | Lays out a spec and draws it as SVG |
| `canvas.py` | SVG drawing helpers, which also record what was drawn where |
| `overlaps.py` | The overlap check |
| `style.py` | Colour palettes, sizes and spacing |

## A note on AI

AI tools were used to help structure and write the code in this repository. All of its outputs, including every map shown here, were checked by Mike Martinez before being committed.
