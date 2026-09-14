from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol


class DownloadCancelled(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class DownloadedModel:
    module_id: str
    model_ref: str
    size_bytes: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ModelDownloadProgress:
    module_id: str
    model_ref: str
    status: str
    digest: str | None = None
    total_bytes: int | None = None
    completed_bytes: int | None = None

    @property
    def percent(self) -> float | None:
        if not isinstance(self.total_bytes, int) or self.total_bytes <= 0:
            return None
        if not isinstance(self.completed_bytes, int) or self.completed_bytes < 0:
            return None
        return min(100.0, max(0.0, self.completed_bytes * 100.0 / self.total_bytes))


ProgressSink = Callable[[ModelDownloadProgress], None]


class ModelDownloader(Protocol):
    @property
    def id(self) -> str: ...

    @property
    def label(self) -> str: ...

    def available(self) -> bool: ...

    def list_installed(self) -> list[DownloadedModel]: ...

    def download(
        self,
        model_ref: str,
        progress: ProgressSink,
        cancel_event: threading.Event,
    ) -> None: ...


class ModelDownloaderRegistry:
    def __init__(self, downloaders: list[ModelDownloader] | tuple[ModelDownloader, ...] = ()) -> None:
        self._downloaders: dict[str, ModelDownloader] = {}
        for downloader in downloaders:
            self.register(downloader)

    def register(self, downloader: ModelDownloader) -> None:
        downloader_id = downloader.id.strip()
        if not downloader_id:
            raise ValueError("model downloader id must be non-empty")
        if downloader_id in self._downloaders:
            raise ValueError(f"duplicate model downloader id: {downloader_id}")
        self._downloaders[downloader_id] = downloader

    def get(self, downloader_id: str) -> ModelDownloader:
        try:
            return self._downloaders[downloader_id]
        except KeyError as exc:
            raise KeyError(f"unknown model downloader: {downloader_id}") from exc

    def downloaders(self) -> tuple[ModelDownloader, ...]:
        return tuple(self._downloaders[key] for key in sorted(self._downloaders))


class ModelDownloadJob:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cancel_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._running = False
        self._state = "idle"
        self._module_id = ""
        self._model_ref = ""
        self._progress: ModelDownloadProgress | None = None
        self._error: str | None = None

    @property
    def running(self) -> bool:
        with self._lock:
            return self._running

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    @property
    def error(self) -> str | None:
        with self._lock:
            return self._error

    def start(self, downloader: ModelDownloader, model_ref: str) -> None:
        model_ref = model_ref.strip()
        if not model_ref:
            raise ValueError("model reference must be non-empty")
        with self._lock:
            if self._running:
                raise RuntimeError("model download already running")
            self._cancel_event = threading.Event()
            self._running = True
            self._state = "running"
            self._module_id = downloader.id
            self._model_ref = model_ref
            self._progress = ModelDownloadProgress(downloader.id, model_ref, "starting")
            self._error = None
        self._thread = threading.Thread(
            target=self._run,
            args=(downloader, model_ref),
            name=f"lmts-download-{downloader.id}",
            daemon=True,
        )
        self._thread.start()

    def _run(self, downloader: ModelDownloader, model_ref: str) -> None:
        try:
            downloader.download(model_ref, self._on_progress, self._cancel_event)
            with self._lock:
                if self._cancel_event.is_set():
                    self._state = "cancelled"
                else:
                    self._state = "completed"
        except DownloadCancelled:
            with self._lock:
                self._state = "cancelled"
        except Exception as exc:
            with self._lock:
                self._state = "error"
                self._error = str(exc)
        finally:
            with self._lock:
                self._running = False

    def _on_progress(self, progress: ModelDownloadProgress) -> None:
        with self._lock:
            if progress.module_id != self._module_id or progress.model_ref != self._model_ref:
                raise ValueError("model download progress identity mismatch")
            self._progress = progress

    def cancel(self) -> None:
        with self._lock:
            if not self._running:
                return
            self._cancel_event.set()

    @staticmethod
    def _human_bytes(value: int | None) -> str:
        if not isinstance(value, int) or value < 0:
            return "-"
        units = ("B", "KiB", "MiB", "GiB", "TiB")
        number = float(value)
        unit = units[0]
        for candidate in units:
            unit = candidate
            if number < 1024.0 or candidate == units[-1]:
                break
            number /= 1024.0
        return f"{number:.2f} {unit}"

    def lines(self) -> tuple[str, ...]:
        with self._lock:
            state = self._state
            module_id = self._module_id
            model_ref = self._model_ref
            progress = self._progress
            error = self._error
        lines = [
            f"Module: {module_id or '-'}",
            f"Model : {model_ref or '-'}",
            f"State : {state}",
        ]
        if progress is not None:
            lines.append(f"Status: {progress.status}")
            if progress.digest:
                lines.append(f"Layer : {progress.digest[:28]}")
            if progress.total_bytes is not None:
                completed = self._human_bytes(progress.completed_bytes)
                total = self._human_bytes(progress.total_bytes)
                percent = progress.percent
                suffix = "" if percent is None else f" ({percent:.1f}%)"
                lines.append(f"Data  : {completed} / {total}{suffix}")
        if error:
            lines.append(f"Error : {error}")
        return tuple(lines)
