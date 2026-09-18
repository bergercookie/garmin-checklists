#!/usr/bin/env python3
"""Drive the web UI in a real browser and check it works.

Worth its weight: this caught a `Referrer-Policy: no-referrer` header that made
Chrome send `Origin: null` on the sign-in form, which the bridge's own CSRF
check then refused -- sign-in was broken in every real browser while the whole
httpx-based suite stayed green, because httpx implements no referrer policy.

Skipped cleanly when Playwright or a browser is missing, so it never blocks a
checkout that does not want a 100MB browser. Run it with `just check-ui`.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parent.parent
PORT = 8401
PASSWORD = "ui-check-password"
#: Where Playwright's browsers live in this project's container image.
BROWSER = Path(os.environ.get("CHROMIUM", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"))

failures: list[str] = []


def check(description: str, condition: bool, detail: str = "") -> None:
    print(f"  {'PASS' if condition else 'FAIL'}  {description}", flush=True)
    if not condition:
        failures.append(description)
        if detail:
            print(f"        {detail}", flush=True)


def start_bridge(data_file: Path) -> subprocess.Popen[bytes]:
    environment = {
        **os.environ,
        "CHECKLISTS_ADMIN_PASSWORD": PASSWORD,
        "CHECKLISTS_DATA_FILE": str(data_file),
        "CHECKLISTS_HOST": "127.0.0.1",
        "CHECKLISTS_PORT": str(PORT),
        "CHECKLISTS_PUBLIC_URL": f"http://127.0.0.1:{PORT}",
    }
    process = subprocess.Popen(
        ["uv", "run", "checklists-bridge"],
        cwd=REPO / "bridge",
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.time() + 60
    while time.time() < deadline:
        try:
            if httpx.get(f"http://127.0.0.1:{PORT}/healthz", timeout=2).status_code == 200:
                return process
        except httpx.HTTPError:
            time.sleep(1)
    raise TimeoutError("the bridge did not come up")


def seed_a_local_checklist() -> None:
    """So one tile has something to show besides "not connected"."""
    api = httpx.Client(base_url=f"http://127.0.0.1:{PORT}", timeout=20)
    signed_in = api.post("/login", data={"password": PASSWORD}, follow_redirects=False)
    api.headers["Cookie"] = signed_in.headers["set-cookie"].split(";")[0]
    api.headers["Origin"] = f"http://127.0.0.1:{PORT}"
    api.post("/api/v1/admin/local/checklists", json={"name": "Packing"})


def main() -> int:
    argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    ).parse_args()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("SKIP  playwright is not installed (uv sync --group dev)")
        return 0
    if not BROWSER.exists():
        print(f"SKIP  no browser at {BROWSER}; set CHROMIUM to one")
        return 0

    workspace = Path(tempfile.mkdtemp(prefix="checklists-ui-"))
    bridge = start_bridge(workspace / "bridge.json")
    try:
        seed_a_local_checklist()
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                args=["--no-sandbox"], executable_path=str(BROWSER)
            )
            # A phone, because that is where this page is used.
            page = browser.new_page(viewport={"width": 430, "height": 900})
            problems: list[str] = []
            page.on("pageerror", lambda error: problems.append(str(error)))

            page.goto(f"http://127.0.0.1:{PORT}/login")
            page.fill("#password", PASSWORD)
            page.click("button[type=submit]")
            # The real browser sign-in, which is the thing that was broken.
            page.wait_for_selector(".provider-tile", timeout=15000)
            check("signing in from a real browser works", True)

            tiles = page.query_selector_all(".provider-tile")
            check(f"every provider has a tile, got {len(tiles)}", len(tiles) >= 3)
            for tile in tiles:
                name_el = tile.query_selector(".provider-name")
                art_el = tile.query_selector("img.provider-art")
                assert name_el is not None
                assert art_el is not None
                name = name_el.inner_text()
                box = art_el.bounding_box()
                check(
                    f"{name!r} shows a picture",
                    box is not None and box["width"] > 10 and box["height"] > 10,
                    str(box),
                )

            # Keyboard only: the tiles are buttons, so they must focus and fire.
            focused = ""
            for _ in range(14):
                page.keyboard.press("Tab")
                focused = str(page.evaluate("document.activeElement.className"))
                if "provider-tile" in focused:
                    break
            check("a tile can be reached with Tab", "provider-tile" in focused, focused)
            page.keyboard.press("Enter")
            page.wait_for_selector("#provider-sheet[open]", timeout=5000)
            check("Enter opens that provider's settings", True)
            page.click("#sheet-close")

            page.click(".provider-tile:has-text('Trilium')")
            page.wait_for_selector("#provider-sheet[open]")
            labels = [item.inner_text() for item in page.query_selector_all("#sheet-body label")]
            check(
                f"the Trilium form is built from the registry: {labels}",
                {"Trilium URL", "ETAPI token", "Which notes"} <= set(labels),
            )
            check("no uncaught JavaScript errors", not problems, str(problems[:3]))
            browser.close()
    finally:
        bridge.terminate()

    if failures:
        print(f"\n{len(failures)} check(s) failed.")
        return 1
    print("\nThe web UI works in a real browser.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
