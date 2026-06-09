"""Durable sidecar event log with long-poll and SSE wakeups."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from plenipo.runtime.events import AgentEvent
from plenipo.runtime.store import RuntimeStore, SidecarEventRecord
from plenipo.runtime.inbox_crypto import (
    SidecarStoreKeyError,
    read_sidecar_store_key,
)
from plenipo.sidecar.models import sidecar_event_to_api_dict


@dataclass
class DurableEventService:
    """SQLite-backed durable event service with long-poll support."""

    store: RuntimeStore
    _condition: asyncio.Condition = field(default_factory=asyncio.Condition)

    async def notify(self) -> None:
        """Wakes long-poll waiters after a new durable event is persisted."""
        async with self._condition:
            self._condition.notify_all()

    async def wait_for_events(
        self,
        *,
        after_id: int,
        timeout_ms: int,
        limit: int,
        include_plaintext: bool = True,
    ) -> tuple[list[dict[str, Any]], int]:
        """Long-polls durable events with id greater than after_id."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + (timeout_ms / 1000.0)

        while True:
            rows = self.store.list_sidecar_events(after_id=after_id, limit=limit)
            if rows:
                return self._rows_to_api(rows, include_plaintext=include_plaintext), rows[-1].id

            remaining = deadline - loop.time()
            if remaining <= 0:
                return [], after_id

            async with self._condition:
                try:
                    await asyncio.wait_for(self._condition.wait(), timeout=remaining)
                except asyncio.TimeoutError:
                    return [], after_id

    def list_events_after(
        self,
        *,
        after_id: int,
        limit: int,
        include_plaintext: bool = True,
    ) -> tuple[list[dict[str, Any]], int]:
        """Returns durable events without blocking."""
        rows = self.store.list_sidecar_events(after_id=after_id, limit=limit)
        if not rows:
            return [], after_id
        return self._rows_to_api(rows, include_plaintext=include_plaintext), rows[-1].id

    def _rows_to_api(
        self,
        rows: list[SidecarEventRecord],
        *,
        include_plaintext: bool,
    ) -> list[dict[str, Any]]:
        store_key = None
        if include_plaintext and any(row.event_type == 'message' for row in rows):
            if self.store.count_inbox_messages() > 0:
                store_key = read_sidecar_store_key()
                if store_key is None:
                    raise SidecarStoreKeyError(
                        'sidecar store key missing; cannot decrypt encrypted local inbox',
                    )
        events: list[dict[str, Any]] = []
        for row in rows:
            events.append(
                sidecar_event_to_api_dict(
                    row,
                    store=self.store,
                    include_plaintext=include_plaintext,
                    store_key=store_key,
                )
            )
        return events


# Backward-compatible alias used by existing imports/tests.
EventBuffer = DurableEventService


async def consume_runtime_events(
    events: AsyncIterator[AgentEvent],
    buffer: DurableEventService,
) -> None:
    """Wakes durable event waiters when runtime emits public events."""
    async for event in events:
        if event.type in ('message', 'delivery_receipt'):
            await buffer.notify()
