#!/usr/bin/env python3
"""Fail unless the installed package version matches the git tag being released.

hatch-vcs derives the version from `git describe`, so the two agree by
construction -- unless the checkout is shallow, the tag was never fetched, or
the working tree is dirty, in which case you get something like
`1.2.1.dev4+g1a2b3cd` and would otherwise publish an image tagged `1.2.0`
containing a build that does not call itself that.

Usage: `just check-tag v1.2.0`, which the release workflow runs before it
publishes anything.
"""

from __future__ import annotations

import argparse
import sys

from checklists_bridge.config import VERSION


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("tag", help="the git tag being released, e.g. v1.2.0")
    args = parser.parse_args(argv[1:])

    expected = args.tag.removeprefix("v")
    if expected == VERSION:
        print(f"PASS  tag {args.tag} and package version {VERSION} agree")
        return 0

    print(f"FAIL  tag {args.tag} wants version {expected}, but the package says {VERSION}")
    if "dev" in VERSION or "+" in VERSION:
        print(
            "\nThat is a development version, which means the build could not see the "
            "tag.\nIn CI, check out with `fetch-depth: 0` and make sure the tag was "
            "pushed;\nlocally, commit or stash your changes first."
        )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
