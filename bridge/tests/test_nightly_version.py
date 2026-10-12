"""The nightly's version has to satisfy two rule books at once."""

from __future__ import annotations

import datetime
import importlib.util
import re
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "nightly_version", Path(__file__).resolve().parents[2] / "tools" / "nightly_version.py"
)
assert SPEC is not None and SPEC.loader is not None
nightly = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(nightly)

NOON = datetime.datetime(2026, 10, 12, 3, 7, tzinfo=datetime.UTC)


@pytest.mark.parametrize(
    ("tag", "expected"),
    [
        ("v0.2.0", "0.2.1.dev202610120307"),
        ("v1.9.9", "1.9.10.dev202610120307"),
        ("v1.3.0-rc1", "1.3.0.dev202610120307"),
        ("v2.0.0-beta.2", "2.0.0.dev202610120307"),
        (None, "0.1.0.dev202610120307"),
    ],
)
def test_the_version_leads_up_to_the_next_release(tag: str | None, expected: str) -> None:
    assert nightly.nightly_version(tag, NOON) == expected


def test_it_is_a_pep_440_development_release() -> None:
    packaging = pytest.importorskip("packaging.version")
    version = packaging.Version(nightly.nightly_version("v0.2.0", NOON))
    assert version.is_devrelease
    # Ahead of the release before it, behind the one it leads up to.
    assert packaging.Version("0.2.0") < version < packaging.Version("0.2.1")


def test_it_is_a_valid_docker_tag() -> None:
    # What a registry accepts: no `+`, which is what hatch-vcs's own
    # between-tags spelling (0.2.1.dev4+g1a2b3cd) would have.
    version = nightly.nightly_version("v0.2.0", NOON)
    assert re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}", version)
    assert "+" not in version


def test_a_later_build_sorts_later() -> None:
    packaging = pytest.importorskip("packaging.version")
    later = NOON + datetime.timedelta(minutes=1)
    assert packaging.Version(nightly.nightly_version("v0.2.0", later)) > packaging.Version(
        nightly.nightly_version("v0.2.0", NOON)
    )


def test_the_time_is_taken_in_utc_whatever_the_zone_it_arrives_in() -> None:
    plus_two = datetime.timezone(datetime.timedelta(hours=2))
    local = datetime.datetime(2026, 10, 12, 5, 7, tzinfo=plus_two)
    assert nightly.nightly_version("v0.2.0", local) == nightly.nightly_version("v0.2.0", NOON)


@pytest.mark.parametrize("bad", ["latest", "v1.2", "release-3", "v1.2.3.4"])
def test_something_that_is_not_a_release_tag_is_refused(bad: str) -> None:
    with pytest.raises(ValueError, match="not a release tag"):
        nightly.next_release(bad)


def test_latest_tag_asks_git_and_copes_with_there_being_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Result:
        def __init__(self, code: int, out: str) -> None:
            self.returncode, self.stdout = code, out

    monkeypatch.setattr(nightly.subprocess, "run", lambda *_args, **_kwargs: Result(0, "v0.2.0\n"))
    assert nightly.latest_tag() == "v0.2.0"
    monkeypatch.setattr(nightly.subprocess, "run", lambda *_args, **_kwargs: Result(128, ""))
    assert nightly.latest_tag() is None


def test_main_prints_the_version(capsys: pytest.CaptureFixture[str]) -> None:
    assert nightly.main(["nightly_version.py"]) == 0
    assert re.fullmatch(r"\d+\.\d+\.\d+\.dev\d{12}", capsys.readouterr().out.strip())


def test_the_pre_release_guard_refuses_what_neither_rule_book_allows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(nightly, "PEP_440_DEV", re.compile(r"^never$"))
    with pytest.raises(ValueError, match="both"):
        nightly.nightly_version("v0.2.0", NOON)
