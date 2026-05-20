"""SSE streaming infrastructure for long-running generation tasks."""
from __future__ import annotations
import asyncio
import json
import logging
from typing import Any, AsyncGenerator
from sse_starlette.sse import ServerSentEvent

logger = logging.getLogger(__name__)

# Registry of active channels: key = "{run_id}:{stage}"
_channels: dict[str, "ProgressChannel"] = {}


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
                logger.warning("SSE emit fallback failed for %s: %s", self.key, exc)

    def close(self) -> None:
        """Signal end of stream."""
        self._closed = True
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._queue.put_nowait, None)
        else:
            try:
                self._queue.put_nowait(None)
            except Exception:
                pass

    async def drain(self) -> AsyncGenerator[ServerSentEvent, None]:
        """Async generator that yields SSE events until channel is closed."""
        while True:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=self._heartbeat_interval)
            except asyncio.TimeoutError:
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
