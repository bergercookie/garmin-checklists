"""JSON API behind the web UI."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from checklists_bridge.models import DomainError
from checklists_bridge.providers import (
    ProviderAuthError,
    ProviderError,
    SourceNotFoundError,
)
from checklists_bridge.web.deps import AdminAuth, Config, Service

router = APIRouter(prefix="/api/v1/admin", tags=["admin"], dependencies=[AdminAuth])
# Compartmentalized by concern -- provider onboarding and local-checklist CRUD
# each get their own router, included below -- rather than one long list of
# routes covering both plus pairing/sync.
providers_router = APIRouter(prefix="/providers")
local_router = APIRouter(prefix="/local")


class ProviderConfigBody(BaseModel):
    config: dict[str, Any] = Field(default_factory=dict)


class SelectionBody(BaseModel):
    source_ids: list[str] = Field(default_factory=list)


class NewChecklistBody(BaseModel):
    name: str


class UpdateChecklistBody(BaseModel):
    name: str | None = None
    items: list[str] | None = None


def _fail(error: Exception) -> HTTPException:
    """Translate domain errors into the status codes the UI expects."""
    if isinstance(error, ProviderAuthError):
        return HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(error))
    if isinstance(error, SourceNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, detail=str(error))
    if isinstance(error, DomainError):
        return HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(error))
    return HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(error))


@router.get("/state")
def read_state(service: Service, settings: Config) -> dict[str, Any]:
    """Everything the single-page UI needs to render itself."""
    checklists, synced_at = service.snapshot()
    health = service.sync_health()
    return {
        "device_token": service.device_token,
        "public_url": settings.public_url,
        "synced_at": synced_at,
        # A sync that failed must not read as a sync that worked, so these are
        # reported separately from `synced_at` rather than folded into it.
        "last_attempt_at": health.attempted_at,
        "sync_errors": list(health.errors),
        "snapshot": [item.to_dict() for item in checklists],
        "local_checklists": [item.to_dict() for item in service.local_checklists()],
        "providers": [
            {
                **status_.spec.to_dict(),
                "configured": status_.configured,
                "selected": list(status_.selected),
                "config": status_.config,
            }
            for status_ in service.provider_statuses()
        ],
    }


@providers_router.put("/{provider_id}/config")
def configure_provider(
    provider_id: str, body: ProviderConfigBody, service: Service
) -> dict[str, Any]:
    try:
        sources = service.configure_provider(provider_id, body.config)
    except (ProviderError, DomainError) as error:
        raise _fail(error) from error
    return {"sources": [asdict(source) for source in sources]}


@providers_router.delete("/{provider_id}/config", status_code=status.HTTP_204_NO_CONTENT)
def forget_provider(provider_id: str, service: Service) -> None:
    try:
        service.forget_provider(provider_id)
    except ProviderError as error:
        raise _fail(error) from error


@providers_router.get("/{provider_id}/sources")
def list_sources(provider_id: str, service: Service) -> dict[str, Any]:
    """Onboarding picker: what this provider offers for import."""
    try:
        sources = service.list_sources(provider_id)
    except (ProviderError, DomainError) as error:
        raise _fail(error) from error
    return {"sources": [asdict(source) for source in sources]}


@providers_router.put("/{provider_id}/selection")
def set_selection(provider_id: str, body: SelectionBody, service: Service) -> dict[str, Any]:
    try:
        service.set_selection(provider_id, body.source_ids)
    except (ProviderError, DomainError) as error:
        raise _fail(error) from error
    return {"selected": body.source_ids}


@local_router.post("/checklists", status_code=status.HTTP_201_CREATED)
def create_local(body: NewChecklistBody, service: Service) -> dict[str, Any]:
    try:
        return asdict(service.create_local_checklist(body.name))
    except (ProviderError, DomainError) as error:
        raise _fail(error) from error


@local_router.put("/checklists/{source_id}")
def update_local(source_id: str, body: UpdateChecklistBody, service: Service) -> dict[str, Any]:
    try:
        if body.name is not None:
            service.rename_local_checklist(source_id, body.name)
        if body.items is not None:
            service.set_local_items(source_id, body.items)
    except (ProviderError, DomainError) as error:
        raise _fail(error) from error
    return {"ok": True}


@local_router.delete("/checklists/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_local(source_id: str, service: Service) -> None:
    try:
        service.delete_local_checklist(source_id)
    except (ProviderError, DomainError) as error:
        raise _fail(error) from error


router.include_router(providers_router)
router.include_router(local_router)


@router.post("/refresh")
def refresh(service: Service) -> dict[str, Any]:
    report = service.refresh()
    return {
        "ok": report.ok,
        "at": report.at,
        "errors": list(report.errors),
        "checklists": [item.to_dict() for item in report.checklists],
    }


@router.post("/sessions/revoke", status_code=status.HTTP_204_NO_CONTENT)
def revoke_sessions(service: Service) -> None:
    """Sign every browser out, this one included."""
    service.revoke_sessions()


@router.post("/device-token")
def rotate_device_token(service: Service) -> dict[str, str]:
    """Invalidate the old pairing token; the watch must be re-paired."""
    return {"device_token": service.rotate_device_token()}
