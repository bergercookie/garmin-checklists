from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from checklists_bridge.config import (
    UNKNOWN_VERSION,
    ConfigError,
    Settings,
    detect_version,
)
from checklists_bridge.service import ChecklistService


def test_admin_password_is_required() -> None:
    with pytest.raises(ConfigError, match="ADMIN_PASSWORD"):
        Settings.from_env({})


def test_a_whitespace_password_does_not_count() -> None:
    with pytest.raises(ConfigError):
        Settings.from_env({"CHECKLISTS_ADMIN_PASSWORD": "   "})


def test_defaults_suit_a_laptop() -> None:
    settings = Settings.from_env({"CHECKLISTS_ADMIN_PASSWORD": "hunter2"})
    assert settings.host == "127.0.0.1"
    assert settings.port == 8099
    assert settings.data_file == Path("data/bridge.json")
    assert settings.public_url == ""
    # Not "*": trusting every peer's forwarded headers by default is exactly
    # the risk an unset value should avoid. main() falls this back to
    # uvicorn's own safe default, "127.0.0.1", not to a wildcard.
    assert settings.trusted_proxies == ""


def test_every_setting_can_be_overridden() -> None:
    settings = Settings.from_env(
        {
            "CHECKLISTS_ADMIN_PASSWORD": "  hunter2  ",
            "CHECKLISTS_DATA_FILE": "/var/lib/checklists/bridge.json",
            "CHECKLISTS_HOST": "0.0.0.0",
            "CHECKLISTS_PORT": "9000",
            "CHECKLISTS_PUBLIC_URL": "https://checklists.example.com/",
            "CHECKLISTS_TRUSTED_PROXIES": "172.20.0.1",
        }
    )
    assert settings.admin_password == "hunter2"
    assert settings.data_file == Path("/var/lib/checklists/bridge.json")
    assert settings.host == "0.0.0.0"
    assert settings.port == 9000
    # The trailing slash is dropped so paths can be appended without doubling it.
    assert settings.public_url == "https://checklists.example.com"
    assert settings.trusted_proxies == "172.20.0.1"


def test_environment_is_read_when_no_mapping_is_given(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHECKLISTS_ADMIN_PASSWORD", "from-env")
    monkeypatch.delenv("CHECKLISTS_PORT", raising=False)
    assert Settings.from_env().admin_password == "from-env"


def test_a_non_numeric_port_is_rejected() -> None:
    with pytest.raises(ValueError):
        Settings.from_env({"CHECKLISTS_ADMIN_PASSWORD": "x", "CHECKLISTS_PORT": "http"})


def test_the_version_comes_from_the_installed_package_metadata() -> None:
    # hatch-vcs writes it from the git tag at build time, so the only thing
    # worth asserting here is that a real version was found rather than the
    # placeholder -- pinning the number would break on every release.
    assert detect_version() not in ("", UNKNOWN_VERSION)


def test_an_uninstalled_source_tree_reports_a_placeholder(monkeypatch: pytest.MonkeyPatch) -> None:
    def not_installed(_name: str) -> str:
        raise PackageNotFoundError

    monkeypatch.setattr("checklists_bridge.config.installed_version", not_installed)
    assert detect_version() == UNKNOWN_VERSION


def test_the_health_check_fails_when_the_data_file_cannot_be_read(
    client: TestClient, service: ChecklistService
) -> None:
    assert client.get("/healthz").json()["status"] == "ok"

    # A health check that only proves the process is listening would stay green
    # here, so Docker would never restart a bridge that answers 500 to
    # everything the watch and the phone actually ask for.
    service._database.path.write_text("{ not json")
    unhealthy = client.get("/healthz")
    assert unhealthy.status_code == 503
    assert unhealthy.json()["status"] == "unhealthy"
