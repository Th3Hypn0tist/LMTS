from __future__ import annotations

from lmts.core.model_downloader import ModelDownloadQueue, ModelDownloaderRegistry
from lmts.tools.ollama_downloader import OllamaModelDownloader


class ModelDownloaderPage:
    def __init__(self) -> None:
        self.registry = ModelDownloaderRegistry((OllamaModelDownloader(),))
        self.queue = ModelDownloadQueue(self.registry)
        downloaders = self.registry.downloaders()
        self.module_id = downloaders[0].id if downloaders else None
        self._installed_cache = []
        self._status = ""
        self.refresh()

    @property
    def downloader(self):
        if self.module_id is None:
            return None
        return self.registry.get(self.module_id)

    def refresh(self) -> None:
        downloader = self.downloader
        if downloader is None:
            self._installed_cache = []
            self._status = "no downloader modules registered"
            return
        if not downloader.available():
            self._installed_cache = []
            self._status = f"{downloader.label}: unavailable"
            return
        try:
            self._installed_cache = downloader.list_installed()
        except RuntimeError as exc:
            self._installed_cache = []
            self._status = str(exc)
            return
        self._status = f"{downloader.label}: {len(self._installed_cache)} installed model(s)"

    def lines(self) -> tuple[str, ...]:
        downloader = self.downloader
        module = f"{downloader.label} ({downloader.id})" if downloader is not None else "-"
        installed = [model.model_ref for model in self._installed_cache]
        queue_lines = self.queue.lines(self.module_id)
        return (
            "Model Downloader",
            "",
            f"Module    : {module}",
            f"Status    : {self._status or '-'}",
            f"Installed : {len(installed)}",
            "",
            "Installed models",
            *(f"  {model_ref}" for model_ref in installed),
            "",
            *queue_lines,
        )

    def choose_module(self, host, stdscr) -> None:
        downloaders = list(self.registry.downloaders())
        if not downloaders:
            host.message = "no downloader modules registered"
            return
        current = next((index for index, item in enumerate(downloaders) if item.id == self.module_id), 0)
        chosen = host.choose(
            stdscr,
            "Downloader module",
            [f"{item.label}  [{item.id}]  {'READY' if item.available() else 'UNAVAILABLE'}" for item in downloaders],
            current,
        )
        if chosen is None:
            return
        self.module_id = downloaders[chosen].id
        self.refresh()
        host.message = self._status

    def enqueue(self, host, stdscr) -> None:
        downloader = self.downloader
        if downloader is None:
            host.message = "select a downloader module"
            return
        if not downloader.available():
            host.message = f"model downloader is unavailable: {downloader.id}"
            return
        raw = host.input_multiline(
            stdscr,
            "Model references, one per line",
            initial="",
        )
        if raw is None:
            return
        refs = [line.strip() for line in raw.splitlines() if line.strip()]
        if not refs:
            host.message = "enter at least one model reference"
            return
        if len(refs) != len(set(refs)):
            host.message = "model reference list contains duplicates"
            return
        try:
            items = [self.queue.enqueue(downloader.id, model_ref) for model_ref in refs]
        except (KeyError, ValueError, RuntimeError) as exc:
            host.message = f"cannot queue model download: {exc}"
            return
        host.message = f"queued {len(items)} model download(s)"

    def show_progress(self, host, stdscr) -> None:
        host.text_viewer(stdscr, "Model download queue", self.queue.lines(self.module_id))
        host.message = "download queue viewed"

    def cancel(self, host, stdscr) -> None:
        items = [
            item for item in self.queue.items()
            if item.module_id == self.module_id and item.state in {"queued", "downloading"}
        ]
        if not items:
            host.message = "no queued or active model downloads"
            return
        chosen = host.choose(
            stdscr,
            "Cancel model download",
            [f"[{item.state.upper()}] {item.model_ref}" for item in items],
        )
        if chosen is None:
            return
        self.queue.cancel(items[chosen].id)
        host.message = f"cancel requested: {items[chosen].model_ref}"

    def delete(self, host, stdscr) -> None:
        downloader = self.downloader
        if downloader is None:
            host.message = "select a downloader module"
            return
        self.refresh()
        if not self._installed_cache:
            host.message = "no installed models to delete"
            return
        chosen = host.choose(
            stdscr,
            "Delete installed model",
            [model.model_ref for model in self._installed_cache],
        )
        if chosen is None:
            return
        model_ref = self._installed_cache[chosen].model_ref
        confirm = host.choose(stdscr, f"Delete {model_ref}?", ["No", "Delete"], 0)
        if confirm != 1:
            return
        try:
            downloader.delete(model_ref)
        except (OSError, ValueError, RuntimeError) as exc:
            host.message = f"model delete failed: {exc}"
            return
        self.refresh()
        host.message = f"deleted model: {model_ref}"
