#!/usr/bin/env python3
"""Prove that tagging is all it takes to set the version.

Clones the working repository into a temporary directory, tags the clone, and
builds a wheel from it. If the filename does not carry the tag's version then
hatch-vcs is misconfigured -- which is the kind of thing nobody notices until
the day they cut a release.

The clone is thrown away, so the real repository never grows a fake tag.
Run it with `just check-version-from-tag`.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

#: Absurd on purpose: if this ever shows up in a real artefact, it came from here.
FAKE_TAG = "v9.9.9"


def run(command: list[str], cwd: Path) -> str:
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(
            f"FAIL  {' '.join(command)} exited {result.returncode}\n{result.stderr.strip()}"
        )
    return result.stdout


def main() -> int:
    argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    ).parse_args()
    with tempfile.TemporaryDirectory() as temporary:
        clone = Path(temporary) / "clone"
        # A local clone of HEAD: fast, and it carries the commit graph hatch-vcs
        # wants. Uncommitted work in the real tree is deliberately not included.
        run(["git", "clone", "--quiet", str(REPO), str(clone)], cwd=REPO)
        run(["git", "tag", "--force", FAKE_TAG], cwd=clone)

        bridge = clone / "bridge"
        run(["uv", "build", "--wheel", "--out-dir", "dist"], cwd=bridge)

        wheels = sorted((bridge / "dist").glob("*.whl"))
        if len(wheels) != 1:
            print(f"FAIL  expected one wheel, built {len(wheels)}")
            return 1

        name = wheels[0].name
        expected = FAKE_TAG.removeprefix("v")
        match = re.fullmatch(r"checklists_bridge-(.+?)-py3-none-any\.whl", name)
        if match is None:
            print(f"FAIL  cannot read a version out of {name}")
            return 1

        built = match.group(1)
        if built != expected:
            print(f"FAIL  tagged {FAKE_TAG} but built version {built}")
            print("\nhatch-vcs is not reading the tag. Check [tool.hatch.version] in")
            print("bridge/pyproject.toml -- `raw-options.root` has to point at the")
            print("git root, which is the directory above it.")
            return 1

        print(f"PASS  tagging {FAKE_TAG} builds version {built}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
