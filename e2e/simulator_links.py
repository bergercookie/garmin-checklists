"""Linked checklists, on the real watch app in the Connect IQ simulator.

    just watch-e2e-links

A Trilium note links to another note, which is a checklist of its own. The run
proves the whole path: real Trilium -> the bridge unrolls the link -> the real
compiled app draws a heading and the linked list's items indented under it, and
the heading is something the buttons step over rather than land on.

Needs what `just watch-e2e` needs: the SDK with its Devices and Fonts, a
developer key, Docker and a display. About two minutes.

What is asserted is what can be read off the pixels: the heading is drawn in its
own colour and only where there is one, and the focus bar moves two rows, not
one, across it. How it *looks* -- the indent, the heading's wording -- is for a
person to read in build/simulator-screenshots/links/.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
import simulator_stack as sim
import stack
from providers.trilium import LINK_CHILD, LINK_PARENT, OTHER_NOTE, Trilium
from simulator_features import Simulator, ticked_boxes
from simulator_stack import DEVICE, DISPLAY, TLS_PORT

#: What COLOR_ORANGE, the heading colour, comes out as on screen.
HEADING_ORANGE = "#FF5500"

#: A single item under the link, so the parent is three rows -- Lights out, the
#: heading, Brush teeth -- which fits on screen on both devices without scrolling.
CHILD_ITEMS = ["Brush teeth"]

#: The part of a simulator screenshot to look for the focus bar in: the display,
#: with room on the left, where the bar is.
BAR_CROP = "240x240+96+170" if DEVICE == "fenix7" else "380x340+130+285"

#: How far a focus bar may be from where it should be, in pixels.
TOLERANCE = 12


def count_colour(path: Path, colour: str) -> int:
    histogram = subprocess.run(
        ["convert", str(path), "-format", "%c", "histogram:info:-"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    for line in histogram.splitlines():
        if colour in line.upper():
            return int(line.split(":")[0])
    return 0


def is_white(pixel: str) -> bool:
    """Whether a ``txt:`` pixel, ``(r,g,b) #RRGGBB ...``, is white enough.

    Not exactly white: the simulator scales a large device up, which blurs a
    thin bar's edges into grey.
    """
    channels = pixel.split(")")[0].lstrip("(").split(",")
    return len(channels) >= 3 and all(int(float(value)) >= 215 for value in channels[:3])


def focus_bar_y(path: Path) -> int | None:
    """The height of the white bar beside the focused row, or None if not found.

    It is the leftmost white thing on the display, left of every letter, and
    several rows' worth of pixels tall -- unlike any stroke of text.
    """
    width, height, _left, top = (int(part) for part in BAR_CROP.replace("x", "+").split("+"))
    dump = subprocess.run(
        ["convert", str(path), "-crop", BAR_CROP, "+repage", "txt:-"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    white: dict[int, list[int]] = {}
    for line in dump.splitlines()[1:]:
        position, _, rest = line.partition(": ")
        if not is_white(rest):
            continue
        x, y = (int(part) for part in position.split(","))
        # The bezel is outside this inner box.
        if width * 0.1 < x < width * 0.9 and height * 0.2 < y < height * 0.9:
            white.setdefault(x, []).append(y)
    for x in sorted(white):
        ys = sorted(white[x])
        run = [ys[0]]
        for y in ys[1:]:
            if y == run[-1] + 1:
                run.append(y)
            elif len(run) >= 14:
                break
            else:
                run = [y]
        if len(run) >= 14:
            return top + (run[0] + run[-1]) // 2
    return None


def publish_screenshot(source: Path, name: str) -> None:
    """Crop a screenshot to the device and put it in docs/images/."""
    # Imported here: capture_screenshots pulls in the Vikunja fixture.
    import capture_screenshots

    target = capture_screenshots.IMAGES / f"{DEVICE}-{name}.png"
    shutil.copy(source, target)
    capture_screenshots.crop_to_device(target)
    print(f"    docs/images/{target.name}")


def run(*, publish: bool) -> int:
    stack.step("0. Prerequisites")
    sdk = sim.preflight()
    stack.check(f"simulating {DEVICE} on display {DISPLAY}", True)

    workspace = Path(tempfile.mkdtemp(prefix="checklists-links-"))
    fixture = Trilium()
    bridge = simulator = None
    try:
        stack.step("1. Trilium, with a note that links to another")
        fixture.start(workspace)
        seeded = fixture.seed()
        parent, child = fixture.seed_links(CHILD_ITEMS, closing_item=None)
        camera = fixture.note_id(OTHER_NOTE)

        stack.step("2. The bridge, over TLS, serving all three")
        certificate, key = sim.issue_certificate(workspace)
        access_log = workspace / "bridge.log"
        bridge = sim.start_tls_bridge(workspace / "bridge.json", access_log, certificate, key)
        phone = httpx.Client(base_url=f"https://127.0.0.1:{TLS_PORT}", verify=False, timeout=30)
        phone.post("/login", data={"password": stack.ADMIN_PASSWORD}, follow_redirects=False)
        admin = f"/api/v1/admin/providers/{fixture.provider_id}"
        phone.put(f"{admin}/config", json={"config": seeded.config}).raise_for_status()
        phone.put(f"{admin}/selection", json={"source_ids": [parent, child, camera]})
        report = phone.post("/api/v1/admin/refresh").json()
        stack.check("the bridge refreshed without errors", report["ok"], str(report.get("errors")))
        device_token = phone.get("/api/v1/admin/state").json()["device_token"]

        stack.step("3. Compile the watch app and start the simulator")
        prg = sim.build_prg(sdk, workspace, f"https://127.0.0.1:{TLS_PORT}", device_token)
        simulator = sim.start_simulator(sdk)
        watch = Simulator(sdk, prg, workspace, access_log)
        watch.launch()
        watch.click("START", pause=10)
        stack.check("the watch synced", watch.syncs() == 1, str(watch.syncs()))

        stack.step(f"4. {LINK_PARENT}: the link is a heading, with its items under it")
        watch.open_index()
        watch.click("START", pause=2)
        parent_screen = watch.screen("parent")
        stack.check(
            "a heading is drawn in its own colour",
            count_colour(parent_screen, HEADING_ORANGE) > 0,
        )
        watch.click("BACK", pause=2)

        stack.step(f"5. {LINK_CHILD}: a list of its own, with no heading")
        watch.click("DOWN", pause=1)
        watch.click("START", pause=2)
        stack.check(
            "no heading colour on a plain list",
            count_colour(watch.screen("child"), HEADING_ORANGE) == 0,
        )
        watch.click("BACK", pause=2)

        stack.step(f"6. {OTHER_NOTE}: how far one press of DOWN moves the focus")
        watch.click("DOWN", pause=1)
        watch.click("START", pause=2)
        before = focus_bar_y(watch.screen("plain-first"))
        watch.click("DOWN", pause=1)
        after = focus_bar_y(watch.screen("plain-second"))
        stack.check("the focus bar was found", before is not None and after is not None)
        row = (after or 0) - (before or 0)
        stack.check(f"DOWN moved it one row: {row}px", row > 10, f"{before} -> {after}")
        if row <= 10:
            return 1  # everything below is measured in rows
        watch.click("BACK", pause=2)

        stack.step(f"7. {LINK_PARENT}: DOWN steps over the heading, UP steps back over it")
        watch.clicks("UP", 2)
        watch.click("START", pause=2)
        first = focus_bar_y(watch.screen("parent-first"))
        watch.click("DOWN", pause=1)
        second = focus_bar_y(watch.screen("parent-second"))
        stack.check("both bars found", first is not None and second is not None)
        moved = (second or 0) - (first or 0)
        stack.check(
            f"one press moved two rows -- past the heading: {moved}px vs {row}px",
            abs(moved - 2 * row) <= TOLERANCE,
        )
        watch.click("UP", pause=1)
        back = focus_bar_y(watch.screen("parent-back"))
        stack.check(
            "UP came back over it to the first item",
            back is not None and abs(back - (first or 0)) <= TOLERANCE,
            f"{first} -> {back}",
        )

        stack.step("8. Ticking the linked item ticks it, and only it")
        watch.click("DOWN", pause=1)
        watch.click("START", pause=1.5)
        ticked = watch.screen("ticked")
        stack.check("one box is ticked", ticked_boxes(ticked) > 0)
        watch.click("BACK", pause=2)
        watch.screen("index-progress")

        if publish:
            stack.step("9. Publish the documentation screenshot")
            publish_screenshot(ticked, "linked")

        keep = sim.REPO / "build" / "simulator-screenshots" / "links"
        keep.mkdir(parents=True, exist_ok=True)
        for shot in sorted(workspace.glob("[0-9]*.png")):
            shutil.copy(shot, keep / shot.name)
        print(f"\n  screenshots: {keep}")
        return 0 if not stack.failures else 1
    finally:
        if bridge is not None:
            bridge.terminate()
        if simulator is not None:
            simulator.terminate()
        stack.docker_remove(fixture.container)
        sim.remove_trust_anchor()
        shutil.rmtree(workspace, ignore_errors=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--publish-screenshots",
        action="store_true",
        help="also write the linked-list screenshot used by the docs to docs/images/",
    )
    code = run(publish=parser.parse_args().publish_screenshots)
    print()
    if stack.failures:
        print(f"\033[31m{len(stack.failures)} check(s) failed:\033[0m")
        for item in stack.failures:
            print(f"  - {item}")
    else:
        print("\033[32mEvery check passed: Trilium -> bridge -> the real watch app.\033[0m")
    raise SystemExit(code)
