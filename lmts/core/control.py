from __future__ import annotations

import threading


class RunCancelled(RuntimeError):
    """Raised at safe checkpoints after cancellation has been requested."""


class RunControl:
    """Thread-safe cooperative cancellation state for one run matrix."""

    def __init__(self) -> None:
        self._cancel = threading.Event()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def request_cancel(self) -> None:
        self._cancel.set()

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise RunCancelled("run cancelled by user")
