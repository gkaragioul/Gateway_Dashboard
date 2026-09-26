import os
import secrets
import socket
from pathlib import Path
from typing import Annotated, Any

from fastapi import Cookie, Depends, FastAPI, File, Form, Header, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .audit_log import AuditLog
from .drives import list_drives
from .filesystem import (
    FilesystemUnavailable,
    UploadConflictError,
    UploadNameError,
    common_locations,
    item_metadata,
    list_children,
    open_in_explorer,
    path_variants,
    preview_file_path,
    preview_media_type,
    upload_file_to_folder,
)
from .login_limiter import LoginRateLimiter
from .path_utils import PathError
from .security import SecurityStore
from .settings import AppSettings
from .setup_code import (
    clear_setup_code,
    is_local_request,
    load_or_create_setup_code,
    setup_code_matches,
    setup_code_path,
)


SESSION_COOKIE = "pcdd_session"
CSRF_COOKIE = "pcdd_csrf"
SESSION_TTL_SECONDS = 8 * 60 * 60
REMEMBER_TTL_SECONDS = 30 * 24 * 60 * 60


class LoginRequest(BaseModel):
    password: str
    remember: bool = False
    device_name: str = "Browser"


class SetupRequest(LoginRequest):
    setup_code: str | None = None


class PathRequest(BaseModel):
    path: str


