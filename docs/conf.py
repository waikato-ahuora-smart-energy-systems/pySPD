"""User documentation, using the same Sphinx RTD theme as OpenPinch."""

import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
metadata = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text())
project = "PySPD"
release = metadata["project"]["version"]
version = release

extensions = ["myst_parser", "sphinx_rtd_theme"]
source_suffix = {".md": "markdown", ".rst": "restructuredtext"}
root_doc = "index"
myst_enable_extensions = ["colon_fence", "deflist"]
myst_heading_anchors = 6

# Internal records live outside the source tree, in private/docs. These
# exclusions also protect against an old archive restored into docs/.
exclude_patterns = [
    "_build",
    ".DS_Store",
    "Thumbs.db",
    "gate-*",
    "adr",
    "research",
    "developer-guide",
    "engineering-record.md",
    "pyomo-vspd-stage-gate-plan.md",
    "case-studies/potential-builds.md",
]

# Match OpenPinch's uncustomized theme rather than approximating it with CSS.
html_theme = "sphinx_rtd_theme"
html_title = f"{project} {release} documentation"

html_show_copyright = False
