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
from .path_utils import PathError
from .security import SecurityStore
from .settings import AppSettings


SESSION_COOKIE = "pcdd_session"
CSRF_COOKIE = "pcdd_csrf"
SESSION_TTL_SECONDS = 8 * 60 * 60
REMEMBER_TTL_SECONDS = 30 * 24 * 60 * 60


class LoginRequest(BaseModel):
    password: str
    remember: bool = False
    device_name: str = "Browser"


class SetupRequest(LoginRequest):
    pass


class PathRequest(BaseModel):
    path: str


def create_app(settings: AppSettings | None = None) -> FastAPI:
    resolved_settings = settings or AppSettings.from_env()
    resolved_settings.ensure_dirs()
    store = SecurityStore(resolved_settings.config_path)
    audit = AuditLog(resolved_settings.log_dir)
    app = FastAPI(title="Gateway Dashboard", version="0.9.2")
    static_dir = Path(__file__).parent / "static"

    app.state.settings = resolved_settings
    app.state.security_store = store
    app.state.audit_log = audit

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
        pcdd_session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
    ) -> dict[str, Any]:
        authenticated = store.verify_trusted_token(pcdd_session)
        return {
            "configured": store.is_configured(),
            "authenticated": authenticated,
            "hostname": socket.gethostname(),
            "platform": os.name,
        }

    @app.post("/api/auth/setup")
    async def setup(payload: SetupRequest, request: Request, response: Response) -> dict[str, Any]:
        if store.is_configured():
            raise HTTPException(status_code=409, detail="Password already configured.")
        try:
            store.set_password(payload.password)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        audit.record("auth.setup", "ok", client=request.client.host if request.client else None)
        _issue_session(response, store, payload.device_name, payload.remember)
        return {"ok": True}

    @app.post("/api/auth/login")
    async def login(payload: LoginRequest, request: Request, response: Response) -> dict[str, Any]:
        if not store.is_configured():
            raise HTTPException(status_code=428, detail="Password setup required.")
        if not store.verify_password(payload.password):
            audit.record("auth.login", "rejected", client=request.client.host if request.client else None)
            raise HTTPException(status_code=401, detail="Wrong password.")
        audit.record("auth.login", "ok", client=request.client.host if request.client else None)
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