def create_app(settings: AppSettings | None = None) -> FastAPI:
    resolved_settings = settings or AppSettings.from_env()
    resolved_settings.ensure_dirs()
    store = SecurityStore(resolved_settings.config_path)
    audit = AuditLog(resolved_settings.log_dir)
    app = FastAPI(title="Gateway Dashboard", version="0.9.5")
    static_dir = Path(__file__).parent / "static"
    config_dir = resolved_settings.config_path.parent
    login_limiter = LoginRateLimiter()

    app.state.settings = resolved_settings
    app.state.security_store = store
    app.state.audit_log = audit
    app.state.login_limiter = login_limiter

    if store.is_configured():
        clear_setup_code(config_dir)
    else:
        _announce_setup_code(load_or_create_setup_code(config_dir), setup_code_path(config_dir))

    async def require_auth(
        pcdd_session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
    ) -> str:
        if not store.is_configured():
            raise HTTPException(status_code=428, detail="Password setup required.")
        if not store.verify_trusted_token(pcdd_session):
            raise HTTPException(status_code=401, detail="Authentication required.")
        return pcdd_session or ""

    async def require_csrf(
        token: Annotated[str, Depends(require_auth)],
        csrf_header: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
        csrf_cookie: Annotated[str | None, Cookie(alias=CSRF_COOKIE)] = None,
    ) -> str:
        if not csrf_header or not csrf_cookie or not secrets.compare_digest(csrf_header, csrf_cookie):
            raise HTTPException(status_code=403, detail="CSRF token mismatch.")
        return token

    @app.get("/", response_class=HTMLResponse)
    async def index() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon() -> FileResponse:
        return FileResponse(static_dir / "favicon.ico", media_type="image/x-icon")

    @app.get("/api/auth/state")
    async def auth_state(
        request: Request,
        pcdd_session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
    ) -> dict[str, Any]:
        authenticated = store.verify_trusted_token(pcdd_session)
        configured = store.is_configured()
        return {
            "configured": configured,
            "authenticated": authenticated,
            "setup_requires_code": not configured and not _is_local(request),
            "hostname": socket.gethostname(),
            "platform": os.name,
        }

    @app.post("/api/auth/setup")
    async def setup(payload: SetupRequest, request: Request, response: Response) -> dict[str, Any]:
        if store.is_configured():
            raise HTTPException(status_code=409, detail="Password already configured.")
        client = _client_host(request)
        _refuse_if_locked_out(login_limiter, client)
        local = _is_local(request)
        if not local and not setup_code_matches(load_or_create_setup_code(config_dir), payload.setup_code):
            _record_failed_attempt(login_limiter, audit, "auth.setup", client)
            raise HTTPException(status_code=403, detail=_finish_setup_on_pc_message(request))
        try:
            store.set_password(payload.password)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        login_limiter.reset(client)
        clear_setup_code(config_dir)
        audit.record("auth.setup", "ok", client=client, method="local" if local else "setup_code")
        _issue_session(response, store, payload.device_name, payload.remember)
        return {"ok": True}

    @app.post("/api/auth/login")
    async def login(payload: LoginRequest, request: Request, response: Response) -> dict[str, Any]:
        if not store.is_configured():
            raise HTTPException(status_code=428, detail="Password setup required.")
        client = _client_host(request)
        _refuse_if_locked_out(login_limiter, client)
        if not store.verify_password(payload.password):
            locked_for = _record_failed_attempt(login_limiter, audit, "auth.login", client)
            detail = "Wrong password."
            if locked_for:
                detail += f" Too many failed attempts from this device. Try again in {locked_for} seconds."
            raise HTTPException(status_code=401, detail=detail)
        login_limiter.reset(client)
        audit.record("auth.login", "ok", client=client)
        _issue_session(response, store, payload.device_name, payload.remember)
        return {"ok": True}

    @app.post("/api/auth/logout")
    async def logout(
        response: Response,
        token: Annotated[str, Depends(require_auth)],
    ) -> dict[str, Any]:
        store.revoke_token(token)
        response.delete_cookie(SESSION_COOKIE)
        response.delete_cookie(CSRF_COOKIE)
        audit.record("auth.logout", "ok")
        return {"ok": True}

    @app.get("/api/drives")
    async def drives(token: Annotated[str, Depends(require_auth)]) -> dict[str, Any]:
        return {"drives": list_drives()}

    @app.get("/api/locations")
    async def locations(token: Annotated[str, Depends(require_auth)]) -> dict[str, Any]:
        return {"locations": common_locations()}

    @app.get("/api/tree")
    async def tree(
        path: str,
        token: Annotated[str, Depends(require_auth)],
        page: int = 1,
        page_size: int = 200,
    ) -> dict[str, Any]:
        try:
            return list_children(path, page=page, page_size=page_size)
        except PathError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except FilesystemUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except NotADirectoryError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/item")
    async def item(path: str, token: Annotated[str, Depends(require_auth)]) -> dict[str, Any]:
        try:
            return item_metadata(path)
        except PathError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except FilesystemUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/file")
    async def file_preview(path: str, token: Annotated[str, Depends(require_auth)]) -> FileResponse:
        try:
            target = preview_file_path(path)
            response = FileResponse(
                target,
                media_type=preview_media_type(path),
                filename=target.name,
                content_disposition_type="inline",
            )
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Content-Type-Options"] = "nosniff"
            return response
        except PathError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except FilesystemUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except IsADirectoryError as exc:
            raise HTTPException(status_code=400, detail="Folders open in the dashboard list, not file preview.") from exc

    @app.post("/api/path/copy")
    async def copy_path(payload: PathRequest, token: Annotated[str, Depends(require_auth)]) -> dict[str, str]:
        try:
            return path_variants(payload.path)
        except PathError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/open")
    async def open_path(
        payload: PathRequest,
        token: Annotated[str, Depends(require_csrf)],
    ) -> dict[str, Any]:
        try:
            open_in_explorer(payload.path)
        except PathError as exc:
            audit.record("filesystem.open", "rejected", path=payload.path, reason=str(exc))
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except FilesystemUnavailable as exc:
            audit.record("filesystem.open", "unavailable", path=payload.path, reason=str(exc))
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            audit.record("filesystem.open", "missing", path=payload.path)
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        audit.record("filesystem.open", "ok", path=payload.path)
        return {"ok": True}

    @app.post("/api/upload")
    async def upload_file(
        request: Request,
        path: Annotated[str, Form()],
        file: Annotated[UploadFile, File()],
        token: Annotated[str, Depends(require_csrf)],
    ) -> dict[str, Any]:
        try:
            if not resolved_settings.write_operations_enabled:
                audit.record("filesystem.upload", "disabled", path=path, filename=file.filename)
                raise HTTPException(
                    status_code=403,
                    detail="Uploads are turned off on this PC (PCDD_ENABLE_WRITES=0).",
                )
            result = upload_file_to_folder(path, file.filename or "", file.file)
        except PathError as exc:
            audit.record("filesystem.upload", "rejected", path=path, filename=file.filename, reason=str(exc))
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except UploadNameError as exc:
            audit.record("filesystem.upload", "rejected", path=path, filename=file.filename, reason=str(exc))
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except UploadConflictError as exc:
            audit.record("filesystem.upload", "conflict", path=path, filename=file.filename)
            raise HTTPException(status_code=409, detail=f"File already exists: {file.filename}") from exc
        except FilesystemUnavailable as exc:
            audit.record("filesystem.upload", "unavailable", path=path, filename=file.filename, reason=str(exc))
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            audit.record("filesystem.upload", "missing", path=path, filename=file.filename)
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except NotADirectoryError as exc:
            audit.record("filesystem.upload", "not_directory", path=path, filename=file.filename)
            raise HTTPException(status_code=400, detail="Uploads require a folder destination.") from exc
        finally:
            await file.close()

        audit.record(
            "filesystem.upload",
            "ok",
            path=result["path"],
            folder=path,
            filename=result["name"],
            size=result["size"],
            client=request.client.host if request.client else None,
        )
        return result

    @app.get("/api/jobs")
    async def jobs(token: Annotated[str, Depends(require_auth)], limit: int = 100) -> dict[str, Any]:
        return {"events": audit.tail(limit=limit)}

    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    return app


