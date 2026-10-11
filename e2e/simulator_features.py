"""Two watch features, driven through the real app in the Connect IQ simulator.

    just watch-e2e-features

1. **Sync from every screen.** Long-pressing UP (the MENU key) syncs from the
   home screen, the checklist index, a checklist, the settings and the
   daily-clear time editor alike, and lands back on the home screen.
2. **The daily clear.** The time is set on the watch itself, in Settings. Before
   it the ticks survive a restart; once it has passed, the next start finds
   every list unticked, and without touching the bridge; and it happens once,
   not on every start after.

It uses the bridge's own checklists, so it needs no Docker -- only what
`just watch-e2e` needs from the SDK -- and takes up to six minutes, because the
time picker works in steps of five minutes and the clear has to be waited for.

The simulator has no input but a mouse here, so buttons are clicked on the
device image and a long press is a button held down. Every step asserts
something observable -- the bridge's own access log, or the pixels on screen --
rather than that a click was sent.
"""

from __future__ import annotations

import argparse
import datetime
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
import simulator_stack as sim
import stack
from simulator_stack import DEVICE, DISPLAY, TLS_PORT

#: Where to click each device's buttons in the simulator window; see
#: simulator_stack.py. The checks below fail loudly if one is off.
BUTTONS = {
    device: {
        "START": sim.START_BUTTON[device],
        "BACK": sim.BACK_BUTTON[device],
        "UP": sim.UP_BUTTON[device],
        "DOWN": sim.DOWN_BUTTON[device],
    }
    for device in sim.START_BUTTON
}

#: How long the MENU key is held. Longer than the platform's long-press
#: threshold, shorter than anything that would be taken for a stuck button.
HOLD_SECONDS = 1.5

#: The editor's minute field moves in steps of this many minutes.
MINUTE_STEP = 5
#: The time the editor opens on when nothing has been set: the 03:00 default.
DEFAULT_HOUR = 3

LISTS = {"Dive kit": ["Mask", "Fins", "Regulator", "Computer"], "Camping": ["Tent", "Stove", "Map"]}
#: Rows on the index above Settings: the two checklists, then "Sync now".
INDEX_ROWS_BEFORE_SETTINGS = len(LISTS) + 1
#: Settings rows above "Clear at": "Show clock" and "Clear daily".
SETTINGS_ROWS_BEFORE_CLEAR_AT = 2

#: The display within a screenshot of the simulator window, per device.
FACE_CROP = "240x240+96+170" if DEVICE == "fenix7" else "300x300+176+305"

#: What COLOR_GREEN, the tick box, comes out as on screen.
TICK_GREEN = "#00FF00"


class Simulator:
    """The running app, and the few things a test does to it."""

    def __init__(self, sdk: Path, prg: Path, workspace: Path, access_log: Path) -> None:
        self.sdk = sdk
        self.prg = prg
        self.workspace = workspace
        self.access_log = access_log
        self.shots = 0
        # START on the home screen goes straight into the checklist last opened,
        # until a sync forgets it.
        self.remembers_checklist = False

    def launch(self) -> None:
        """Start the app, as picking it from the watch's menu would."""
        # The app's own System.println output, for working out what a failure was.
        console = (self.workspace / "console.log").open("ab")
        subprocess.Popen(
            [str(self.sdk / "bin" / "monkeydo"), str(self.prg), DEVICE],
            env=sim.simulator_env(),
            stdout=console,
            stderr=console,
            start_new_session=True,
        )
        time.sleep(15)

    def screen(self, label: str) -> Path:
        self.shots += 1
        return sim.screenshot(f"{self.shots:02d}-{label}.png", self.workspace)

    def click(self, button: str, pause: float = 1.0) -> None:
        x, y = BUTTONS[DEVICE][button]
        self._mouse(["mousemove", str(x), str(y), "click", "1"], pause)

    def clicks(self, button: str, count: int) -> None:
        for _ in range(count):
            self.click(button, pause=0.5)
        time.sleep(1)

    def hold_menu(self) -> None:
        """Long-press UP: the MENU key. It syncs, which forgets the last checklist."""
        self.remembers_checklist = False
        x, y = BUTTONS[DEVICE]["UP"]
        self._mouse(["mousemove", str(x), str(y), "mousedown", "1"], HOLD_SECONDS)
        self._mouse(["mouseup", "1"], 1.0)

    def _mouse(self, arguments: list[str], pause: float) -> None:
        subprocess.run(
            ["xdotool", *arguments],
            env={**os.environ, "DISPLAY": DISPLAY},
            check=True,
            capture_output=True,
        )
        time.sleep(pause)

    def shows(self, picture: Path, within: float = 10.0) -> bool:
        """Whether the display comes to match picture, allowing for slow redraws."""
        deadline = time.time() + within
        while True:
            if same_picture(self.screen("after-back"), picture):
                return True
            if time.time() > deadline:
                return False
            time.sleep(1)

    def syncs(self) -> int:
        """How many times the watch has asked the bridge for the index."""
        log = self.access_log.read_text(errors="replace")
        return sum(
            1
            for line in log.splitlines()
            if "/api/v1/watch/lists?refresh=true" in line and " 200 " in line
        )

    # -- Navigation, from the home screen ---------------------------------

    def open_index(self) -> None:
        self.click("START", pause=2)
        if self.remembers_checklist:
            # It opened that checklist over the index; BACK reveals the index.
            self.click("BACK", pause=1.5)

    def open_first_checklist(self) -> None:
        self.open_index()
        self.click("START", pause=2)
        self.remembers_checklist = True

    def open_settings(self) -> None:
        self.open_index()
        self.clicks("DOWN", INDEX_ROWS_BEFORE_SETTINGS)
        self.click("START", pause=2)

    def open_time_editor(self) -> None:
        self.open_settings()
        self.clicks("DOWN", SETTINGS_ROWS_BEFORE_CLEAR_AT)
        self.click("START", pause=2)

    def exit_app(self, depth: int) -> None:
        """BACK out of depth screens, then out of the app itself."""
        for _ in range(depth + 1):
            self.click("BACK", pause=1.5)


