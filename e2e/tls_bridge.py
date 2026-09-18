"""Serve the bridge over TLS for the simulator end-to-end run.

Connect IQ refuses a plain-HTTP endpoint: makeWebRequest fails with
SECURE_CONNECTION_REQUIRED (-1001) before anything is sent. In production that
is the reverse proxy's job (see docs/bridge.md), so rather than add TLS options
to the bridge itself, the test starts it through this runner.

    python -m tls_bridge <certfile> <keyfile>

The rest of the bridge's own configuration (host, port, admin password, data
file, ...) still comes from the environment; see Settings.from_env.
"""

from __future__ import annotations

import argparse

import uvicorn

from checklists_bridge.config import Settings
from checklists_bridge.web import create_app


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("certfile", help="PEM certificate, trusted by whatever will connect")
    parser.add_argument("keyfile", help="PEM private key matching certfile")
    args = parser.parse_args()

    settings = Settings.from_env()
    uvicorn.run(
        create_app(settings),
        host=settings.host,
        port=settings.port,
        ssl_certfile=args.certfile,
        ssl_keyfile=args.keyfile,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
