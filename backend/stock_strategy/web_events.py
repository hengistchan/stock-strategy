from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from .event_stream import EventBroker


def create_events_router(events: EventBroker) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["events"])

    @router.get(
        "/events",
        response_class=StreamingResponse,
        responses={
            200: {
                "description": ("Backtest, experiment, and monitoring state changes"),
                "content": {
                    "text/event-stream": {
                        "schema": {"type": "string"},
                    }
                },
            }
        },
    )
    async def event_stream(request: Request) -> StreamingResponse:
        return StreamingResponse(
            events.stream(request.is_disconnected),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    return router
