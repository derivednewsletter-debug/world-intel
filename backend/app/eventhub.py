"""In-memory pub/sub event hub.

Collectors publish new events here after inserting them. Connected SSE
clients receive them in real-time — no polling needed.

Thread-safe: collectors run in threadpool workers, SSE runs in the async
event loop.  We bridge them with a simple queue-per-subscriber pattern.
"""
import asyncio
import threading
import time
from collections import defaultdict
from typing import Any


class EventHub:
    """Fan-out hub: one publisher, many subscriber queues."""

    def __init__(self):
        self._subscribers: dict[str, asyncio.Queue] = {}
        self._lock = threading.Lock()
        self._event_count = 0
        self._last_event_at: float | None = None

    def publish(self, event: dict[str, Any]) -> None:
        """Publish a single event to all connected subscribers.

        Called from background collector threads — thread-safe.
        """
        self._event_count += 1
        self._last_event_at = time.time()
        payload = {"type": "event", "data": event, "ts": self._last_event_at}
        with self._lock:
            dead = []
            for sub_id, q in self._subscribers.items():
                try:
                    q.put_nowait(payload)
                except asyncio.QueueFull:
                    dead.append(sub_id)
            for sid in dead:
                self._subscribers.pop(sid, None)

    def publish_batch(self, events: list[dict[str, Any]]) -> None:
        """Publish a batch of events — sends one message with all events."""
        if not events:
            return
        self._event_count += len(events)
        self._last_event_at = time.time()
        payload = {"type": "batch", "data": events, "count": len(events), "ts": self._last_event_at}
        with self._lock:
            dead = []
            for sub_id, q in self._subscribers.items():
                try:
                    q.put_nowait(payload)
                except asyncio.QueueFull:
                    dead.append(sub_id)
            for sid in dead:
                self._subscribers.pop(sid, None)

    def publish_stats(self, stats: dict) -> None:
        """Publish a stats update (source status changes, etc.)."""
        payload = {"type": "stats", "data": stats, "ts": time.time()}
        with self._lock:
            dead = []
            for sub_id, q in self._subscribers.items():
                try:
                    q.put_nowait(payload)
                except asyncio.QueueFull:
                    dead.append(sub_id)
            for sid in dead:
                self._subscribers.pop(sid, None)

    def subscribe(self) -> tuple[str, asyncio.Queue]:
        """Create a new subscriber. Returns (subscriber_id, queue)."""
        sub_id = f"sub-{time.time_ns()}"
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        with self._lock:
            self._subscribers[sub_id] = q
        return sub_id, q

    def unsubscribe(self, sub_id: str) -> None:
        with self._lock:
            self._subscribers.pop(sub_id, None)

    @property
    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subscribers)

    @property
    def total_events_published(self) -> int:
        return self._event_count

    @property
    def last_event_at(self) -> float | None:
        return self._last_event_at


# Global singleton — imported by collectors and the SSE endpoint.
hub = EventHub()
