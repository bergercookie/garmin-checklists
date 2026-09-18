# The bridge: dependencies, tests, linting, versioning and release checks.
#
# Imported by the justfile at the repository root; run these with
# `just <recipe>` from anywhere in the repo, as usual.

# --------------------------------------------------------------------- bridge

# Create/refresh the bridge virtualenv.
install:
    cd "{{bridge}}" && uv sync

# Run the test suite (pytest-xdist spreads it over every core).
test *args:
    cd "{{bridge}}" && uv run pytest {{args}}

# What CI runs for coverage: the suite plus the artifact report formats.
coverage-ci:
    cd "{{bridge}}" && uv run pytest --cov-report=xml --cov-report=html

# Publish the coverage table to a CI run summary.
coverage-summary:
    cd "{{bridge}}" && uv run coverage report --fail-under=0

# Every pre-commit hook over the whole tree: ruff, mypy, tach and the
# file-hygiene checks. This is exactly what CI runs.
lint:
    cd "{{root}}" && uvx pre-commit run --all-files

# Apply the formatter and the safe lint fixes, across bridge/ and e2e/.
fmt:
    uv run --project "{{root}}/bridge" ruff format .
    uv run --project "{{root}}/bridge" ruff check --fix .

# The suite plus a browsable HTML report. Coverage and the threshold are on
# by default (see addopts in pyproject.toml), so `just test` gates too.
coverage *args:
    cd "{{bridge}}" && uv run pytest --cov-report=html {{args}}
    @echo "HTML report: bridge/htmlcov/index.html"

# Fail if uv.lock has drifted from pyproject.toml.
#
# Worth its own check because of one failure mode that is invisible until a
# release: some uv versions record this project's own hatch-vcs version in the
# lock, and that string carries the commit hash, so the lock goes stale on the
# very next commit and `uv sync --locked` -- which the Dockerfile runs -- stops
# working. A current uv writes `(dynamic)` instead and the problem disappears.
#
# Note this must run before `just install`, which would quietly re-lock and hide
# the drift it is meant to catch.
check-lockfile:
    cd "{{bridge}}" && uv lock --check

# Fail if the Python version has drifted apart across pyproject, mypy, ruff,
# devbox and the Dockerfile.
check-python-version:
    uv run --project "{{root}}/bridge" python "{{root}}/tools/check_python_version.py"

# Fail unless the package version matches a release tag. Used by the release
# workflow; run it yourself with `just check-tag v1.2.0` before tagging.
check-tag tag:
    cd "{{bridge}}" && uv run python "{{root}}/tools/check_release_tag.py" {{tag}}

# Prove that a git tag really does set the version, using a throwaway clone.
check-version-from-tag:
    uv run --project "{{root}}/bridge" python "{{root}}/tools/check_version_from_tag.py"

# Build the wheel and sdist that a release publishes.
build:
    cd "{{bridge}}" && uv build --out-dir dist

# Print the version, which comes from the last git tag via hatch-vcs.
version:
    @cd "{{bridge}}" && uv run python -c "from checklists_bridge.config import VERSION; print(VERSION)"

# Everything CI runs, so `just check` before a tag means what it says.
check: lint check-lockfile check-python-version check-justfile check-justfile-user check-version-from-tag coverage docs

# Serve the bridge locally. Needs CHECKLISTS_ADMIN_PASSWORD.
run:
    cd "{{bridge}}" && uv run checklists-bridge

# Install the git pre-commit hooks.
hooks:
    uvx pre-commit install
