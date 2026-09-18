# The documentation site.
#
# Imported by the justfile at the repository root; run these with
# `just <recipe>` from anywhere in the repo, as usual.

# ------------------------------------------------------------------------ docs

# Build the documentation site. Warnings are errors.
docs:
    cd "{{bridge}}" && uv run --group docs sphinx-build -W --keep-going \
        -b html "{{justfile_directory()}}/docs" "{{justfile_directory()}}/docs/_build/html"
    @echo "Open docs/_build/html/index.html"

# Rebuild and serve on http://127.0.0.1:8000 while you edit.
docs-serve: docs
    python3 -m http.server 8000 --directory docs/_build/html
