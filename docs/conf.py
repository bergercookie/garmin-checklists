"""Sphinx configuration.

The documentation is Markdown, parsed by MyST, so every page stays readable on
GitHub and in an editor as well as on the built site.
"""

project = "Checklists"
author = "Checklists contributors"
copyright = "2026, Checklists contributors"

extensions = ["myst_parser"]
myst_enable_extensions = ["colon_fence"]
myst_heading_anchors = 3

exclude_patterns = ["_build"]
templates_path: list[str] = []

html_theme = "furo"
html_title = "Checklists"
html_static_path: list[str] = []

# Broken cross-references and unknown roles should fail the build, not scroll by.
nitpicky = True
