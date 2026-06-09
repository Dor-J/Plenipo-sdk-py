"""In-memory event buffer and sidecar application state."""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from plenipo.runtime.events import AgentEvent
from plenipo.sidecar.models import event_to_dict


@dataclass
class BufferedEvent:
    """A sidecar event with monotonic sequence id."""

    event_id: int
    payload: dict[str, Any]


@dataclass
class EventBuffer:
    """Ring buffer of recent sidecar events with long-poll support."""

    max_size: int = 100
    _events: deque[BufferedEvent] = field(default_factory=deque)
    _next_id: int = field(default=1)
    _condition: asyncio.Condition = field(default_factory=asyncio.Condition)

    def append_runtime_event(self, event: AgentEvent) -> dict[str, Any] | None:
        """Appends a runtime event when it maps to a public sidecar payload."""
        payload = event_to_dict(event)
        if payload is None:
            return None

        buffered = BufferedEvent(event_id=self._next_id, payload=payload)
        self._next_id += 1
        self._events.append(buffered)
        while len(self._events) > self.max_size:
            self._events.popleft()
        return payload

    async def wait_for_events(
        self,
        *,
        since_id: int,
        timeout_ms: int,
        limit: int,
    ) -> list[BufferedEvent]:
        """Long-polls until new events exist or timeout expires."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + (timeout_ms / 1000.0)

        while True:
            matches = [item for item in self._events if item.event_id > since_id][:limit]
            if matches:
                return matches

            remaining = deadline - loop.time()
            if remaining <= 0:
                return []

            async with self._condition:
                try:
                    await asyncio.wait_for(self._condition.wait(), timeout=remaining)
                except asyncio.TimeoutError:
                    return []


async def consume_runtime_events(
    events: AsyncIterator[AgentEvent],
    buffer: EventBuffer,
) -> None:
    """Consumes runtime events into the sidecar buffer until cancelled."""
    async for event in events:
        if buffer.append_runtime_event(event) is not None:
            async with buffer._condition:
                buffer._condition.notify_all()
