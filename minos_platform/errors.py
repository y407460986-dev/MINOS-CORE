"""Structured API error types for minos_platform."""

from __future__ import annotations

from fastapi import HTTPException


class APIError(HTTPException):
    """Base exception for platform-level API errors.

    Inherits from HTTPException so FastAPI routes can raise these directly.
    """

    def __init__(self, message: str, code: str, status_code: int = 422) -> None:
        self.message = message
        self.code = code
        super().__init__(status_code=status_code, detail=message)


class NotFoundError(APIError):
    def __init__(self, resource: str, id: str) -> None:
        super().__init__(
            message=f"{resource} with id={id!r} not found",
            code=f"NOT_FOUND_{resource.upper()}",
            status_code=404,
        )


class InvalidStateError(APIError):
    def __init__(self, current: str, required: str) -> None:
        super().__init__(
            message=f"Project is in status {current!r} but must be {required!r} to perform this action",
            code="INVALID_STATE_TRANSITION",
            status_code=409,
        )


def map_core_error(exc: BaseException) -> APIError:
    """Map a minos_core exception to a platform APIError.

    Preserves all error detail so failures are fully auditable.
    """
    from minos_core.quality_gates import ExportGateError
    from minos_core.review_patch import ReviewPatchError
    from minos_core.schemas import BundleSchemaError

    if isinstance(exc, ReviewPatchError):
        return APIError(str(exc), code="REVIEW_PATCH_ERROR")
    if isinstance(exc, ExportGateError):
        return APIError(str(exc), code="EXPORT_GATE_ERROR")
    if isinstance(exc, BundleSchemaError):
        return APIError(str(exc), code="BUNDLE_SCHEMA_ERROR")
    if isinstance(exc, ValueError):
        return APIError(str(exc), code="VALUE_ERROR")
    if isinstance(exc, TypeError):
        return APIError(str(exc), code="TYPE_ERROR")
    return APIError(str(exc), code="INTERNAL_ERROR")
