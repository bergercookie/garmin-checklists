"""Unrolling checklists that link to other checklists.

A checklist item that links to another checklist stands for that checklist: on
the watch the item becomes a heading and the linked list's items follow it,
indented one level. The watch is shown the result ready-made, so it needs no
idea of links, loops or lookups -- all of that is decided here, once, on the
bridge.

The rules, each of which is a test in test_flatten.py:

* A link only counts if it points at a checklist in ``lookup``: one of the
  served lists, or one only linked to (the service adds those). A link to
  anything else stays an ordinary item.
* A list never contains itself, however indirectly: a link back to a checklist
  already being unrolled is left as an ordinary item rather than followed.
* Nesting stops at :data:`MAX_LINK_DEPTH` levels, and the result at
  :data:`MAX_ITEMS_PER_CHECKLIST` items, so a careless web of links cannot
  swamp the watch's memory. Whatever does not fit is dropped from the end.
* A link whose target turns out to be empty stays an ordinary item; a heading
  with nothing under it would only confuse.
* The same list linked twice is unrolled twice, each with its own items: ticks
  on the watch are per row.
"""

from __future__ import annotations

from collections.abc import Mapping

from checklists_bridge.models import (
    MAX_ITEMS_PER_CHECKLIST,
    MAX_LINK_DEPTH,
    Checklist,
    qualify,
    unqualify,
)


def flatten(checklist: Checklist, lookup: Mapping[str, Checklist]) -> Checklist:
    """``checklist`` with every resolvable link replaced by the list it names.

    ``lookup`` maps qualified checklist ids to checklists, and may hold lists
    that were flattened already: those carry their own depths and headings,
    which are kept as they are. Flattening is therefore idempotent.
    """
    items: list[str] = []
    depths: list[int] = []
    groups: list[int] = []
    _unroll(checklist, 0, {checklist.id}, lookup, items, depths, groups)
    return Checklist(
        id=checklist.id,
        name=checklist.name,
        items=tuple(items),
        depths=tuple(depths) if any(depths) or groups else (),
        groups=tuple(groups),
    )


def _unroll(
    source: Checklist,
    base: int,
    path: set[str],
    lookup: Mapping[str, Checklist],
    items: list[str],
    depths: list[int],
    groups: list[int],
) -> None:
    """Append ``source``'s items, ``base`` levels in, to the three lists."""
    provider_id = unqualify(source.id).provider_id
    links = {link.index: link for link in source.links}
    headings = set(source.groups)
    for index, label in enumerate(source.items):
        if len(items) >= MAX_ITEMS_PER_CHECKLIST:
            return
        depth = base + (source.depths[index] if source.depths else 0)
        if index in headings:
            groups.append(len(items))
        elif index in links and depth < MAX_LINK_DEPTH:
            target = _target(links[index].targets, provider_id, path, lookup)
            if target is not None:
                before = len(items)
                items.append(label)
                depths.append(depth)
                groups.append(before)
                _unroll(target, depth + 1, path | {target.id}, lookup, items, depths, groups)
                if len(items) == before + 1:
                    # Nothing came of it: show the item as the plain text it is.
                    groups.pop()
                continue
        items.append(label)
        depths.append(depth)


def _target(
    targets: tuple[str, ...],
    provider_id: str,
    path: set[str],
    lookup: Mapping[str, Checklist],
) -> Checklist | None:
    """The first of ``targets`` that is a checklist and is not already open."""
    for source_id in targets:
        candidate = lookup.get(qualify(provider_id, source_id))
        if candidate is not None and candidate.id not in path:
            return candidate
    return None
