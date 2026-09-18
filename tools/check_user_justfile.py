"""Check that an untracked `justfile.user` behaves the way it is advertised to.

Four claims are made about it in the justfile and the README, and each is easy
to break by editing the import line:

  * absent, it changes nothing;
  * present, its recipes join the list;
  * a name already used by the justfile is an error, not a silent override --
    otherwise `just lint` could quietly mean something else than it does in CI;
  * `justfile.user.example` is itself valid, and `justfile.user` is ignored by
    git so it can never be committed.

Everything runs against a copy in a temporary directory, so a `justfile.user`
you actually use is neither read nor disturbed.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
failures: list[str] = []


def check(description: str, condition: bool, detail: str = "") -> None:
    print(f"  {'PASS' if condition else 'FAIL'}  {description}")
    if not condition:
        failures.append(description)
        if detail:
            print(f"        {detail.strip()}")


def summary(directory: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "just",
            "--justfile",
            str(directory / "justfile"),
            "--working-directory",
            str(directory),
            "--summary",
        ],
        capture_output=True,
        text=True,
    )


def main() -> int:
    argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    ).parse_args()
    with tempfile.TemporaryDirectory(prefix="justfile-user-") as scratch:
        sandbox = Path(scratch)
        shutil.copy(REPO / "justfile", sandbox / "justfile")
        # The justfile imports just/*.just, and those imports are required, so a
        # sandbox holding only the root file fails to parse at all -- which used
        # to surface as an uncaught StopIteration below rather than a failure.
        shutil.copytree(REPO / "just", sandbox / "just")

        without = summary(sandbox)
        check("absent: the justfile still parses", without.returncode == 0, without.stderr)
        baseline = set(without.stdout.split())

        # Everything below is measured against `baseline`, so a sandbox that saw
        # only half the recipes would still "pass" while testing almost nothing.
        real = set(
            subprocess.run(
                ["just", "--summary"], cwd=REPO, capture_output=True, text=True, check=True
            ).stdout.split()
        )
        check(
            f"the sandbox sees all {len(real)} recipes, not a subset",
            baseline == real,
            f"missing from the sandbox: {sorted(real - baseline)}",
        )

        (sandbox / "justfile.user").write_text('zz-user-recipe:\n    @echo "hello"\n')
        with_user = summary(sandbox)
        check("present: it parses", with_user.returncode == 0, with_user.stderr)
        added = set(with_user.stdout.split()) - baseline
        check("present: the recipe joins the list", added == {"zz-user-recipe"}, str(added))

        clash = next((name for name in sorted(baseline) if name != "default"), "")
        if not clash:
            check("a recipe exists to test shadowing with", False, "the sandbox parsed nothing")
            return 1
        (sandbox / "justfile.user").write_text(f'{clash}:\n    @echo "shadowed"\n')
        collision = summary(sandbox)
        check(
            f"reusing {clash!r} is an error, not a silent override",
            collision.returncode != 0 and "redefined" in collision.stderr,
            collision.stderr or collision.stdout,
        )

        shutil.copy(REPO / "justfile.user.example", sandbox / "justfile.user")
        example = summary(sandbox)
        check("justfile.user.example is valid", example.returncode == 0, example.stderr)

    ignored = subprocess.run(
        ["git", "check-ignore", "justfile.user"], cwd=REPO, capture_output=True, text=True
    )
    check("justfile.user is ignored by git", ignored.returncode == 0)

    if failures:
        print(f"\n{len(failures)} check(s) failed", file=sys.stderr)
        return 1
    print("\njustfile.user behaves as documented")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
