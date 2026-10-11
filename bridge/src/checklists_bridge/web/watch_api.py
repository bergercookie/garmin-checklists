"""The endpoints the Garmin app calls.

Two rules shape this API:
  * keys are single letters and payloads are split per list, because a watch
    parses JSON into a very small heap;
  * it is read-only -- tick state never leaves the watch.

A list that links to others arrives already unrolled (see flatten.py): the
linked lists' items are in ``i``, and ``k`` says how deep each one sits.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, status

from checklists_bridge.service import NotFoundError
from checklists_bridge.web.deps import DeviceAuth, Service

#: Bumped when the payload shape changes so old watch apps can refuse politely.
PAYLOAD_VERSION = 1

router = APIRouter(prefix="/api/v1/watch", tags=["watch"], dependencies=[DeviceAuth])


@router.get("/lists")
def list_checklists(
    service: Service,
    refresh: Annotated[bool, Query(description="Pull from providers before answering")] = False,
) -> dict[str, Any]:
    """Index of every checklist on the watch: id, name and item count."""
    if refresh:
        service.refresh()
    checklists, synced_at = service.snapshot()
    return {
        "v": PAYLOAD_VERSION,
        "t": synced_at,
        "l": [{"id": item.id, "n": item.name, "c": len(item.items)} for item in checklists],
    }


@router.get("/lists/{checklist_id}")
def read_checklist(checklist_id: str, service: Service) -> dict[str, Any]:
    """One checklist with its item labels, in display order."""
    try:
        checklist = service.snapshot_checklist(checklist_id)
    except NotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    payload: dict[str, Any] = {"id": checklist.id, "n": checklist.name, "i": list(checklist.items)}
    if checklist.depths:
        # One number per item: its depth times two, plus one if it is a heading
        # (the item that stands for a linked list). Left out for a plain list,
        # which is every list there was before links, so an old watch app and a
        # new bridge agree on those.
        headings = set(checklist.groups)
        payload["k"] = [
            (depth * 2) + (1 if index in headings else 0)
            for index, depth in enumerate(checklist.depths)
        ]
    return payload
