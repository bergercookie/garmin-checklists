#!/usr/bin/env python3
"""The version a nightly build calls itself, valid as a Python version *and* a Docker tag.

    0.2.1.dev202610120300

It is the next release's number with ``.dev<UTC minute>`` after it:

* **PEP 440**: a development release, ``N.N.N.devNNN``. It sorts before the
  release it leads up to and after the previous one, so ``pip`` and ``uv`` order
  nightlies correctly and never prefer one over a real release.
* **Docker**: letters, digits, ``.`` and ``-`` only, at most 128 characters, no
  leading ``.`` or ``-``. hatch-vcs's own between-tags spelling,
  ``0.2.1.dev4+g1a2b3cd``, has a ``+``, which a registry refuses -- that is the
  reason this exists rather than letting `git describe` name the build.

The number is the minute the build was made, so two builds never share a name and
a later one always sorts later, with no counter to keep anywhere. The next
release is the latest tag with its patch number raised, or, if that tag is a
pre-release such as ``v1.3.0-rc1``, the version it is heading for.

Usage: `just nightly-version`, which the nightly workflow runs. Needs the tags
fetched (`fetch-depth: 0`).
"""

from __future__ import annotations

import argparse
import datetime
import re
import subprocess
import sys

#: `v1.2.3`, optionally `v1.2.3-rc1`. Anything else is not a release tag.
TAG = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(-[0-9A-Za-z.-]+)?$")

#: A PEP 440 development release of a plain N.N.N, and what a registry accepts.
PEP_440_DEV = re.compile(r"^\d+\.\d+\.\d+\.dev\d+$")
DOCKER_TAG = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$")


def next_release(latest_tag: str | None) -> str:
    """The version the next release will have, given the latest tag (or none)."""
    if latest_tag is None:
        return "0.1.0"
    match = TAG.match(latest_tag)
    if match is None:
        raise ValueError(f"{latest_tag!r} is not a release tag like v1.2.3")
    major, minor, patch = (int(part) for part in match.group(1, 2, 3))
    # A pre-release is on its way to its own number; a release is behind it.
    return f"{major}.{minor}.{patch}" if match.group(4) else f"{major}.{minor}.{patch + 1}"


def nightly_version(latest_tag: str | None, when: datetime.datetime) -> str:
    """``next_release``'s number as a dated development release."""
    version = f"{next_release(latest_tag)}.dev{when.astimezone(datetime.UTC):%Y%m%d%H%M}"
    # Belt and braces: the point of this file is that both rules hold.
    if not PEP_440_DEV.match(version) or not DOCKER_TAG.match(version):
        raise ValueError(f"{version!r} is not both a PEP 440 version and a Docker tag")
    return version


def latest_tag() -> str | None:
    """The newest release tag reachable from HEAD, or None if there is none."""
    result = subprocess.run(
        ["git", "describe", "--tags", "--abbrev=0", "--match", "v[0-9]*"],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def main(argv: list[str]) -> int:
    argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    ).parse_args(argv[1:])
    print(nightly_version(latest_tag(), datetime.datetime.now(datetime.UTC)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
