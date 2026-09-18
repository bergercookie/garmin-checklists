"""Shared harness for an end-to-end run: nothing here is specific to one provider.

Everything here is real: the bridge is its own process with its own data file,
and the setup steps drive the same admin API the web UI calls.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parent.parent

BRIDGE_PORT = 8399
ADMIN_PASSWORD = "e2e-admin-password"

#: Appended to by every `check` below, and read by the runners to decide their
#: exit code. The simulator scripts import this module for the same reason.
failures: list[str] = []


def step(title: str) -> None:
    print(f"\n\033[1m{title}\033[0m", flush=True)


def check(description: str, condition: bool, detail: str = "") -> None:
    print(f"  {'PASS' if condition else 'FAIL'}  {description}", flush=True)
    if not condition:
        failures.append(description)
        if detail:
            print(f"        {detail}", flush=True)


def wait_for(name: str, url: str, timeout: float = 90.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if httpx.get(url, timeout=3).status_code < 500:
                return
        except httpx.HTTPError:
            pass
        time.sleep(1)
    raise TimeoutError(f"{name} did not come up at {url}")


def docker_remove(container: str) -> None:
    subprocess.run(["docker", "rm", "-f", container], capture_output=True, check=False)


def start_bridge(data_file: Path) -> subprocess.Popen[bytes]:
    environment = {
        **os.environ,
        "CHECKLISTS_ADMIN_PASSWORD": ADMIN_PASSWORD,
        "CHECKLISTS_DATA_FILE": str(data_file),
        "CHECKLISTS_HOST": "127.0.0.1",
        "CHECKLISTS_PORT": str(BRIDGE_PORT),
        "CHECKLISTS_PUBLIC_URL": f"http://127.0.0.1:{BRIDGE_PORT}",
    }
    process = subprocess.Popen(
        ["uv", "run", "checklists-bridge"],
        cwd=REPO / "bridge",
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    wait_for("bridge", f"http://127.0.0.1:{BRIDGE_PORT}/healthz")
    return process


def phone_session() -> httpx.Client:
    """Sign in to the bridge exactly as the web UI does.

    The session cookie is marked Secure, because the bridge is only supported
    behind an HTTPS proxy. Browsers make an exception for http://localhost and
    send it anyway; httpx enforces the attribute strictly and would silently
    drop it, so the cookie is carried by hand here. That is a quirk of the test
    client, not something a real phone has to do.
    """
    client = httpx.Client(base_url=f"http://127.0.0.1:{BRIDGE_PORT}", timeout=30)
    signed_in = client.post("/login", data={"password": ADMIN_PASSWORD}, follow_redirects=False)
    cookie = signed_in.headers.get("set-cookie", "").split(";")[0]
    if cookie:
        client.headers["Cookie"] = cookie
    # Writes go through the cross-origin guard, exactly as the browser's do.
    client.headers["Origin"] = f"http://127.0.0.1:{BRIDGE_PORT}"
    return client


def report(subject: str) -> int:
    """Print the tally and return the exit code."""
    print()
    if failures:
        print(f"\033[31m{len(failures)} check(s) failed:\033[0m")
        for item in failures:
            print(f"  - {item}")
        return 1
    print(f"\033[32mEvery check passed: {subject}.\033[0m")
    return 0
