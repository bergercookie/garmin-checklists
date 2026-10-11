from __future__ import annotations

import pytest

from checklists_bridge.models import (
    MAX_ITEMS_PER_CHECKLIST,
    Checklist,
    DomainError,
    Link,
    clean_entries,
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


def test_a_linked_checklist_survives_a_dict_round_trip() -> None:
    checklist = Checklist(
        id="trilium:a",
        name="Home",
        items=("Lights", "Night", "x"),
        links=(Link(index=1, targets=("n1", "n2")),),
        depths=(0, 0, 1),
        groups=(1,),
    )
    assert Checklist.from_dict(checklist.to_dict()) == checklist


def test_a_plain_checklist_stores_no_link_fields_at_all() -> None:
    # So a data file written before links existed reads back unchanged, and one
    # written now is no bigger.
    assert set(Checklist(id="a:b", name="Kit", items=("x",)).to_dict()) == {"id", "name", "items"}


def test_clean_entries_keeps_each_link_on_the_item_it_belonged_to() -> None:
    items, links = clean_entries(
        [("  ", ("ghost",)), ("Mask", ()), ("Night  routine", ("n1",)), ("", ()), ("End", ("n2",))]
    )
    assert items == ("Mask", "Night routine", "End")
    assert links == (Link(index=1, targets=("n1",)), Link(index=2, targets=("n2",)))


def test_clean_entries_caps_the_count() -> None:
    items, links = clean_entries((f"x{n}", ("t",)) for n in range(MAX_ITEMS_PER_CHECKLIST + 20))
    assert len(items) == len(links) == MAX_ITEMS_PER_CHECKLIST
