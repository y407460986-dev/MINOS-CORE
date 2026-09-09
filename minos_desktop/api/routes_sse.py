"""SSE streaming endpoints for chain generation progress."""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, Request
from sse_starlette.event import ServerSentEvent
from sse_starlette.sse import EventSourceResponse

from .auth import require_stream_token
from .sse import get_channel

router = APIRouter(prefix="/api/runs", tags=["sse"])


@router.get("/{run_id}/chain/{stage}/stream", dependencies=[Depends(require_stream_token)])
async def chain_generation_stream(
    run_id: int, stage: str, request: Request
) -> EventSourceResponse:
    """SSE endpoint that streams generation progress for a stage."""
    channel = get_channel(run_id, stage)
    if channel is None:
        # No active generation — return a single "done" event
        async def _empty() -> AsyncGenerator[ServerSentEvent, None]:
            yield ServerSentEvent(
                data=json.dumps(
                    {
                        "type": "done",
                        "stage": stage,
                        "run_id": run_id,
                        "total_rows": 0,
                        "status": "not_running",
                    }
                ),
                event="done",
            )
        return EventSourceResponse(_empty())

    # Bind the current event loop so the channel can push from sync threads
    channel.bind_loop(asyncio.get_running_loop())
    return EventSourceResponse(channel.drain())
