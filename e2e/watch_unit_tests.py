"""Run the Monkey C unit tests (watch/tests/) in the Connect IQ simulator.

    just watch-test

They need the simulator rather than a plain interpreter because they exercise
the real Storage and clock. They write to the simulator's storage, so the run
starts from an empty state directory, as the end-to-end runs do.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import simulator_stack as sim
import stack
from simulator_stack import DEVICE


def run() -> int:
    stack.step("0. Prerequisites")
    sdk = sim.preflight()

    workspace = Path(tempfile.mkdtemp(prefix="checklists-unit-"))
    simulator = None
    try:
        stack.step("1. Compile the app with watch/tests/")
        prg = workspace / "tests.prg"
        built = subprocess.run(
            [
                str(sdk / "bin" / "monkeyc"),
                "--unit-test",
                "-o",
                str(prg),
                "-f",
                str(sim.REPO / "watch" / "tests.jungle"),
                "-y",
                os.environ["CIQ_KEY"],
                "-d",
                DEVICE,
                "-w",
                "-l",
                "3",
            ],
            capture_output=True,
            text=True,
        )
        stack.check(f"{DEVICE} builds with the tests", built.returncode == 0, built.stdout[-800:])

        stack.step("2. Run them in the simulator")
        simulator = sim.start_simulator(sdk)
        ran = subprocess.run(
            [str(sdk / "bin" / "monkeydo"), str(prg), DEVICE, "-t"],
            env=sim.simulator_env(),
            capture_output=True,
            text=True,
            timeout=300,
        )
        for line in ran.stdout.splitlines():
            if line.strip() and "Picked up JAVA" not in line:
                print(f"    {line}")
        summary = re.search(r"PASSED \(passed=(\d+), failed=(\d+), errors=(\d+)\)", ran.stdout)
        stack.check("the run reported a summary", summary is not None)
        if summary:
            passed, failed, errors = map(int, summary.groups())
            stack.check(
                f"{passed} tests passed, none failed", passed > 0 and failed == 0 and errors == 0
            )
        return 0 if not stack.failures else 1
    finally:
        if simulator is not None:
            simulator.terminate()
        shutil.rmtree(workspace, ignore_errors=True)


if __name__ == "__main__":
    argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    ).parse_args()
    code = run()
    print()
    if stack.failures:
        print(f"\033[31m{len(stack.failures)} check(s) failed:\033[0m")
        for item in stack.failures:
            print(f"  - {item}")
    else:
        print("\033[32mAll the watch unit tests passed.\033[0m")
    raise SystemExit(code)