def ticked_boxes(path: Path) -> int:
    """How many pixels of the tick-box green are in a screenshot."""
    histogram = subprocess.run(
        ["convert", str(path), "-format", "%c", "histogram:info:-"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    for line in histogram.splitlines():
        if TICK_GREEN in line.upper():
            return int(line.split(":")[0])
    return 0


def watch_face(path: Path) -> bytes:
    """Just the display: the simulator's status bar changes with memory use."""
    return subprocess.run(
        ["convert", str(path), "-crop", FACE_CROP, "+repage", "png:-"],
        check=True,
        capture_output=True,
    ).stdout


def same_picture(first: Path, second: Path) -> bool:
    return watch_face(first) == watch_face(second)


def sync_from_every_screen(watch: Simulator) -> None:
    stack.step("4. Home screen: the first sync, then START opens the lists")
    first_run = watch.screen("first-run")
    watch.click("START", pause=8)
    stack.check("the first sync reached the bridge", watch.syncs() == 1, str(watch.syncs()))
    watch.exit_app(0)
    launcher = watch.screen("launcher")
    stack.check("BACK on the home screen leaves the app", not same_picture(launcher, first_run))

    # Each place: how to get there from the home screen.
    places = {
        "the checklist index": watch.open_index,
        "a checklist": watch.open_first_checklist,
        "the settings": watch.open_settings,
        "the clear-time editor": watch.open_time_editor,
    }
    for number, (name, navigate) in enumerate(places.items(), start=5):
        stack.step(f"{number}. Long-press UP on {name}")
        watch.launch()
        navigate()
        before = watch.syncs()
        watch.hold_menu()
        time.sleep(8)
        stack.check(
            f"the watch synced from {name}",
            watch.syncs() == before + 1,
            f"{before} -> {watch.syncs()}",
        )
        # One BACK on the home screen exits the app. If any screen had been left
        # open under the sync, it would pop that instead.
        watch.click("BACK", pause=2)
        stack.check(
            "it landed on the home screen: the next BACK left the app",
            watch.shows(launcher),
        )


def sync_clears_ticks_from_a_checklist(watch: Simulator) -> None:
    stack.step("9. A sync from inside a checklist drops its ticks")
    watch.launch()
    watch.open_first_checklist()
    watch.click("START", pause=1.5)
    stack.check("an item is ticked", ticked_boxes(watch.screen("ticked")) > 0)
    watch.hold_menu()
    time.sleep(8)
    watch.open_first_checklist()
    stack.check(
        "the same checklist is unticked after the sync", ticked_boxes(watch.screen("fresh")) == 0
    )
    watch.exit_app(2)


def target_time() -> tuple[int, int, datetime.datetime]:
    """The next five-minute mark that is at least 100 seconds away."""
    soonest = datetime.datetime.now() + datetime.timedelta(seconds=100)
    minutes = soonest.hour * 60 + soonest.minute + 1
    total = -(-minutes // MINUTE_STEP) * MINUTE_STEP
    if total >= 24 * 60:
        raise SystemExit("too close to midnight to schedule a clear for today; run it again later")
    target = soonest.replace(hour=total // 60, minute=total % 60, second=0, microsecond=0)
    return total // 60, total % 60, target


def daily_clear(watch: Simulator) -> None:
    hour, minute, target = target_time()
    stack.step(f"10. Set the clear time to {hour:02d}:{minute:02d} in Settings")
    watch.launch()
    watch.open_time_editor()
    # The editor opens on the 03:00 default; UP is one step later.
    watch.clicks("UP", (hour - DEFAULT_HOUR) % 24)
    watch.click("START", pause=1)
    watch.clicks("UP", minute // MINUTE_STEP)
    watch.screen("editor")
    watch.click("START", pause=2)
    watch.screen("settings-after-save")
    # Back on the index, with Settings -- the row just used -- still focused.
    watch.click("BACK", pause=2)
    watch.clicks("UP", INDEX_ROWS_BEFORE_SETTINGS)

    stack.step("11. Tick an item, and leave the app")
    watch.click("START", pause=2)
    watch.click("START", pause=1.5)
    watch.remembers_checklist = True
    stack.check("an item is ticked", ticked_boxes(watch.screen("ticked-before")) > 0)
    syncs = watch.syncs()
    watch.exit_app(2)

    stack.step(f"12. Before {hour:02d}:{minute:02d}: the ticks survive a restart")
    watch.launch()
    stack.check(
        "the app reopened on the checklist, tick intact",
        ticked_boxes(watch.screen("before-time")) > 0,
    )
    stack.check("it was before the set time", datetime.datetime.now() < target, str(target))
    watch.exit_app(2)

    stack.step(f"13. Wait for {hour:02d}:{minute:02d}")
    wait = (target - datetime.datetime.now()).total_seconds() + 15
    print(f"    {max(wait, 0):.0f}s", flush=True)
    time.sleep(max(wait, 0))

    stack.step("14. After it: the next start finds every list unticked")
    watch.launch()
    watch.screen("after-time-home")
    watch.click("START", pause=2)
    stack.check(
        "the checklist, opened from home, is unticked",
        ticked_boxes(watch.screen("after-time")) == 0,
    )
    stack.check(
        "the clear did not sync with the bridge", watch.syncs() == syncs, str(watch.syncs())
    )

    stack.step("15. It clears once, not on every start")
    watch.click("START", pause=1.5)
    stack.check("an item is ticked again", ticked_boxes(watch.screen("ticked-after")) > 0)
    watch.exit_app(2)
    watch.launch()
    stack.check(
        "the new tick survived a restart",
        ticked_boxes(watch.screen("second-restart")) > 0,
    )
    watch.exit_app(2)


def run() -> int:
    stack.step("0. Prerequisites")
    sdk = sim.preflight()
    stack.check(f"simulating {DEVICE} on display {DISPLAY}", DEVICE in BUTTONS)

    workspace = Path(tempfile.mkdtemp(prefix="checklists-features-"))
    bridge = simulator = None
    try:
        stack.step("1. A bridge with two checklists of its own")
        certificate, key = sim.issue_certificate(workspace)
        access_log = workspace / "bridge.log"
        bridge = sim.start_tls_bridge(workspace / "bridge.json", access_log, certificate, key)
        phone = httpx.Client(base_url=f"https://127.0.0.1:{TLS_PORT}", verify=False, timeout=30)
        phone.post("/login", data={"password": stack.ADMIN_PASSWORD}, follow_redirects=False)
        for name, items in LISTS.items():
            created = phone.post("/api/v1/admin/local/checklists", json={"name": name})
            phone.put(
                f"/api/v1/admin/local/checklists/{created.json()['id']}", json={"items": items}
            ).raise_for_status()
        stack.check("the bridge holds both", phone.post("/api/v1/admin/refresh").json()["ok"])
        device_token = phone.get("/api/v1/admin/state").json()["device_token"]

        stack.step("2. Compile the watch app, paired to it")
        prg = sim.build_prg(sdk, workspace, f"https://127.0.0.1:{TLS_PORT}", device_token)

        stack.step("3. Start the simulator")
        simulator = sim.start_simulator(sdk)
        watch = Simulator(sdk, prg, workspace, access_log)
        watch.launch()

        sync_from_every_screen(watch)
        sync_clears_ticks_from_a_checklist(watch)
        daily_clear(watch)

        keep = sim.REPO / "build" / "simulator-screenshots" / "features"
        keep.mkdir(parents=True, exist_ok=True)
        for shot in sorted(workspace.glob("[0-9]*.png")):
            shutil.copy(shot, keep / shot.name)
        shutil.copy(workspace / "console.log", keep / "console.log")
        print(f"\n  screenshots: {keep}")
        return 0 if not stack.failures else 1
    finally:
        if bridge is not None:
            bridge.terminate()
        if simulator is not None:
            simulator.terminate()
        sim.remove_trust_anchor()
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
        print("\033[32mEvery check passed: both features, in the real app.\033[0m")
    raise SystemExit(code)
