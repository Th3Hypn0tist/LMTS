from __future__ import annotations

import threading
from collections.abc import Callable

from lmts.core.control import RunControl


RunWorker = Callable[[RunControl], None]


class RunLifecycleService:
    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._control: RunControl | None = None
        self._lock = threading.Lock()

    @property
    def running(self) -> bool:
        thread = self._thread
        return thread is not None and thread.is_alive()

    @property
    def control(self) -> RunControl | None:
        return self._control

    def start(self, worker: RunWorker, *, name: str = 'lmts-test-matrix') -> bool:
        with self._lock:
            if self.running:
                return False
            control = RunControl()
            self._control = control

            def run() -> None:
                try:
                    worker(control)
                finally:
                    with self._lock:
                        self._control = None
                        self._thread = None

            self._thread = threading.Thread(target=run, name=name, daemon=True)
            self._thread.start()
            return True

    def request_cancel(self) -> bool:
        control = self._control
        if control is None or not self.running:
            return False
        control.request_cancel()
        return True
