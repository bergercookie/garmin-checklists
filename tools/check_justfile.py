"""Check that the justfile is the single way to run things.

Two invariants, both cheap to break by accident:

1. Every `just <recipe>` named in the docs or the workflows exists.
2. The workflows drive everything through `just`, rather than calling pytest,
   ruff, mypy, tach, pre-commit or docker directly -- otherwise CI and a
   developer's machine can quietly diverge.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WORKFLOWS = REPO / ".github" / "workflows"

#: Lines that merely install a tool, rather than running it.
INSTALLS = re.compile(r"\b(pipx|pip|pip3|apt-get|apt|brew|cargo|uv tool)\s+install\b")

#: Tools that must be reached through a recipe, not invoked in a workflow.
DIRECT_CALLS = re.compile(
    r"(?<![\w/-])(uv run pytest|pytest|ruff|mypy|tach|pre-commit|uvx pre-commit"
    r"|monkeyc|docker build|docker compose)(?![\w-])"
)

#: `just foo` / `just foo bar` in prose, code blocks or workflow steps.
JUST_CALL = re.compile(r"\bjust\s+([a-z][a-z0-9-]*)")

#: Words that follow "just" in English but are not recipes.
NOT_RECIPES = {
    "a",
    "an",
    "and",
    "as",
    "is",
    "it",
    "like",
    "one",
    "run",
    "that",
    "the",
    "to",
    "use",
    "what",
}


def recipes() -> set[str]:
    listing = subprocess.run(
        ["just", "--summary"], cwd=REPO, capture_output=True, text=True, check=True
    )
    return set(listing.stdout.split())


def documents() -> list[Path]:
    return [
        REPO / "README.md",
        *sorted((REPO / "docs").glob("*.md")),
        *sorted(WORKFLOWS.glob("*.yml")),
    ]


def main() -> int:
    argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    ).parse_args()
    known = recipes()
    problems: list[str] = []

    for path in documents():
        text = path.read_text()
        for match in JUST_CALL.finditer(text):
            name = match.group(1)
            if name in NOT_RECIPES or name in known:
                continue
            line = text[: match.start()].count("\n") + 1
            problems.append(f"{path.relative_to(REPO)}:{line}: no such recipe: just {name}")

    for path in sorted(WORKFLOWS.glob("*.yml")):
        for number, raw_line in enumerate(path.read_text().splitlines(), start=1):
            stripped = raw_line.strip()
            if stripped.startswith("#"):
                continue
            # Cut the `just <recipe>` calls out and scan what is left, rather
            # than exempting the whole line. A compound step -- `just install &&
            # pytest -x` -- is the likeliest way this invariant breaks, and
            # exempting any line containing "just " waved exactly that through.
            remainder = JUST_CALL.sub("", stripped)
            if INSTALLS.search(remainder):
                continue
            found = DIRECT_CALLS.search(remainder)
            if found:
                problems.append(
                    f"{path.relative_to(REPO)}:{number}: calls {found.group(1)!r} directly; "
                    "add a recipe and call that instead"
                )

    if problems:
        print("justfile is not the single source of truth:\n", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1
    print(f"{len(known)} recipes; docs and workflows all go through just")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
