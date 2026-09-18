"""Regenerate the screenshots used in the documentation.

Runs the same stack as simulator_stack.py -- real Vikunja, real bridge, the real
watch app in the Connect IQ simulator -- then walks the UI and crops each frame
down to the device. The result is committed to docs/images/, so the docs always
show the app as it actually renders rather than as it once did.

    just screenshots            # fenix7
    CIQ_DEVICE=descentg2 just screenshots

Same prerequisites as `just watch-e2e`; see docs/testing.md.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

# The sibling harness modules and tools/ are not importable packages.
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import simulator_stack as sim
import stack
from providers.vikunja import Vikunja
from simulator_stack import DEVICE, TLS_PORT
from watch_fingerprint import source_fingerprint

#: These runs are about the watch app, so they stay on one provider.
_vikunja = Vikunja()

REPO = Path(__file__).resolve().parent.parent
IMAGES = REPO / "docs" / "images"

#: The device sits in a white surround below the menu bar. Crop that away, then
#: let a fuzzy trim remove whatever white is left around the watch body.
#: The simulator window is the device on a white field, with a menu bar above,
#: a status bar below and a black gutter to the right. Cut those away, then let
#: a fuzzy trim take the remaining white margin down to the watch body.
#: Width the published images are downscaled to (only if they are wider).
DOC_WIDTH = 520

CHROME = {
    # device: (width, height, left, top) of the white field holding the watch
    "fenix7": (400, 545, 0, 26),
    "descentg2": (646, 830, 0, 26),
}


def crop_to_device(path: Path) -> None:
    width, height, left, top = CHROME[DEVICE]
    subprocess.run(
        [
            "convert",
            str(path),
            "-crop",
            f"{width}x{height}+{left}+{top}",
            "+repage",
            "-bordercolor",
            "white",
            "-border",
            "1",
            "-fuzz",
            "12%",
            "-trim",
            "+repage",
            # The docs render these around 250px wide; shipping 650px of
            # lossless screenshot in the repository is not worth it.
            "-resize",
            f"{DOC_WIDTH}>",
            "-colors",
            "256",
            "-strip",
            str(path),
        ],
        check=True,
        capture_output=True,
    )


def capture(name: str, workspace: Path) -> Path:
    raw = sim.screenshot(f"raw-{name}.png", workspace)
    crop_to_device(raw)
    return raw


def run() -> int:
    stack.step("0. Prerequisites")
    sdk = sim.preflight()

    workspace = Path(tempfile.mkdtemp(prefix="checklists-shots-"))
    bridge = simulator = None
    try:
        stack.step("1. A bridge with two checklists to show")
        _vikunja.start(workspace)
        seeded = _vikunja.seed()
        certificate, key = sim.issue_certificate(workspace)
        bridge = sim.start_tls_bridge(
            workspace / "bridge.json", workspace / "bridge.log", certificate, key
        )
        phone = httpx.Client(base_url=f"https://127.0.0.1:{TLS_PORT}", verify=False, timeout=30)
        phone.post("/login", data={"password": stack.ADMIN_PASSWORD}, follow_redirects=False)
        phone.put(
            f"/api/v1/admin/providers/{_vikunja.provider_id}/config",
            json={"config": seeded.config},
        )
        # Both projects, so the index screenshot has more than one row.
        phone.put(
            f"/api/v1/admin/providers/{_vikunja.provider_id}/selection",
            json={"source_ids": seeded.all_source_ids},
        )
        stack.check("two checklists imported", phone.post("/api/v1/admin/refresh").json()["ok"])
        device_token = phone.get("/api/v1/admin/state").json()["device_token"]

        stack.step("2. Build and launch")
        prg = sim.build_prg(sdk, workspace, f"https://127.0.0.1:{TLS_PORT}", device_token)
        simulator = sim.start_simulator(sdk)
        subprocess.Popen(
            [str(sdk / "bin" / "monkeydo"), str(prg), DEVICE],
            env=sim.simulator_env(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        time.sleep(25)

        stack.step("3. Walk the screens")
        unpaired = capture("01-first-run", workspace)
        stack.check("first run captured", sim.press_start(workspace, "sync"))
        time.sleep(8)
        home = capture("02-home", workspace)

        stack.check("index opened", sim.press_start(workspace, "index"))
        index_before = capture("03-index", workspace)

        stack.check("items opened", sim.press_start(workspace, "items"))
        items = capture("04-items", workspace)

        stack.check("item ticked", sim.press_start(workspace, "tick"))
        ticked = capture("05-ticked", workspace)

        stack.check("back returned to the index", sim.press_back(workspace, "back"))
        index_after = capture("06-index-progress", workspace)

        stack.step("4. Publish")
        IMAGES.mkdir(parents=True, exist_ok=True)
        published = {
            f"{DEVICE}-first-run.png": unpaired,
            f"{DEVICE}-home.png": home,
            f"{DEVICE}-index.png": index_before,
            f"{DEVICE}-checklist.png": items,
            f"{DEVICE}-checklist-ticked.png": ticked,
            f"{DEVICE}-index-progress.png": index_after,
        }
        for name, source in published.items():
            shutil.copy(source, IMAGES / name)
            print(f"    docs/images/{name}")
        if stack.failures:
            # The fingerprint is a claim that these images match these sources.
            # A run that failed half way has no business making it: the check
            # would then report the docs as current over stale or wrong images.
            return 1
        (IMAGES / "watch-source.sha256").write_text(source_fingerprint() + "\n")
        return 0
    finally:
        if bridge is not None:
            bridge.terminate()
        if simulator is not None:
            simulator.terminate()
        stack.docker_remove(_vikunja.container)
        shutil.rmtree(workspace, ignore_errors=True)


if __name__ == "__main__":
    argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    ).parse_args()
    code = run()
    print()
    if stack.failures:
        print(f"\033[31m{len(stack.failures)} step(s) failed:\033[0m")
        for item in stack.failures:
            print(f"  - {item}")
    else:
        print("\033[32mScreenshots refreshed in docs/images/.\033[0m")
    raise SystemExit(code)
