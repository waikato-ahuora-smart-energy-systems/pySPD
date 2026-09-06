# Maintaining the documentation

PySPD uses the same Sphinx Read the Docs theme as OpenPinch. Its default theme
provides the blue search header, dark left navigation, serif headings,
breadcrumbs, and previous/next links. MyST parses the Markdown source pages;
Sphinx renders them with the `sphinx_rtd_theme` theme.

The public manual contains user guides, study recipes, validation guidance,
and references. Internal engineering records stay in `private/docs/`.

## Build and preview

From the repository root:

```shell
uv sync --frozen --group docs
uv run --no-sync sphinx-build -W --keep-going -b html docs site
uv run --no-sync python -m http.server 8765 --bind 127.0.0.1 --directory site
```

Open `http://127.0.0.1:8765/`. Rebuild after editing a page, then refresh the
browser. The strict build treats warnings as errors, including missing pages,
unresolved internal references, and documents omitted from every toctree.
Before submitting:

```shell
uv run --no-sync pytest tests/release/test_packaging_contract.py -q
git diff --check
```

`site/` is generated and ignored by Git. Clear it before rebuilding when moving
or removing pages; Sphinx does not delete all obsolete outputs automatically.
The HTML builder uses `.html` page URLs, matching OpenPinch.

## Structure and navigation

| Location | Purpose |
|---|---|
| `README.md` | Project purpose, quick start, status, and links |
| `docs/conf.py` | Sphinx theme, Markdown extensions, and publication exclusions |
| `docs/index.md` | Manual landing page and main documentation toctree |
| `docs/getting-started.md` | Installation-to-report walkthrough |
| `docs/user-guide/` | Inputs, configuration, execution, results, and scenario API |
| `docs/case-studies/` | Study recipes and implemented research profiles |
| `docs/validation/` | Reference data and comparison methods |
| `docs/reference/` | Commands, fields, report contracts, terminology, and limitations |
| `private/docs/` | Gates, ADRs, research logs, developer processes, and roadmaps |

Add a page to the appropriate index's MyST `{toctree}` directive. Keep normal
Markdown links relative to the source page; MyST resolves `.md` links and
heading anchors to the generated HTML URLs.

Use MyST admonitions rather than Material-specific syntax:

````markdown
:::{admonition} Memory before cores
:class: note

Choose workers according to available memory.
:::
````

Use ordinary section headings for comparisons and definition lists for the
landing page's task choices. Preserve the standard theme appearance so the
manual continues to match OpenPinch.

## Read the Docs and CI

`.readthedocs.yaml` selects Ubuntu 24.04, Python 3.13, native `uv sync` with the
`docs` dependency group, and the Sphinx configuration `docs/conf.py`. Warnings
fail hosted builds. The dependency lock pins Sphinx, MyST, and the RTD theme;
local and CI installation additionally pass `--frozen`.

The site builds without importing PySPD, reading GDX, or solving models.
Building documentation on Linux does not qualify Linux solver results. A
hosted build still requires a connected Read the Docs project.

## Publication boundary

The Sphinx source directory is `docs/`. Internal records live outside it.
`exclude_patterns` also prevents an old archive restored into `docs/gate-*/`
from appearing in the website. Never add `private/` to a toctree, include
instruction, static-assets directory, or download link.

The small atlas JSON/CSV artifacts are linked as user downloads. Raw solver
observations and internal certificates remain repository-only. Preserve
immutable evidence bytes when moving records.

## Check examples

Compare commands against CLI help and configuration fields against
`ApplicationConfiguration`. Execute self-contained examples when changing them;
a documentation build validates parsing and links, not Python behavior.
Label examples requiring external inputs or a GAMS runtime, and distinguish
production workflows from research profiles and planned extensions.
