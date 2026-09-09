"""FastAPI app factory for the MINOS desktop local sidecar."""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from minos_core.ai_config import register_db_overrides_provider
from minos_core.validation import ValidationError
from minos_desktop.services import (
    DEFAULT_DESKTOP_DB_PATH,
    DEFAULT_DESKTOP_OUTPUT_DIR,
    DesktopProjectStore,
    DesktopSettingsStore,
    RunRepository,
)

from .auth import require_api_token
from .routes_auth import router as auth_router
from .routes_closure import router as closure_router
from .routes_exports import router as exports_router
from .routes_health import router as health_router
from .routes_knowledge import router as knowledge_router
from .routes_projects import router as projects_router
from .routes_runs import router as runs_router
from .routes_settings import router as settings_router
from .routes_sse import router as sse_router
from .routes_tables import router as tables_router
from .schemas import APIError, failure_from_exception


def create_app(
    *,
    db_path: str | Path = DEFAULT_DESKTOP_DB_PATH,
    output_dir: str | Path = DEFAULT_DESKTOP_OUTPUT_DIR,
) -> FastAPI:
    app = FastAPI(
        title="MINOS Desktop Sidecar API",
        description="Local API facade for minos_desktop services.",
        version="3.8.6",
    )
    app.state.db_path = str(db_path)
    app.state.output_dir = str(output_dir)
    app.state.run_repository_factory = lambda: RunRepository(app.state.db_path)
    app.state.project_store_factory = lambda: DesktopProjectStore(app.state.db_path)
    register_db_overrides_provider(
        lambda: DesktopSettingsStore(app.state.db_path).get_ai_overrides()
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:1420",
            "http://localhost:1420",
            "https://tauri.localhost",
            "http://tauri.localhost",
            "tauri://localhost",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Security headers middleware
    class SecurityHeadersMiddleware(BaseHTTPMiddleware):
        async def dispatch(
            self, request: Request, call_next: RequestResponseEndpoint
        ) -> Response:
            response = await call_next(request)
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            return response

    app.add_middleware(SecurityHeadersMiddleware)

    protected_dependencies = [Depends(require_api_token)]
    for router, tag in (
        (auth_router, "auth"),
        (health_router, "health"),
        (settings_router, "settings"),
        (projects_router, "projects"),
        (runs_router, "runs"),
        (tables_router, "tables"),
        (closure_router, "closure"),
        (exports_router, "exports"),
        (knowledge_router, "knowledge"),
    ):
        tags: list[str | Enum] = [tag]
        app.include_router(
            router,
            prefix="/api",
            tags=tags,
            dependencies=protected_dependencies,
        )

    # SSE uses a short-lived query stream token because EventSource cannot attach
    # the normal Authorization header consistently.
    app.include_router(sse_router)

    @app.exception_handler(APIError)
    async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "detail": exc.detail,
                "code": exc.code,
                "failure_message": exc.failure_message,
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        error = APIError("请求参数格式不正确。", "VALIDATION_ERROR", 422)
        return JSONResponse(
            status_code=422,
            content={
                "detail": error.detail,
                "code": error.code,
                "failure_message": error.failure_message,
            },
        )

    @app.exception_handler(ValidationError)
    async def input_validation_error_handler(
        request: Request,
        exc: ValidationError,
    ) -> JSONResponse:
        error = APIError(str(exc), "VALIDATION_ERROR", 422)
        return JSONResponse(
            status_code=422,
            content={
                "detail": error.detail,
                "code": error.code,
                "failure_message": error.failure_message,
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        error = failure_from_exception(exc)
        return JSONResponse(
            status_code=error.status_code,
            content={
                "detail": error.detail,
                "code": error.code,
                "failure_message": error.failure_message,
            },
        )

    return app


app = create_app()
