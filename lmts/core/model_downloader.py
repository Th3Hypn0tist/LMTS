from __future__ import annotations

import threading
import uuid
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

    @property
    def artifact_id(self) -> str:
        digest = str(self.metadata.get("digest") or "").strip()
        return f"{self.module_id}:{digest}" if digest else f"{self.module_id}:{self.model_ref}"


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

    def delete(self, model_ref: str) -> None: ...


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


@dataclass(slots=True)
class ModelDownloadQueueItem:
    id: str
    module_id: str
    model_ref: str
    state: str = "queued"
    progress: ModelDownloadProgress | None = None
    error: str | None = None


class ModelDownloadQueue:
    """FIFO download queues with at most one active transfer per downloader module."""

    def __init__(self, registry: ModelDownloaderRegistry) -> None:
        self.registry = registry
        self._lock = threading.RLock()
        self._items: list[ModelDownloadQueueItem] = []
        self._workers: dict[str, threading.Thread] = {}
        self._cancel_events: dict[str, threading.Event] = {}

    def enqueue(self, module_id: str, model_ref: str) -> ModelDownloadQueueItem:
        return self.enqueue_many(module_id, (model_ref,))[0]

    def enqueue_many(
        self,
        module_id: str,
        model_refs: list[str] | tuple[str, ...],
    ) -> tuple[ModelDownloadQueueItem, ...]:
        downloader = self.registry.get(module_id)
        refs = tuple(str(value).strip() for value in model_refs)
        if not refs:
            raise ValueError("at least one model reference is required")
        if any(not value for value in refs):
            raise ValueError("model reference must be non-empty")
        if len(refs) != len(set(refs)):
            raise ValueError("model reference list contains duplicates")
        if not downloader.available():
            raise RuntimeError(f"model downloader is unavailable: {module_id}")

        with self._lock:
            live_refs = {
                item.model_ref
                for item in self._items
                if item.module_id == module_id and item.state in {"queued", "downloading"}
            }
            conflicts = [model_ref for model_ref in refs if model_ref in live_refs]
            if conflicts:
                raise ValueError(
                    "model download already queued or active: "
                    + ", ".join(f"{module_id}:{model_ref}" for model_ref in conflicts)
                )
            items = tuple(
                ModelDownloadQueueItem(id=uuid.uuid4().hex, module_id=module_id, model_ref=model_ref)
                for model_ref in refs
            )
            self._items.extend(items)
            self._ensure_worker_locked(module_id)
            return items

    def items(self) -> tuple[ModelDownloadQueueItem, ...]:
        with self._lock:
            return tuple(self._items)

    def get(self, item_id: str) -> ModelDownloadQueueItem:
        with self._lock:
            for item in self._items:
                if item.id == item_id:
                    return item
        raise KeyError(f"unknown model download queue item: {item_id}")

    def active(self, module_id: str | None = None) -> tuple[ModelDownloadQueueItem, ...]:
        with self._lock:
            return tuple(item for item in self._items if item.state == "downloading" and (module_id is None or item.module_id == module_id))

    def queued(self, module_id: str | None = None) -> tuple[ModelDownloadQueueItem, ...]:
        with self._lock:
            return tuple(item for item in self._items if item.state == "queued" and (module_id is None or item.module_id == module_id))

    def cancel(self, item_id: str) -> None:
        with self._lock:
            item = self.get(item_id)
            if item.state == "queued":
                item.state = "cancelled"
                return
            if item.state != "downloading":
                return
            event = self._cancel_events.get(item_id)
            if event is not None:
                event.set()

    def cancel_active(self, module_id: str | None = None) -> int:
        with self._lock:
            items = list(self.active(module_id))
            for item in items:
                event = self._cancel_events.get(item.id)
                if event is not None:
                    event.set()
            return len(items)

    def clear_finished(self) -> int:
        with self._lock:
            before = len(self._items)
            self._items = [item for item in self._items if item.state in {"queued", "downloading"}]
            return before - len(self._items)

    def _ensure_worker_locked(self, module_id: str) -> None:
        worker = self._workers.get(module_id)
        if worker is not None and worker.is_alive():
            return
        worker = threading.Thread(target=self._worker, args=(module_id,), name=f"lmts-download-queue-{module_id}", daemon=True)
        self._workers[module_id] = worker
        worker.start()

    def _next_queued_locked(self, module_id: str) -> ModelDownloadQueueItem | None:
        for item in self._items:
            if item.module_id == module_id and item.state == "queued":
                return item
        return None

    def _worker(self, module_id: str) -> None:
        downloader = self.registry.get(module_id)
        while True:
            with self._lock:
                item = self._next_queued_locked(module_id)
                if item is None:
                    self._workers.pop(module_id, None)
                    return
                item.state = "downloading"
                item.error = None
                item.progress = ModelDownloadProgress(module_id, item.model_ref, "starting")
                cancel_event = threading.Event()
                self._cancel_events[item.id] = cancel_event

            def on_progress(progress: ModelDownloadProgress, *, item_id: str = item.id) -> None:
                with self._lock:
                    current = self.get(item_id)
                    if progress.module_id != current.module_id or progress.model_ref != current.model_ref:
                        raise ValueError("model download progress identity mismatch")
                    current.progress = progress

            try:
                downloader.download(item.model_ref, on_progress, cancel_event)
                with self._lock:
                    item.state = "cancelled" if cancel_event.is_set() else "completed"
            except DownloadCancelled:
                with self._lock:
                    item.state = "cancelled"
            except Exception as exc:
                with self._lock:
                    item.state = "error"
                    item.error = str(exc)
            finally:
                with self._lock:
                    self._cancel_events.pop(item.id, None)

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

    def lines(self, module_id: str | None = None) -> tuple[str, ...]:
        with self._lock:
            items = [item for item in self._items if module_id is None or item.module_id == module_id]
        if not items:
            return ("Queue: empty",)

        lines = [f"Queue: {len(items)} item(s)"]
        for index, item in enumerate(items, start=1):
            marker = ">" if item.state == "downloading" else " "
            line = f"{marker}{index:02d} [{item.state.upper():11}] {item.module_id}  {item.model_ref}"
            progress = item.progress
            if progress is not None and progress.percent is not None:
                line += f"  {progress.percent:.1f}%"
            lines.append(line)
            if item.state == "downloading" and progress is not None:
                if progress.status:
                    lines.append(f"     {progress.status}")
                if progress.total_bytes is not None:
                    lines.append(f"     {self._human_bytes(progress.completed_bytes)} / {self._human_bytes(progress.total_bytes)}")
            if item.error:
                lines.append(f"     ERROR: {item.error}")
        return tuple(lines)
