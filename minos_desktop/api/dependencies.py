"""Request-scoped service dependencies for the desktop API."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, cast

from fastapi import Depends, Request

from minos_desktop.services import DesktopProjectStore, DesktopRunService, RunRepository


def get_run_repository(request: Request) -> RunRepository:
    factory = cast(Callable[[], RunRepository], request.app.state.run_repository_factory)
    return factory()


RunRepositoryDep = Annotated[RunRepository, Depends(get_run_repository)]


def get_run_service(repository: RunRepositoryDep) -> DesktopRunService:
    return DesktopRunService(repository=repository)


RunServiceDep = Annotated[DesktopRunService, Depends(get_run_service)]


def get_project_store(request: Request) -> DesktopProjectStore:
    factory = cast(
        Callable[[], DesktopProjectStore], request.app.state.project_store_factory
    )
    return factory()


ProjectStoreDep = Annotated[DesktopProjectStore, Depends(get_project_store)]
