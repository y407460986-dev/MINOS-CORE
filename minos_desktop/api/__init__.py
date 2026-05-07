"""Local FastAPI sidecar for the MINOS desktop workbench."""

from .app import app, create_app

__all__ = ["app", "create_app"]
