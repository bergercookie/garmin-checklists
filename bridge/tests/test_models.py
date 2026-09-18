from __future__ import annotations

import pytest

from checklists_bridge.models import (
    MAX_ITEMS_PER_CHECKLIST,
    Checklist,
    DomainError,
    clean_items,
    clean_name,
    qualify,
    unqualify,
)


def test_qualified_ids_round_trip() -> None:
    parts = unqualify(qualify("vikunja", "12"))
    assert parts == ("vikunja", "12")
    assert (parts.provider_id, parts.source_id) == ("vikunja", "12")


@pytest.mark.parametrize("bad", ["", "vikunja", ":12", "vikunja:"])
def test_unqualify_rejects_malformed_ids(bad: str) -> None:
    with pytest.raises(DomainError):
        unqualify(bad)


def test_qualify_rejects_provider_ids_containing_the_separator() -> None:
    with pytest.raises(DomainError):
        qualify("vik:unja", "12")


def test_clean_name_collapses_whitespace() -> None:
    assert clean_name("  Dive   kit \n") == "Dive kit"


def test_clean_name_rejects_blank() -> None:
    with pytest.raises(DomainError):
        clean_name("   ")


def test_clean_items_drops_blanks_and_caps_the_count() -> None:
    items = clean_items(["  Mask ", "", "   ", "Fins", *[f"x{i}" for i in range(200)]])
    assert items[:3] == ("Mask", "Fins", "x0")
    assert len(items) == MAX_ITEMS_PER_CHECKLIST


def test_clean_items_rejects_a_bare_string() -> None:
    with pytest.raises(DomainError):
        clean_items("Mask")


def test_checklist_dict_round_trip() -> None:
    checklist = Checklist(id="local:a", name="Kit", items=("Mask", "Fins"))
    assert Checklist.from_dict(checklist.to_dict()) == checklist
