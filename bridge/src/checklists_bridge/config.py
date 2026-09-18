"""Process configuration, read once from the environment."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as installed_version
from pathlib import Path

ENV_PREFIX = "CHECKLISTS_"

#: Shown when the package metadata cannot be read, which in practice means
#: somebody is running from a source tree they never installed.
UNKNOWN_VERSION = "0+unknown"


def detect_version() -> str:
    """Return the installed version, which hatch-vcs took from the git tag."""
    try:
        return installed_version("checklists-bridge")
    except PackageNotFoundError:
        return UNKNOWN_VERSION


#: Kept here rather than in __init__ so every layer can read it without
#: importing the package root.
VERSION = detect_version()


class ConfigError(Exception):
    """Raised when the environment is missing something the bridge needs."""


@dataclass(frozen=True, slots=True)
class Settings:
    """Everything the bridge needs to know before it can start."""

    #: Relative to the working directory the process starts in unless given an
    #: absolute path (the Docker image and the systemd unit both do). Nothing
    #: pre-creates it: ``Database`` (storage.py) writes it on first save, but
    #: its parent directory must already exist.
    data_file: Path
    admin_password: str
    host: str = "127.0.0.1"
    port: int = 8099
    #: Public HTTPS URL the watch will talk to; only used to render setup hints.
    public_url: str = ""
    #: Whose X-Forwarded-* headers uvicorn should believe -- IPs and/or CIDR
    #: ranges, comma-separated. Left unset (the default), only the immediate
    #: peer is trusted, uvicorn's own safe default; that is wrong the moment a
    #: reverse proxy sits in front of the bridge; in a container the proxy is
    #: never 127.0.0.1, so this must then be set explicitly to the proxy's
    #: real address at deploy time. It deliberately does not default to "*"
    #: (trust every peer's headers unconditionally): that would let anyone who
    #: can reach the port spoof their address and bypass the login throttle.
    trusted_proxies: str = ""

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        source = os.environ if env is None else env
        password = source.get(f"{ENV_PREFIX}ADMIN_PASSWORD", "").strip()
        if not password:
            raise ConfigError(f"{ENV_PREFIX}ADMIN_PASSWORD must be set: it protects the web UI")
        return cls(
            data_file=Path(source.get(f"{ENV_PREFIX}DATA_FILE", "data/bridge.json")),
            admin_password=password,
            host=source.get(f"{ENV_PREFIX}HOST", "127.0.0.1"),
            port=int(source.get(f"{ENV_PREFIX}PORT", "8099")),
            public_url=source.get(f"{ENV_PREFIX}PUBLIC_URL", "").rstrip("/"),
            trusted_proxies=source.get(f"{ENV_PREFIX}TRUSTED_PROXIES", ""),
        )
