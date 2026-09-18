"""FastAPI application factory plus the two HTML pages of the web UI."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, FastAPI, Form, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.applications import Starlette

from checklists_bridge.config import VERSION, Settings
from checklists_bridge.security import SESSION_TTL_SECONDS, passwords_match, sign_session
from checklists_bridge.service import ChecklistService
from checklists_bridge.storage import Database, StorageError
from checklists_bridge.web import admin_api, watch_api
from checklists_bridge.web.deps import SESSION_COOKIE, get_service, is_signed_in
from checklists_bridge.web.guard import (
    Handler,
    LoginThrottle,
    apply_guards,
    client_address,
)

HERE = Path(__file__).parent
TEMPLATES = Jinja2Templates(directory=str(HERE / "templates"))

pages = APIRouter(tags=["pages"])


@pages.get("/", response_class=HTMLResponse)
def index(request: Request) -> Response:
    if not is_signed_in(request, get_service(request)):
        return RedirectResponse("/login", status_code=303)
    return TEMPLATES.TemplateResponse(request, "index.html", {"version": VERSION})


@pages.get("/login", response_class=HTMLResponse)
def login_form(request: Request, error: str = "", locked: str = "") -> Response:
    # `locked` is the lockout's remaining seconds, passed through the redirect
    # `login()` issues below so the page can tell the owner why the form did
    # nothing rather than leaving it looking like a silently wrong password.
    return TEMPLATES.TemplateResponse(request, "login.html", {"error": error, "locked": locked})


@pages.post("/login")
def login(request: Request, password: str = Form(default="")) -> Response:
    settings: Settings = request.app.state.settings
    service: ChecklistService = request.app.state.service
    throttle: LoginThrottle = request.app.state.login_throttle
    client = client_address(request)

    wait = throttle.locked_for(client)
    if wait > 0:
        # Told plainly rather than silently: a locked-out owner needs to know it
        # is a lockout and not a wrong password.
        return RedirectResponse(f"/login?locked={int(wait) + 1}", status_code=303)

    if not passwords_match(password, settings.admin_password):
        throttle.record_failure(client)
        return RedirectResponse("/login?error=1", status_code=303)

    throttle.record_success(client)
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(
        SESSION_COOKIE,
        sign_session(service.session_secret, service.session_epoch),
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        samesite="lax",
        # Unconditional, not `scheme == "https"`: the bridge is only supported
        # behind an HTTPS proxy, and behind one uvicorn sees plain http unless
        # it has been told to trust the proxy's headers. Deriving it from the
        # scheme therefore dropped the flag in the deployment we actually ship.
        secure=True,
    )
    return response


@pages.post("/logout")
def logout() -> Response:
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE)
    return response


@pages.get("/healthz")
def healthz(request: Request) -> Response:
    """Container health. Touches storage on purpose.

    A health check that only proves the process is listening stays green while
    an unreadable data file makes every real endpoint fail -- so Docker never
    restarts it and the first thing anybody notices is that the watch stopped
    syncing.
    """
    try:
        get_service(request).sync_health()
    except StorageError as error:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "unhealthy", "version": VERSION, "detail": str(error)},
        )
    return JSONResponse({"status": "ok", "version": VERSION})


def create_app(settings: Settings, service: ChecklistService | None = None) -> Starlette:
    """Build the ASGI app. Tests pass a service backed by a temporary file."""
    app = FastAPI(
        title="Checklists bridge",
        version=VERSION,
        docs_url=None,
        redoc_url=None,
        # The schema would list every admin route to anyone who asked, and the
        # UIs above are already off, so nothing is losing a feature here.
        openapi_url=None,
    )
    app.state.settings = settings
    app.state.service = service or ChecklistService(Database(settings.data_file))
    app.state.login_throttle = LoginThrottle()

    @app.middleware("http")
    async def guards(request: Request, call_next: Handler) -> Response:
        return await apply_guards(request, call_next, settings.public_url)

    app.include_router(watch_api.router)
    app.include_router(admin_api.router)
    app.include_router(pages)
    app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")
    return app
