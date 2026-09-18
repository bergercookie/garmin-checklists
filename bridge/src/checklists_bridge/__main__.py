"""``python -m checklists_bridge`` / ``checklists-bridge`` entry point."""

from __future__ import annotations

import sys

import uvicorn

from checklists_bridge.config import ConfigError, Settings
from checklists_bridge.web import create_app


def main() -> int:
    try:
        settings = Settings.from_env()
    except ConfigError as error:
        print(f"configuration error: {error}", file=sys.stderr)
        return 2
    uvicorn.run(
        create_app(settings),
        host=settings.host,
        port=settings.port,
        # "127.0.0.1" is uvicorn's own safe default -- only the immediate peer
        # is believed -- and is what an unset CHECKLISTS_TRUSTED_PROXIES falls
        # back to here. In a container the reverse proxy is never 127.0.0.1, so
        # every client would look like the Docker gateway and the login
        # throttle would lock all of them out together; CHECKLISTS_TRUSTED_
        # PROXIES exists to name that proxy's real address instead. Only ever
        # set it to a proxy you control: the bridge is not meant to be exposed
        # directly.
        forwarded_allow_ips=settings.trusted_proxies or "127.0.0.1",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
