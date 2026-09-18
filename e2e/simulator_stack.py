"""The same end-to-end chain, but with the real watch app.

Where full_stack.py drives a Python stand-in for the watch, this drives the
actual Monkey C application running in Garmin's Connect IQ simulator: real
Vikunja, real bridge, real compiled .prg, real HTTP from the device.

    just watch-e2e

Needs the Connect IQ SDK, its device definitions *and* its Fonts directory, a
developer key, Docker, and an X display (Xvfb is fine). See docs/testing.md.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stack
from providers.vikunja import Vikunja

#: These runs are about the watch app, so they stay on one provider.
_vikunja = Vikunja()

REPO = Path(__file__).resolve().parent.parent
DEVICE = os.environ.get("CIQ_DEVICE", "fenix7")
DISPLAY = os.environ.get("DISPLAY", ":99")
GARMIN_HOME = Path.home() / ".Garmin" / "ConnectIQ"

#: Where to click for each device's START button, in the simulator window.
#: Derived by eye once per device; every click asserts the screen changed, so a
#: wrong coordinate fails loudly instead of silently doing nothing.
#: Only BACK and START are needed; the simulator's keyboard mapping does not
#: cover them, so they are clicked on the device image.
START_BUTTON = {"fenix7": (378, 197), "descentg2": (588, 300)}
BACK_BUTTON = {"fenix7": (378, 400), "descentg2": (588, 600)}

#: The simulator's stand-in for the watch's filesystem. It keeps app settings
#: here, and a stored value beats the defaults compiled into the .prg -- so a
#: previous run would otherwise leave this one unpaired.
SIMULATOR_STATE_PATH = Path("/tmp/com.garmin.connectiq")

#: The watch will not talk to plain HTTP, and will not trust a certificate the
#: system does not, so the run mints one and installs it. Both facts cost a
#: while to find: HTTP fails with -1001 (SECURE_CONNECTION_REQUIRED) and an
#: untrusted certificate surfaces, unhelpfully, as an HTTP 404.
TLS_PORT = 8444
TRUST_ANCHOR_PATH = Path("/usr/local/share/ca-certificates/checklists-e2e.crt")


def sdk_path() -> Path:
    if os.environ.get("CIQ_SDK"):
        return Path(os.environ["CIQ_SDK"])
    configured = GARMIN_HOME / "current-sdk.cfg"
    if configured.exists():
        return Path(configured.read_text().strip())
    raise SystemExit("set CIQ_SDK, or install an SDK with the Connect IQ SDK Manager")


def preflight() -> Path:
    sdk = sdk_path()
    for description, path in (
        ("SDK", sdk / "bin" / "monkeyc"),
        ("simulator", sdk / "bin" / "simulator"),
        ("monkeydo", sdk / "bin" / "monkeydo"),
        (f"device definition for {DEVICE}", GARMIN_HOME / "Devices" / DEVICE),
        # Without this the app compiles and launches, then dies on its first
        # drawText with "Invalid Font Specified".
        ("Fonts directory", GARMIN_HOME / "Fonts"),
        ("developer key (set CIQ_KEY)", Path(os.environ.get("CIQ_KEY", "/nonexistent"))),
    ):
        stack.check(f"{description} present", path.exists(), str(path))
    # Everything below this line is a program on $PATH, not part of the SDK,
    # so a checkout missing one gets a clear preflight failure here instead of
    # a bare "<program>: command not found" mid-run: xdotool clicks on-screen
    # buttons (press()), import/convert (ImageMagick) capture and crop
    # screenshots (screenshot(), and capture_screenshots.py's own cropping),
    # and openssl/sudo mint and trust the certificate (issue_certificate).
    for program, needed_for in (
        ("xdotool", "clicking on-screen buttons"),
        ("import", "capturing a screenshot"),
        ("convert", "cropping a screenshot"),
        ("openssl", "minting the certificate"),
        ("sudo", "trusting the certificate system-wide"),
    ):
        stack.check(
            f"{program!r} present", shutil.which(program) is not None, f"needed for {needed_for}"
        )
    if stack.failures:
        raise SystemExit("missing prerequisites; see docs/testing.md")
    return sdk


def sudo(args: list[str], why: str) -> subprocess.CompletedProcess[bytes]:
    """Run a sudo command, telling the user what for and exactly what runs."""
    command = ["sudo", *args]
    print(f"  sudo: {why}\n    $ {' '.join(command)}")
    return subprocess.run(command, capture_output=True)


def issue_certificate(workspace: Path) -> tuple[Path, Path]:
    """Self-sign a certificate for 127.0.0.1 and add it to the system trust."""
    certificate, key = workspace / "cert.pem", workspace / "key.pem"
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-keyout",
            str(key),
            "-out",
            str(certificate),
            "-days",
            "3650",
            "-nodes",
            "-subj",
            "/CN=127.0.0.1",
            "-addext",
            "subjectAltName=IP:127.0.0.1,DNS:localhost",
        ],
        check=True,
        capture_output=True,
    )
    installed = sudo(
        ["cp", str(certificate), str(TRUST_ANCHOR_PATH)],
        "installing the self-signed certificate into the system trust store",
    )
    if installed.returncode == 0:
        sudo(["update-ca-certificates"], "refreshing the system CA bundle to pick it up")
    # Compared byte for byte, not merely "the file exists": a leftover anchor
    # from a previous run would otherwise make this pass while the certificate
    # actually being served is untrusted -- which surfaces as the confusing 404
    # this check exists to pre-empt.
    stack.check(
        "certificate installed in the system trust store",
        TRUST_ANCHOR_PATH.exists() and TRUST_ANCHOR_PATH.read_bytes() == certificate.read_bytes(),
        "needs sudo (will prompt if not already cached); "
        "without it the watch answers 404 for every request",
    )
    return certificate, key


def remove_trust_anchor() -> None:
    """Take the run's certificate back out of the machine's trust store.

    It is self-signed, valid for ten years, and its key was thrown away with the
    temporary directory. Leaving it installed means every developer and CI
    machine that ever ran this permanently trusts a key nobody holds.
    """
    if not TRUST_ANCHOR_PATH.exists():
        return
    sudo(
        ["rm", "-f", str(TRUST_ANCHOR_PATH)], "removing this run's certificate from the trust store"
    )
    sudo(["update-ca-certificates", "--fresh"], "refreshing the system CA bundle to match")


def start_tls_bridge(
    data_file: Path, log: Path, certificate: Path, key: Path
) -> subprocess.Popen[bytes]:
    environment = {
        **os.environ,
        "CHECKLISTS_ADMIN_PASSWORD": stack.ADMIN_PASSWORD,
        "CHECKLISTS_DATA_FILE": str(data_file),
        "CHECKLISTS_HOST": "127.0.0.1",
        "CHECKLISTS_PORT": str(TLS_PORT),
        "CHECKLISTS_PUBLIC_URL": f"https://127.0.0.1:{TLS_PORT}",
    }
    sink = log.open("wb")
    process = subprocess.Popen(
        [
            "uv",
            "run",
            "python",
            str(Path(__file__).parent / "tls_bridge.py"),
            str(certificate),
            str(key),
        ],
        cwd=REPO / "bridge",
        env=environment,
        stdout=sink,
        stderr=sink,
    )
    deadline = time.time() + 60
    while time.time() < deadline:
        try:
            httpx.get(f"https://127.0.0.1:{TLS_PORT}/healthz", verify=False, timeout=3)
            return process
        except httpx.HTTPError:
            time.sleep(1)
    raise TimeoutError("the TLS bridge did not come up")


def build_prg(sdk: Path, workspace: Path, bridge_url: str, device_token: str) -> Path:
    """Compile a throwaway build whose settings already point at the bridge.

    The simulator keeps app settings in a binary .SET file, so rather than
    reverse-engineer that, the pairing values are baked in as property defaults
    for this build only. The committed source is never touched.
    """
    source = workspace / "watch"
    shutil.copytree(REPO / "watch", source)
    properties = source / "resources" / "properties" / "properties.xml"
    properties.write_text(
        "<properties>\n"
        f'    <property id="bridgeUrl" type="string">{bridge_url}</property>\n'
        f'    <property id="deviceToken" type="string">{device_token}</property>\n'
        "</properties>\n"
    )
    output = workspace / f"checklists-{DEVICE}.prg"
    result = subprocess.run(
        [
            str(sdk / "bin" / "monkeyc"),
            "-o",
            str(output),
            "-f",
            str(source / "monkey.jungle"),
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
    noise = ("Picked up JAVA", "Invalid device id")
    messages = [
        line
        for line in (result.stdout + result.stderr).splitlines()
        if line.strip() and not any(skip in line for skip in noise)
    ]
    stack.check(
        f"{DEVICE} builds at type-check level 3",
        result.returncode == 0,
        "\n".join(messages),
    )
    return output


def simulator_env() -> dict[str, str]:
    environment = {**os.environ, "DISPLAY": DISPLAY}
    compat = os.environ.get("CIQ_COMPAT_LIBS")
    if compat:
        environment["LD_LIBRARY_PATH"] = compat
    return environment


def start_simulator(sdk: Path) -> subprocess.Popen[bytes]:
    shutil.rmtree(SIMULATOR_STATE_PATH, ignore_errors=True)
    process = subprocess.Popen(
        [str(sdk / "bin" / "simulator")],
        env=simulator_env(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    time.sleep(15)
    return process


def screenshot(name: str, workspace: Path) -> Path:
    path = workspace / name
    subprocess.run(
        ["import", "-window", "root", "-screen", str(path)],
        env={**os.environ, "DISPLAY": DISPLAY},
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["convert", str(path), "-trim", "+repage", str(path)], check=True, capture_output=True
    )
    return path


def press_start(workspace: Path, label: str) -> bool:
    return press(START_BUTTON, workspace, label)


def press_back(workspace: Path, label: str) -> bool:
    return press(BACK_BUTTON, workspace, label)


def press(button: dict[str, tuple[int, int]], workspace: Path, label: str) -> bool:
    """Click a device button; returns whether the screen changed."""
    before = screenshot(f"before-{label}.png", workspace).read_bytes()
    x, y = button[DEVICE]
    subprocess.run(
        ["xdotool", "mousemove", str(x), str(y), "click", "1"],
        env={**os.environ, "DISPLAY": DISPLAY},
        check=True,
        capture_output=True,
    )
    time.sleep(4)
    after = screenshot(f"after-{label}.png", workspace).read_bytes()
    return before != after


def run() -> int:
    stack.step("0. Prerequisites")
    sdk = preflight()
    stack.check(f"simulating {DEVICE} on display {DISPLAY}", True)

    workspace = Path(tempfile.mkdtemp(prefix="checklists-sim-"))
    bridge = None
    simulator = None
    try:
        stack.step("1. Vikunja")
        _vikunja.start(workspace)
        seeded = _vikunja.seed()
        stack.check("vikunja seeded with a read_all token and two projects", bool(seeded.config))

        stack.step("2. Bridge, over TLS")
        certificate, key = issue_certificate(workspace)
        access_log = workspace / "bridge.log"
        bridge = start_tls_bridge(workspace / "bridge.json", access_log, certificate, key)
        phone = httpx.Client(base_url=f"https://127.0.0.1:{TLS_PORT}", verify=False, timeout=30)
        phone.post("/login", data={"password": stack.ADMIN_PASSWORD}, follow_redirects=False)
        phone.put(
            f"/api/v1/admin/providers/{_vikunja.provider_id}/config",
            json={"config": seeded.config},
        )
        phone.put(
            f"/api/v1/admin/providers/{_vikunja.provider_id}/selection",
            json={"source_ids": [seeded.source_id]},
        )
        report = phone.post("/api/v1/admin/refresh").json()
        stack.check("bridge imported the dive checklist", report["ok"] and report["checklists"])
        device_token = phone.get("/api/v1/admin/state").json()["device_token"]

        stack.step("3. Compile the watch app, paired to this bridge")
        # The simulator reaches the host's loopback directly.
        prg = build_prg(sdk, workspace, f"https://127.0.0.1:{TLS_PORT}", device_token)

        stack.step("4. Launch it in the Connect IQ simulator")
        simulator = start_simulator(sdk)
        subprocess.Popen(
            [str(sdk / "bin" / "monkeydo"), str(prg), DEVICE],
            env=simulator_env(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        time.sleep(25)
        home = screenshot("01-home.png", workspace)
        stack.check("the app rendered its home screen", home.stat().st_size > 0)

        stack.step("5. Press START to sync")
        stack.check("the screen responded to START", press_start(workspace, "sync"))
        time.sleep(6)
        screenshot("02-after-sync.png", workspace)

        stack.step("6. The bridge saw the watch, not a stand-in")
        log = access_log.read_text(errors="replace")
        stack.check(
            "the watch fetched the index",
            # Per line: the path and a 200 anywhere in the whole log would also
            # be satisfied by a 401 on the index and a 200 on /healthz.
            any(
                "/api/v1/watch/lists?refresh=true" in line and " 200 " in line
                for line in log.splitlines()
            ),
            log[-400:],
        )
        # Connect IQ percent-encodes the ':' in a qualified id; the bridge
        # decodes it back, so both spellings count as a hit.
        source = seeded.source_id
        stack.check(
            "the watch fetched the checklist itself",
            f"/api/v1/watch/lists/vikunja:{source}" in log
            or f"/api/v1/watch/lists/vikunja%3A{source}" in log,
            log[-400:],
        )

        stack.step("7. Open the checklist on the watch")
        stack.check("START opened the checklist index", press_start(workspace, "index"))
        screenshot("03-index.png", workspace)
        stack.check("START opened the items", press_start(workspace, "items"))
        items = screenshot("04-items.png", workspace)

        stack.step("8. Tick an item")
        # Without this the whole no-leak assertion below is vacuous: it used to
        # pass on a watch that had never ticked anything, and would have passed
        # just as happily against an app that posted every tick to Vikunja.
        stack.check("START ticked an item", press_start(workspace, "tick"))
        screenshot("05-ticked.png", workspace)

        stack.step("9. The tick stayed on the watch")
        after_tick = access_log.read_text(errors="replace")
        writes = [
            line
            for line in after_tick.splitlines()
            if "/api/v1/watch" in line and '"GET ' not in line
        ]
        # The bridge's own log is the stronger check of the two: it catches a
        # leak even when Vikunja is unreachable, and even if the token it was
        # given happened to be read-only.
        stack.check("the watch made no non-GET call to the bridge", not writes, str(writes))

        untouched, detail = _vikunja.nothing_was_ticked(seeded.source_id)
        stack.check("no Vikunja task was marked done", untouched, detail)

        keep = REPO / "build" / "simulator-screenshots"
        keep.mkdir(parents=True, exist_ok=True)
        for shot in sorted(workspace.glob("0*.png")):
            shutil.copy(shot, keep / shot.name)
        print(f"\n  screenshots: {keep}")
        print(f"  last frame:  {items.name}")
        return 0 if not stack.failures else 1
    finally:
        if bridge is not None:
            bridge.terminate()
        if simulator is not None:
            simulator.terminate()
        stack.docker_remove(_vikunja.container)
        remove_trust_anchor()
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
        print("\033[32mEvery check passed: Vikunja -> bridge -> the real watch app.\033[0m")
    raise SystemExit(code)
