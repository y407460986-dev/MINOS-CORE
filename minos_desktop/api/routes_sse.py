"""SSE streaming endpoints for chain generation progress."""
from __future__ import annotations
import asyncio
import json
import os
from fastapi import APIRouter, Depends, Request
from sse_starlette.sse import EventSourceResponse, ServerSentEvent

from minos_desktop.services import DesktopRunService

from .auth import require_api_token
from .schemas import APIError
from .sse import create_sse_token, get_channel, is_valid_sse_token

router = APIRouter(prefix="/api", tags=["sse"])


@router.get("/sse-token", dependencies=[Depends(require_api_token)])
def issue_sse_token() -> dict[str, object]:
    token = os.getenv("MINOS_DESKTOP_API_TOKEN")
    if not token:
        return {"token": "", "expires_in": 0}
    return {"token": create_sse_token(token), "expires_in": 300}


@router.get("/runs/{run_id}/chain/{stage}/stream")
async def chain_generation_stream(run_id: int, stage: str, request: Request):
    """SSE endpoint that streams generation progress for a stage."""
    _require_sse_token(request)
    channel = get_channel(run_id, stage)
    if channel is None:
        terminal = _persisted_done_event(request, run_id, stage)

        async def _empty():
            yield ServerSentEvent(
                data=json.dumps(terminal, ensure_ascii=False),
                event="done",
            )
        return EventSourceResponse(_empty())

    # Bind the current event loop so the channel can push from sync threads
    channel.bind_loop(asyncio.get_running_loop())
    return EventSourceResponse(channel.drain())


def _require_sse_token(request: Request) -> None:
    token = os.getenv("MINOS_DESKTOP_API_TOKEN")
    if not token:
        return
    supplied = (
        request.query_params.get("token")
        or request.cookies.get("minos_desktop_api_token")
        or request.cookies.get("minos_api_token")
    )
    if not is_valid_sse_token(token, supplied or ""):
        raise APIError(
            detail="missing or invalid SSE token",
            code="UNAUTHORIZED",
            status_code=401,
        )


def _persisted_done_event(request: Request, run_id: int, stage: str) -> dict[str, object]:
    service = DesktopRunService(request.app.state.db_path)
    run = service.get_run(run_id)
    chain_stages = run.state.chain_stages
    stage_state = getattr(chain_stages, stage, None) if chain_stages is not None else None
    status = str(getattr(stage_state, "status", "") or "not_running")
    total_rows = int(getattr(stage_state, "row_count", 0) or 0)
    if total_rows <= 0:
        total_rows = _stage_row_count(run.current_result, stage)
    event: dict[str, object] = {
        "type": "done",
        "stage": stage,
        "run_id": run_id,
        "total_rows": total_rows,
        "status": status,
    }
    if status == "failed" and run.failure_message:
        event["failure_message"] = run.failure_message
    return event


def _stage_row_count(result: dict[str, object], stage: str) -> int:
    key = {"pfd": "process_flow", "pfmea": "pfmea", "cp": "control_plan"}.get(stage, stage)
    table = result.get(key) if isinstance(result, dict) else None
    if not isinstance(table, dict):
        return 0
    rows_key = "steps" if key == "process_flow" else "rows"
    rows = table.get(rows_key)
    return len(rows) if isinstance(rows, list) else 0
