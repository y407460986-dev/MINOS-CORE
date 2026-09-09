"""SSE streaming infrastructure for long-running generation tasks."""
from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncGenerator
from typing import Any

from sse_starlette.event import ServerSentEvent

from minos_core.observability.logging import get_logger

logger = get_logger(__name__)
struct_logger = get_logger(__name__)

# Registry of active channels: key = "{run_id}:{stage}"
_channels: dict[str, ProgressChannel] = {}


class ProgressChannel:
    """Thread-safe channel that bridges sync generation threads to async SSE streams."""

    def __init__(self, run_id: int, stage: str, heartbeat_interval: float = 15.0) -> None:
        self.run_id = run_id
        self.stage = stage
        self.key = f"{run_id}:{stage}"
        self._queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._closed = False
        self._heartbeat_interval = heartbeat_interval

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def emit(self, event: dict[str, Any]) -> None:
        """Push an event from a sync thread. Thread-safe."""
        if self._closed:
            return
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._queue.put_nowait, event)
        else:
            try:
                self._queue.put_nowait(event)
            except Exception as exc:
                logger.warning("sse_emit_fallback_failed", channel=self.key, error=str(exc))
                struct_logger.warning(
                    "sse.emit_fallback_failed",
                    channel=self.key,
                    error=str(exc),
                )

    def close(self) -> None:
        """Signal end of stream."""
        self._closed = True
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._queue.put_nowait, None)
        else:
            with contextlib.suppress(Exception):
                self._queue.put_nowait(None)

    async def drain(self) -> AsyncGenerator[ServerSentEvent, None]:
        """Async generator that yields SSE events until channel is closed."""
        idle_heartbeats = 0
        while True:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=self._heartbeat_interval)
            except TimeoutError:
                idle_heartbeats += 1
                if idle_heartbeats > 20:
                    self.close()
                    break
                yield ServerSentEvent(
                    data=json.dumps(
                        {
                            "type": "heartbeat",
                            "stage": self.stage,
                            "run_id": self.run_id,
                            "status": "alive",
                        },
                        ensure_ascii=False,
                    ),
                    event="heartbeat",
                )
                continue
            idle_heartbeats = 0
            if event is None:
                break
            event_type = event.get("type", "progress")
            yield ServerSentEvent(
                data=json.dumps(event, ensure_ascii=False),
                event=event_type,
            )


def create_channel(run_id: int, stage: str) -> ProgressChannel:
    """Create and register a new progress channel, or return existing one."""
    key = f"{run_id}:{stage}"
    existing = _channels.get(key)
    if existing is not None and not existing._closed:
        return existing
    channel = ProgressChannel(run_id, stage)
    _channels[channel.key] = channel
    return channel


def get_channel(run_id: int, stage: str) -> ProgressChannel | None:
    """Get an active channel, or None if not found."""
    return _channels.get(f"{run_id}:{stage}")


def remove_channel(run_id: int, stage: str) -> None:
    """Remove a channel from the registry."""
    _channels.pop(f"{run_id}:{stage}", None)
