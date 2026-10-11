"""Unrolling linked checklists: what the watch is actually sent."""

from __future__ import annotations

from collections.abc import Mapping

from checklists_bridge.flatten import flatten
from checklists_bridge.models import (
    MAX_ITEMS_PER_CHECKLIST,
    MAX_LINK_DEPTH,
    Checklist,
    Link,
)


def checklist(
    name: str, items: list[str], links: Mapping[int, tuple[str, ...]] | None = None
) -> Checklist:
    return Checklist(
        id=f"t:{name}",
        name=name,
        items=tuple(items),
        links=tuple(Link(index=index, targets=targets) for index, targets in (links or {}).items()),
    )


def lookup(*lists: Checklist) -> dict[str, Checklist]:
    return {item.id: item for item in lists}


def test_a_list_without_links_is_left_exactly_as_it_is() -> None:
    plain = checklist("a", ["Mask", "Fins"])
    flat = flatten(plain, lookup(plain))
    assert flat == plain
    # No depths at all, so the watch gets the payload it always did.
    assert flat.depths == () and flat.groups == ()


def test_a_link_becomes_a_heading_with_the_linked_items_indented_under_it() -> None:
    night = checklist("night", ["Brush teeth", "Lock door"])
    home = checklist("home", ["Lights", "Night routine", "Sleep"], {1: ("night",)})
    flat = flatten(home, lookup(home, night))
    assert flat.items == ("Lights", "Night routine", "Brush teeth", "Lock door", "Sleep")
    assert flat.depths == (0, 0, 1, 1, 0)
    assert flat.groups == (1,)
    assert flat.id == "t:home" and flat.name == "home"


def test_links_nest_up_to_the_depth_limit_and_no_further() -> None:
    chain = [checklist(str(n), [f"item {n}", f"to {n + 1}"], {1: (str(n + 1),)}) for n in range(6)]
    flat = flatten(chain[0], lookup(*chain))
    assert max(flat.depths) == MAX_LINK_DEPTH
    # The link at the deepest level is not followed: it stays a plain item.
    last_group = max(flat.groups)
    assert flat.items[last_group + 1 :] == (
        f"item {MAX_LINK_DEPTH}",
        f"to {MAX_LINK_DEPTH + 1}",
    )
    assert flat.depths[-1] == MAX_LINK_DEPTH


def test_a_link_to_something_that_is_not_a_checklist_stays_an_ordinary_item() -> None:
    home = checklist("home", ["See the manual", "Lights"], {0: ("nowhere",)})
    flat = flatten(home, lookup(home))
    assert flat.items == ("See the manual", "Lights")
    assert flat.groups == ()


def test_the_first_target_that_is_a_checklist_is_the_one_used() -> None:
    other = checklist("other", ["x"])
    home = checklist("home", ["Both"], {0: ("missing", "other")})
    assert flatten(home, lookup(home, other)).items == ("Both", "x")


def test_a_list_linking_to_itself_is_not_followed() -> None:
    loop = checklist("loop", ["Again", "Done"], {0: ("loop",)})
    flat = flatten(loop, lookup(loop))
    assert flat.items == ("Again", "Done")
    assert flat.groups == ()


def test_a_cycle_through_another_list_is_cut_where_it_closes() -> None:
    a = checklist("a", ["to b", "a1"], {0: ("b",)})
    b = checklist("b", ["to a", "b1"], {0: ("a",)})
    flat = flatten(a, lookup(a, b))
    # a -> b is unrolled; b's link back to a is the loop, so it stays plain.
    assert flat.items == ("to b", "to a", "b1", "a1")
    assert flat.depths == (0, 1, 1, 0)
    assert flat.groups == (0,)


def test_the_same_list_linked_twice_is_unrolled_twice() -> None:
    shared = checklist("shared", ["s1"])
    home = checklist("home", ["first", "second"], {0: ("shared",), 1: ("shared",)})
    flat = flatten(home, lookup(home, shared))
    assert flat.items == ("first", "s1", "second", "s1")
    assert flat.groups == (0, 2)


def test_a_link_to_an_empty_list_stays_an_ordinary_item() -> None:
    empty = checklist("empty", [])
    home = checklist("home", ["Nothing here", "Lights"], {0: ("empty",)})
    flat = flatten(home, lookup(home, empty))
    assert flat.items == ("Nothing here", "Lights")
    assert flat.groups == ()


def test_the_result_never_exceeds_the_item_cap() -> None:
    big = checklist("big", [f"b{n}" for n in range(MAX_ITEMS_PER_CHECKLIST)])
    home = checklist("home", ["head", "tail"], {0: ("big",)})
    flat = flatten(home, lookup(home, big))
    assert len(flat.items) == MAX_ITEMS_PER_CHECKLIST
    assert flat.items[0] == "head"


def test_flattening_a_flattened_list_changes_nothing() -> None:
    night = checklist("night", ["Brush teeth"])
    home = checklist("home", ["Night routine"], {0: ("night",)})
    once = flatten(home, lookup(home, night))
    assert flatten(once, lookup(once, night)) == once


def test_a_flattened_list_can_itself_be_linked_to() -> None:
    # What happens when one fetch failed and last refresh's copy is used: the
    # copy is already flattened, with its own headings, and keeps them.
    leaf = checklist("leaf", ["l1"])
    middle = flatten(checklist("middle", ["to leaf", "m1"], {0: ("leaf",)}), lookup(leaf))
    top = checklist("top", ["to middle"], {0: ("middle",)})
    flat = flatten(top, lookup(top, middle, leaf))
    assert flat.items == ("to middle", "to leaf", "l1", "m1")
    assert flat.depths == (0, 1, 2, 1)
    assert flat.groups == (0, 1)


def test_links_only_resolve_within_their_own_provider() -> None:
    other_provider = Checklist(id="x:night", name="night", items=("n1",))
    home = checklist("home", ["Night routine"], {0: ("night",)})
    flat = flatten(home, {home.id: home, other_provider.id: other_provider})
    assert flat.items == ("Night routine",)
