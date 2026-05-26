"""FastAPI application entry point for minos_platform."""

from __future__ import annotations

import logging
import os
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


def _allow_no_auth() -> bool:
    return os.getenv("MINOS_PLATFORM_ALLOW_NO_AUTH", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize the async SQLite engine on startup, close it on shutdown."""
    db_url = config.get_db_url()
    await db.init_db(db_url)
    token = os.getenv("MINOS_PLATFORM_API_TOKEN")
    if not token and _allow_no_auth():
        logger.warning(
            "MINOS_PLATFORM_API_TOKEN is not set and MINOS_PLATFORM_ALLOW_NO_AUTH "
            "is enabled — platform API is running without authentication."
        )
    elif not token:
        logger.warning(
            "MINOS_PLATFORM_API_TOKEN is not set — platform API will reject "
            "requests until a bearer token is configured, unless "
            "MINOS_PLATFORM_ALLOW_NO_AUTH enables local dev mode."
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
        "http://127.0.0.1:*",
        "http://localhost:*",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def platform_auth_middleware(request: Request, call_next):
    token = os.getenv("MINOS_PLATFORM_API_TOKEN")
    if not token and _allow_no_auth():
        return await call_next(request)

    authorization = request.headers.get("Authorization")
    expected = f"Bearer {token}" if token else ""
    if authorization != expected:
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
