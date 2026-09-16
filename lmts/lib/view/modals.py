from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

from .events import UIEventBus


T = TypeVar('T')


@dataclass(frozen=True, slots=True)
class ModalState:
    owner: str
    kind: str
    depth: int
    thread_id: int


class ModalManager:
    """Owns one modal interaction stack for a UI host.

    Nested modal calls are allowed only on the same thread and owner. This lets
    composite dialogs reuse primitive host dialogs while still preventing two
    independent UI flows from owning curses input at the same time.
    """

    def __init__(self, events: UIEventBus | None = None) -> None:
        self.events = events
        self._lock = threading.RLock()
        self._stack: list[tuple[str, str]] = []
        self._thread_id: int | None = None

    @property
    def active(self) -> ModalState | None:
        with self._lock:
            if not self._stack or self._thread_id is None:
                return None
            owner, kind = self._stack[-1]
            return ModalState(
                owner=owner,
                kind=kind,
                depth=len(self._stack),
                thread_id=self._thread_id,
            )

    def run(self, owner: str, kind: str, callback: Callable[[], T]) -> T:
        if not owner or owner != owner.strip():
            raise ValueError('modal owner must be a non-empty canonical string')
        if not kind or kind != kind.strip():
            raise ValueError('modal kind must be a non-empty canonical string')
        if not callable(callback):
            raise TypeError('modal callback must be callable')

        thread_id = threading.get_ident()
        with self._lock:
            if self._stack:
                root_owner = self._stack[0][0]
                if self._thread_id != thread_id:
                    raise RuntimeError(
                        f'modal already owned by {root_owner} on another thread'
                    )
                if root_owner != owner:
                    raise RuntimeError(
                        f'modal already owned by {root_owner}; {owner} cannot nest inside it'
                    )
            else:
                self._thread_id = thread_id
            self._stack.append((owner, kind))
            depth = len(self._stack)

        if self.events is not None:
            self.events.publish(
                'ui.modal.opened',
                {'owner': owner, 'kind': kind, 'depth': depth},
                source='modal_manager',
            )

        try:
            return callback()
        finally:
            with self._lock:
                popped = self._stack.pop()
                if popped != (owner, kind):
                    raise RuntimeError('modal ownership stack corrupted')
                remaining = len(self._stack)
                if not self._stack:
                    self._thread_id = None
            if self.events is not None:
                self.events.publish(
                    'ui.modal.closed',
                    {'owner': owner, 'kind': kind, 'depth': remaining},
                    source='modal_manager',
                )
