"""FastAPI application entry point for minos_platform."""

from __future__ import annotations

import logging
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from minos_platform import config, db, errors
from minos_platform.routers import (
    apply_review,
    artifacts,
    draft_runs,
    exports,
    input_packages,
    ppap_elements,
    ppap_packages,
    projects,
    review_patches,
    review_template,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize the async SQLite engine on startup, close it on shutdown."""
    db_url = config.get_db_url()
    await db.init_db(db_url)
    token = config.get_platform_api_token()
    if config.platform_auth_required() and not token:
        logger.error(
            "Platform API authentication is required but "
            "MINOS_PLATFORM_API_TOKEN is missing; requests will be rejected."
        )
    elif not config.platform_auth_required() and not token:
        logger.warning(
            "Platform API authentication is explicitly disabled; set "
            "MINOS_PLATFORM_AUTH_REQUIRED=1 before exposing this service."
        )
    yield
    if db._engine is not None:
        await db._engine.dispose()


app = FastAPI(
    title="MINOS Platform",
    description="PPAP project management and artifact storage layer on top of MINOS-CORE",
    version="0.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:1420",
        "http://localhost:1420",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def platform_auth_middleware(request: Request, call_next):
    if (
        request.method == "OPTIONS"
        and request.headers.get("access-control-request-method")
    ):
        return await call_next(request)

    token = config.get_platform_api_token()
    if config.platform_auth_required() and not token:
        return JSONResponse(
            status_code=401,
            content={
                "detail": "platform authentication is required but no API token is configured",
                "code": "UNAUTHORIZED",
            },
        )
    if token:
        authorization = request.headers.get("Authorization")
        expected = f"Bearer {token}"
        if not authorization or not secrets.compare_digest(authorization, expected):
            return JSONResponse(
                status_code=401,
                content={
                    "detail": "missing or invalid Authorization bearer token",
                    "code": "UNAUTHORIZED",
                },
            )
    response = await call_next(request)
    return response


@app.exception_handler(errors.APIError)
async def api_error_handler(request: Request, exc: errors.APIError):
    """Render APIError exceptions with both detail and code fields."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "code": exc.code},
    )


app.include_router(projects.router, prefix="/api", tags=["projects"])
app.include_router(input_packages.router, prefix="/api", tags=["input_packages"])
app.include_router(draft_runs.router, prefix="/api", tags=["draft_runs"])
app.include_router(review_template.router, prefix="/api", tags=["review_template"])
app.include_router(review_patches.router, prefix="/api", tags=["review_patches"])
app.include_router(apply_review.router, prefix="/api", tags=["apply_review"])
app.include_router(exports.router, prefix="/api", tags=["exports"])
app.include_router(artifacts.router, prefix="/api", tags=["artifacts"])
app.include_router(ppap_packages.router, prefix="/api", tags=["ppap_packages"])
app.include_router(ppap_elements.router, prefix="/api", tags=["ppap_elements"])
