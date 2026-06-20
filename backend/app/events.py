from __future__ import annotations

import asyncio
import time
from typing import Any


class EventBus:
    """Per-run pub/sub with replay. MVP-simple; one process, in-memory."""

    def __init__(self) -> None:
        self._history: dict[str, list[dict]] = {}
        self._subs: dict[str, list[asyncio.Queue]] = {}

    def history(self, run_id: str) -> list[dict]:
        return list(self._history.get(run_id, []))

    async def publish(self, run_id: str, type_: str, **payload: Any) -> None:
        event = {"type": type_, "ts": time.time(), **payload}
        self._history.setdefault(run_id, []).append(event)
        for q in list(self._subs.get(run_id, [])):
            await q.put(event)

    def subscribe(self, run_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subs.setdefault(run_id, []).append(q)
        return q

    def unsubscribe(self, run_id: str, q: asyncio.Queue) -> None:
        if run_id in self._subs and q in self._subs[run_id]:
            self._subs[run_id].remove(q)


bus = EventBus()
