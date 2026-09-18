"""Shared FastAPI dependencies: service lookup and the two kinds of auth."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from checklists_bridge.config import Settings
from checklists_bridge.security import tokens_match, verify_session
from checklists_bridge.service import ChecklistService

SESSION_COOKIE = "checklists_session"


def get_service(request: Request) -> ChecklistService:
    service: ChecklistService = request.app.state.service
    return service


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


Service = Annotated[ChecklistService, Depends(get_service)]
Config = Annotated[Settings, Depends(get_settings)]


def require_device(request: Request, service: Service) -> None:
    """Authenticate the watch by its pairing token."""
    header = request.headers.get("authorization", "")
    scheme, _, presented = header.partition(" ")
    if scheme.lower() != "bearer" or not tokens_match(presented, service.device_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="bad device token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def is_signed_in(request: Request, service: ChecklistService) -> bool:
    cookie = request.cookies.get(SESSION_COOKIE, "")
    return bool(cookie) and verify_session(service.session_secret, cookie, service.session_epoch)


def require_admin(request: Request, service: Service) -> None:
    """Authenticate the browser by its signed session cookie."""
    if not is_signed_in(request, service):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="sign in first")


DeviceAuth = Depends(require_device)
AdminAuth = Depends(require_admin)
