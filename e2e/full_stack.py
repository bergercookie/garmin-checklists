"""End-to-end run: a real provider -> real bridge -> simulated watch.

Everything here is a real process talking over real HTTP. The provider runs in a
container, the bridge runs as its own process with its own data file, and the
phone steps drive the same admin API the web UI calls. The one thing that is not
real is the watch: see watch_simulator.py.

    uv run --project bridge python e2e/full_stack.py vikunja
    uv run --project bridge python e2e/full_stack.py trilium

or `just e2e-vikunja` / `just e2e-trilium` / `just e2e` for both. Needs Docker
and about a minute each. Exits non-zero on the first failed check.

The steps below are the same whichever provider is chosen -- that is the point.
Everything provider-shaped lives in e2e/providers/.

    uv run --project bridge python e2e/full_stack.py --install-cert

installs a self-signed certificate for 127.0.0.1 into the system trust store
and exits -- see install_cert() below -- for pointing a real device or browser
at a bridge run by hand (e.g. via tls_bridge.py) rather than by this harness.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import simulator_stack as sim
import stack
from providers import Fixture
from providers.trilium import Trilium
from providers.vikunja import Vikunja
from watch_simulator import Watch, assert_matches_monkey_c

REPO = Path(__file__).resolve().parent.parent
CHOICES: dict[str, type[Fixture]] = {"vikunja": Vikunja, "trilium": Trilium}

ADDED_UPSTREAM = "Spare mask strap"


def run(fixture: Fixture) -> int:
    admin = f"/api/v1/admin/providers/{fixture.provider_id}"
    workspace = Path(tempfile.mkdtemp(prefix="checklists-e2e-"))
    bridge = None
    try:
        stack.step("0. Prerequisites")
        # fixture.start() below shells out to docker directly, so a checkout
        # missing it would otherwise fail with a bare FileNotFoundError rather
        # than a clean check -- so this one is fatal immediately, not just
        # recorded like the rest of the checks in this run.
        if shutil.which("docker") is None:
            raise SystemExit("docker not found; needed to run the provider container")
        stack.check("'docker' present", True)
        for line in assert_matches_monkey_c():
            print(f"  PASS  {line}")

        stack.step(f"1. Start {fixture.label}")
        version = fixture.start(workspace)
        stack.check(f"{fixture.label} is up, version {version}", bool(version))

        stack.step(f"2. Seed {fixture.label} and mint a token")
        seeded = fixture.seed()

        stack.step("3. Start the bridge")
        bridge = stack.start_bridge(workspace / "bridge.json")
        stack.check("bridge answered its health check", True)

        stack.step(f"4. Phone: connect {fixture.label}")
        phone = stack.phone_session()
        connected = phone.put(f"{admin}/config", json={"config": seeded.config})
        stack.check(
            "credentials accepted and validated against the live API",
            connected.status_code == 200,
            connected.text[:200],
        )
        offered = {source["name"] for source in connected.json().get("sources", [])}
        stack.check(
            f"onboarding offers both lists, got {sorted(offered)}",
            {seeded.source_name, seeded.other_source_name} <= offered,
        )
        for name in seeded.also_offered:
            stack.check(f"{name!r} is offered", name in offered, str(sorted(offered)))
        for name, why in seeded.not_offered.items():
            stack.check(
                f"{name!r} is not offered: {why}", name not in offered, str(sorted(offered))
            )

        stack.step("5. Phone: import one list and sync")
        selection = phone.put(f"{admin}/selection", json={"source_ids": [seeded.source_id]})
        stack.check("selection saved", selection.status_code == 200)
        report = phone.post("/api/v1/admin/refresh").json()
        stack.check("refresh reported no provider errors", report["ok"], str(report.get("errors")))
        stack.check("exactly one checklist reached the snapshot", len(report["checklists"]) == 1)

        device_token = phone.get("/api/v1/admin/state").json()["device_token"]
        stack.check("bridge issued a device token for pairing", bool(device_token))

        stack.step("6. The watch syncs")
        watch = Watch(f"http://127.0.0.1:{stack.BRIDGE_PORT}", device_token)
        stack.check(f"sync result: {watch.sync()}", True)
        stack.check(
            f"watch made the expected calls: {watch.requests}",
            watch.requests
            == [
                "/api/v1/watch/lists?refresh=true",
                f"/api/v1/watch/lists/{fixture.provider_id}:{seeded.source_id}",
            ],
        )

        stack.step("7. What the watch stored")
        stack.check(
            f"one checklist stored, not {len(watch.checklists)}", len(watch.checklists) == 1
        )
        stored = watch.checklists[0]
        stack.check(f"named {stored['n']!r}", stored["n"] == seeded.source_name)
        stack.check(
            f"items match {fixture.label}: {stored['i']}",
            stored["i"] == seeded.items,
            f"expected {seeded.items}",
        )
        stack.check("every item arrived unticked", stored["d"] == [False] * len(seeded.items))
        stack.check(
            "the other list stayed out",
            all(item["n"] != seeded.other_source_name for item in watch.checklists),
        )

        stack.step("8. Tick two items on the watch")
        watch.set_ticked(0, 0, True)
        watch.set_ticked(0, 2, True)
        menu = watch.index_menu()[0]
        stack.check(f"menu shows progress: {menu}", f"2/{len(seeded.items)} done" in menu)

        stack.step(f"9. Nothing was written back to {fixture.label}")
        untouched, detail = fixture.nothing_was_ticked(seeded.source_id)
        stack.check(f"{fixture.label} is unchanged", untouched, detail)

        stack.step("10. An upstream edit reaches the watch, and clears the ticks")
        fixture.add_item(seeded.source_id, ADDED_UPSTREAM)
        phone.post("/api/v1/admin/refresh")
        watch.sync()
        stored = watch.checklists[0]
        stack.check(
            f"the new item arrived: {stored['i'][-1]!r}",
            stored["i"] == [*seeded.items, ADDED_UPSTREAM],
            str(stored["i"]),
        )
        stack.check(
            "a sync clears every tick", stored["d"] == [False] * len(stored["i"]), str(stored["d"])
        )

        stack.step("11. A bad device token is refused")
        rejected = Watch(f"http://127.0.0.1:{stack.BRIDGE_PORT}", "WRON-GTOK-ENAA-AAAA")
        try:
            rejected.sync()
            stack.check("bad token rejected", False, "the sync succeeded")
        except Exception as error:
            stack.check(f"bad token rejected: {error}", str(error) == "Token rejected")

        return 0 if not stack.failures else 1
    finally:
        if bridge is not None:
            bridge.terminate()
            bridge.wait(timeout=20)
        stack.docker_remove(fixture.container)
        shutil.rmtree(workspace, ignore_errors=True)


def install_cert() -> int:
    """Trust a self-signed certificate for 127.0.0.1 system-wide, then stop.

    Reuses simulator_stack.issue_certificate, which this run's own watch
    stand-in never needs (it talks plain HTTP), but a real device or browser
    pointed at a bridge started by hand -- e.g. via tls_bridge.py -- does.
    Needs sudo: prompts for a password on the terminal if none is cached, so
    it works interactively without passwordless sudo configured in advance. A
    run with no controlling terminal at all still writes the cert and key, but
    reports the failed check below.

    Unlike issue_certificate's other callers, this one writes to a fixed path
    rather than a throwaway temporary directory, so a previous run's
    certificate is still there to check -- if it is still the one trusted
    system-wide, there is nothing to do, and nothing to ask sudo for.
    """
    workspace = REPO / "build" / "certs"
    certificate, key = workspace / "cert.pem", workspace / "key.pem"
    if (
        certificate.exists()
        and key.exists()
        and sim.TRUST_ANCHOR_PATH.exists()
        and sim.TRUST_ANCHOR_PATH.read_bytes() == certificate.read_bytes()
    ):
        print("already installed and trusted; nothing to do")
        print(f"\n  certificate: {certificate}")
        print(f"  key:         {key}")
        return 0

    for program, needed_for in (("openssl", "minting the certificate"), ("sudo", "trusting it")):
        if shutil.which(program) is None:
            raise SystemExit(f"{program} not found; needed for {needed_for}")
    workspace.mkdir(parents=True, exist_ok=True)
    certificate, key = sim.issue_certificate(workspace)
    print(f"\n  certificate: {certificate}")
    print(f"  key:         {key}")
    return 1 if stack.failures else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument(
        "provider", nargs="?", choices=sorted(CHOICES), help="Run the full stack against this one."
    )
    target.add_argument(
        "--install-cert",
        action="store_true",
        help="Install a trusted certificate for 127.0.0.1 system-wide, then exit "
        "without running the stack at all. See install_cert() for why.",
    )
    return parser


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv[1:])
    if args.install_cert:
        return install_cert()
    fixture = CHOICES[args.provider]()
    code = run(fixture)
    return max(code, stack.report(f"{fixture.label} -> bridge -> watch"))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
