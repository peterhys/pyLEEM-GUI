from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

project = "pyLEEM-GUI"
author = "Peter Sun"

release = version("pyleem-gui")
version = release

extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "superpowers", "Thumbs.db", ".DS_Store"]

autosummary_generate = True
autodoc_member_order = "bysource"
autodoc_typehints = "description"
autodoc_preserve_defaults = True
autodoc_default_options = {
    "members": True,
    "show-inheritance": True,
}

html_theme = "sphinx_book_theme"
html_title = f"{project} documentation"
html_theme_options = {
    "repository_url": "https://github.com/peterhys/pyLEEM-GUI",
    "use_repository_button": True,
}
