from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from itertools import count
import json
from typing import Any


@dataclass(frozen=True, slots=True)
class DomainEvent:
    id: int
    type: str
    data: dict[str, Any]

    def encode(self) -> str:
        payload = json.dumps(self.data, ensure_ascii=False, separators=(",", ":"))
        return f"id: {self.id}\nevent: {self.type}\ndata: {payload}\n\n"


class EventBroker:
    """Fan out lightweight state-change notifications to local SSE clients."""

    def __init__(self, *, queue_size: int = 128) -> None:
        self.queue_size = queue_size
        self._ids = count(1)
        self._subscribers: set[asyncio.Queue[DomainEvent]] = set()

    def publish(self, event_type: str, data: dict[str, Any]) -> DomainEvent:
        event = DomainEvent(next(self._ids), event_type, dict(data))
        for queue in tuple(self._subscribers):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            queue.put_nowait(event)
        return event

    async def stream(
        self,
        is_disconnected: Callable[[], Awaitable[bool]],
    ) -> AsyncIterator[str]:
        queue: asyncio.Queue[DomainEvent] = asyncio.Queue(maxsize=self.queue_size)
        self._subscribers.add(queue)
        try:
            ready = DomainEvent(
                next(self._ids),
                "stream.ready",
                {"connected_at": _now()},
            )
            yield "retry: 3000\n" + ready.encode()
            while not await is_disconnected():
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                except TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                yield event.encode()
        finally:
            self._subscribers.discard(queue)


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")
