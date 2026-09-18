#!/usr/bin/env python3
"""Fail if the project's Python version is not the same in every file.

The floor is stated in six places that no single tool reads: the package
metadata, mypy, ruff, devbox, and both Docker stages. They drift silently --
mypy will happily keep checking against an old version for months -- so this
asserts they agree and prints what it found.

`bridge/pyproject.toml::project.requires-python` is the source of truth.
Run it with `just check-python-version`.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _fail(message: str) -> str:
    print(f"FAIL  {message}")
    return message


def expected_version() -> str:
    """The floor everything else has to match, as ``major.minor``."""
    data = tomllib.loads((ROOT / "bridge" / "pyproject.toml").read_text())
    requires = str(data["project"]["requires-python"])
    match = re.fullmatch(r">=(\d+\.\d+)", requires.strip())
    if match is None:
        raise SystemExit(
            f"requires-python is {requires!r}; this check understands '>=X.Y' only, "
            "so either simplify it or teach this script the new form"
        )
    return match.group(1)


def found_versions(version: str) -> dict[str, list[str]]:
    """Map each place the version is stated to the versions actually there."""
    del version
    bridge = tomllib.loads((ROOT / "bridge" / "pyproject.toml").read_text())
    root = tomllib.loads((ROOT / "pyproject.toml").read_text())
    devbox = json.loads((ROOT / "devbox.json").read_text())
    dockerfile = (ROOT / "bridge" / "Dockerfile").read_text()

    # ruff spells it "py314"; everything else spells it "3.14".
    target = str(root["tool"]["ruff"]["target-version"])
    spelled_out = re.fullmatch(r"py(\d)(\d+)", target)
    return {
        "bridge/pyproject.toml  [tool.mypy] python_version": [
            str(bridge["tool"]["mypy"]["python_version"])
        ],
        "pyproject.toml  [tool.ruff] target-version": [
            f"{spelled_out.group(1)}.{spelled_out.group(2)}" if spelled_out else target
        ],
        "devbox.json  packages": [
            package.split("@", 1)[1]
            for package in devbox["packages"]
            if package.startswith("python@")
        ],
        "bridge/Dockerfile  FROM": re.findall(r"^FROM python:(\d+\.\d+)", dockerfile, re.M),
    }


def main() -> int:
    argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    ).parse_args()
    version = expected_version()
    print(f"bridge/pyproject.toml  requires-python  >={version}   (source of truth)")

    problems = []
    for where, versions in found_versions(version).items():
        if not versions:
            problems.append(_fail(f"{where}: no Python version found at all"))
        elif set(versions) != {version}:
            problems.append(_fail(f"{where}: {', '.join(versions)} (expected {version})"))
        else:
            print(f"PASS  {where}: {version}")

    if problems:
        print(f"\n{len(problems)} place(s) disagree with bridge/pyproject.toml.")
        return 1
    print(f"\nEvery file agrees on Python {version}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
