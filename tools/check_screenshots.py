"""Warn when docs/images is older than the watch sources.

Never fails: regenerating the screenshots needs the Connect IQ SDK, which not
every checkout has, so this reports it and exits with 0. See docs/testing.md.
"""

from __future__ import annotations

import argparse
import os
import sys

from watch_fingerprint import FINGERPRINT, source_fingerprint


def warn(message: str) -> None:
    # Rendered as an annotation on GitHub, plain text anywhere else.
    print(f"::warning::{message}" if os.environ.get("GITHUB_ACTIONS") else f"warning: {message}")


def main() -> int:
    argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    ).parse_args()
    if not FINGERPRINT.exists():
        warn("no screenshot fingerprint recorded; run 'just screenshots'")
        return 0
    if FINGERPRINT.read_text().strip() == source_fingerprint():
        print("docs/images matches the current watch sources")
        return 0
    warn("watch/ changed since the screenshots were taken; run 'just screenshots'")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
    raise SystemExit(main())
