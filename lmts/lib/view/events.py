from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class UIEvent:
    topic: str
    payload: object = None
    source: str = ''

    def __post_init__(self) -> None:
        if not self.topic or self.topic != self.topic.strip():
            raise ValueError('UI event topic must be a non-empty canonical string')
        if self.source != self.source.strip():
            raise ValueError('UI event source must be canonical when provided')


UIEventHandler = Callable[[UIEvent], None]


class UIEventBus:
    """Synchronous, thread-safe in-process UI event bus.

    Delivery errors are intentionally not swallowed. A broken subscriber is a
    broken UI contract and must be visible to the caller.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[UIEventHandler]] = {}
        self._lock = threading.RLock()

    def subscribe(self, topic: str, handler: UIEventHandler) -> None:
        if not topic or topic != topic.strip():
            raise ValueError('UI event topic must be a non-empty canonical string')
        if not callable(handler):
            raise TypeError('UI event handler must be callable')
        with self._lock:
            handlers = self._handlers.setdefault(topic, [])
            if handler in handlers:
                raise ValueError(f'UI event handler already subscribed: {topic}')
            handlers.append(handler)

    def unsubscribe(self, topic: str, handler: UIEventHandler) -> None:
        with self._lock:
            handlers = self._handlers.get(topic)
            if handlers is None or handler not in handlers:
                raise ValueError(f'UI event handler is not subscribed: {topic}')
            handlers.remove(handler)
            if not handlers:
                del self._handlers[topic]

    def publish(
        self,
        event: UIEvent | str,
        payload: object = None,
        *,
        source: str = '',
    ) -> UIEvent:
        resolved = event if isinstance(event, UIEvent) else UIEvent(event, payload, source)
        with self._lock:
            handlers = tuple(self._handlers.get(resolved.topic, ()))
        for handler in handlers:
            handler(resolved)
        return resolved
