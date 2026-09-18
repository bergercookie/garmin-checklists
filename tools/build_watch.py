"""Compile the watch app, optionally with its pairing settings already filled in.

Normally the bridge URL and device token are typed once on the phone, in Garmin
Connect. When that is not an option -- no phone to hand, or Garmin Connect
misbehaving on the app's settings page -- they can be compiled in as the
property defaults instead:

    BRIDGE_URL=https://checklists.example.com DEVICE_TOKEN=K7QF-2M9X-PLDR \\
        just watch-build

The committed sources are never modified: the build runs from a copy.

Two things to know before relying on it:

  * The device token ends up inside the .prg. Treat that build as a secret, and
    rotate the token on the bridge if it gets away from you.
  * Defaults only apply when the watch has no stored settings for the app yet.
    If a previous install left GARMIN/APPS/SETTINGS/<APP>.SET behind, delete it
    (or uninstall the app) or the empty stored values win.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from xml.sax.saxutils import escape

REPO = Path(__file__).resolve().parent.parent
DEFAULT_DEVICE = "fenix7"


def properties_xml(bridge_url: str, device_token: str) -> str:
    return (
        "<properties>\n"
        f'    <property id="bridgeUrl" type="string">{escape(bridge_url)}</property>\n'
        f'    <property id="deviceToken" type="string">{escape(device_token)}</property>\n'
        "</properties>\n"
    )


def main() -> int:
    argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    ).parse_args()
    device = os.environ.get("CIQ_DEVICE", DEFAULT_DEVICE)
    key = os.environ.get("CIQ_KEY")
    if not key:
        print("set CIQ_KEY to your developer key (.der)", file=sys.stderr)
        return 2

    bridge_url = os.environ.get("BRIDGE_URL", "").strip()
    device_token = os.environ.get("DEVICE_TOKEN", "").strip()
    paired = bool(bridge_url or device_token)

    output = REPO / "build" / f"checklists-{device}.prg"
    output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="checklists-build-") as scratch:
        source = Path(scratch) / "watch"
        shutil.copytree(REPO / "watch", source)
        if paired:
            (source / "resources" / "properties" / "properties.xml").write_text(
                properties_xml(bridge_url, device_token)
            )
            print(f"  baking in bridgeUrl={bridge_url or '(unset)'} and a device token")
        result = subprocess.run(
            [
                "monkeyc",
                "-o",
                str(output),
                "-f",
                str(source / "monkey.jungle"),
                "-y",
                key,
                "-d",
                device,
                "-w",
                "-l",
                "3",
            ],
            capture_output=True,
            text=True,
        )

    for line in (result.stdout + result.stderr).splitlines():
        if line.strip() and "Picked up JAVA" not in line:
            print(line)
    if result.returncode == 0:
        print(f"\n  {output}")
        if paired:
            print("  Contains your device token. See tools/build_watch.py before sharing it.")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