def _client_host(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _is_local(request: Request) -> bool:
    return is_local_request(request.client.host if request.client else None, request.url.hostname)


def _refuse_if_locked_out(limiter: LoginRateLimiter, client: str) -> None:
    wait = limiter.retry_after(client)
    if wait:
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed attempts from this device. Try again in {wait} seconds.",
            headers={"Retry-After": str(wait)},
        )


def _record_failed_attempt(limiter: LoginRateLimiter, audit: AuditLog, event: str, client: str) -> int:
    locked_for = limiter.record_failure(client)
    audit.record(event, "rejected", client=client)
    if locked_for:
        # Only the start of a lockout is logged; refused attempts during it are not, so a flood cannot fill the disk.
        audit.record(event, "locked_out", client=client, seconds=locked_for)
    return locked_for


def _finish_setup_on_pc_message(request: Request) -> str:
    port = request.url.port or (request.scope.get("server") or (None, 8787))[1]
    return (
        "Finish setup on the PC. Enter the one-time setup code from setup-code.txt in the dashboard's "
        "config folder on the PC (it is also printed in the server log). Or, if the dashboard listens on "
        f"127.0.0.1, create the password in a browser on the PC itself at http://127.0.0.1:{port}."
    )


def _announce_setup_code(code: str, code_file: Path) -> None:
    print(
        "Gateway Dashboard: no password is set yet.\n"
        f"  One-time setup code: {code}\n"
        f"  (also saved in {code_file}; it is deleted once the password is set)\n"
        "  Create the password in a browser on this PC, or enter this code when setting it up from another device.",
        flush=True,
    )


def _issue_session(response: Response, store: SecurityStore, device_name: str, remember: bool) -> None:
    token = store.create_trusted_token(
        device_name,
        ttl_seconds=REMEMBER_TTL_SECONDS if remember else SESSION_TTL_SECONDS,
    )
    csrf = secrets.token_urlsafe(32)
    max_age = REMEMBER_TTL_SECONDS if remember else SESSION_TTL_SECONDS
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=max_age,
        httponly=True,
        samesite="lax",
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf,
        max_age=max_age,
        httponly=False,
        samesite="lax",
    )
