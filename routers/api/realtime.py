"""Real-time SSE endpoints for live updates."""

import asyncio
from fastapi import Request
from fastapi.responses import StreamingResponse

from core.realtime import sse_manager, CHANNEL_WATCHED, CHANNEL_UPDATES, CHANNEL_DOWNLOADS
from . import api_router


async def _event_generator(request: Request, channels: list[str]):
    queues = [sse_manager.subscribe(ch) for ch in channels]
    try:
        yield "retry: 3000\n\n"  # Reconnect after 3s
        while True:
            # Wait for any queue to have data
            done, _ = await asyncio.wait(
                [q.get() for q in queues],
                return_when=asyncio.FIRST_COMPLETED
            )
            for task in done:
                yield task.result()
    except asyncio.CancelledError:
        pass
    finally:
        for ch, q in zip(channels, queues):
            sse_manager.unsubscribe(ch, q)


@api_router.get('/realtime/updates')
async def realtime_updates(request: Request):
    """SSE stream for watched status + library updates."""
    return StreamingResponse(
        _event_generator(request, [CHANNEL_WATCHED, CHANNEL_UPDATES]),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )


@api_router.get('/realtime/downloads')
async def realtime_downloads(request: Request):
    """SSE stream for download progress."""
    return StreamingResponse(
        _event_generator(request, [CHANNEL_DOWNLOADS]),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )