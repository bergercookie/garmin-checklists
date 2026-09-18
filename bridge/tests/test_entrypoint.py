from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import uvicorn

from checklists_bridge.__main__ import main


def test_missing_password_is_reported_without_a_traceback(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("CHECKLISTS_ADMIN_PASSWORD", raising=False)
    assert main() == 2
    assert "ADMIN_PASSWORD" in capsys.readouterr().err


def test_serves_on_the_configured_address(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CHECKLISTS_ADMIN_PASSWORD", "hunter2")
    monkeypatch.setenv("CHECKLISTS_HOST", "0.0.0.0")
    monkeypatch.setenv("CHECKLISTS_PORT", "9000")
    monkeypatch.setenv("CHECKLISTS_DATA_FILE", str(tmp_path / "bridge.json"))

    served: dict[str, Any] = {}
    monkeypatch.setattr(uvicorn, "run", lambda _app, **kwargs: served.update(kwargs))

    assert main() == 0
    assert served["host"] == "0.0.0.0"
    assert served["port"] == 9000
    # CHECKLISTS_TRUSTED_PROXIES was not set, so this falls back to uvicorn's
    # own safe default -- trust only the immediate peer -- rather than a
    # wildcard that would believe forwarded headers from anyone.
    assert served["forwarded_allow_ips"] == "127.0.0.1"


def test_trusted_proxies_is_passed_through_when_set(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CHECKLISTS_ADMIN_PASSWORD", "hunter2")
    monkeypatch.setenv("CHECKLISTS_DATA_FILE", str(tmp_path / "bridge.json"))
    monkeypatch.setenv("CHECKLISTS_TRUSTED_PROXIES", "172.20.0.1")

    served: dict[str, Any] = {}
    monkeypatch.setattr(uvicorn, "run", lambda _app, **kwargs: served.update(kwargs))

    assert main() == 0
    assert served["forwarded_allow_ips"] == "172.20.0.1"
