from __future__ import annotations

import shutil
import threading

from lmts.core.model_downloader import ModelDownloadQueue, ModelDownloaderRegistry
from lmts.core.control import RunControl
from lmts.core.model_explorer import DEFAULT_EXPLORER_REPEATS, DEFAULT_VARIANCE_THRESHOLD, assess_candidate_fit
from lmts.tools.ollama_catalog import OllamaCatalogScraper
from lmts.tools.ollama_downloader import OllamaModelDownloader
from lmts.services.model_explorer import ModelExplorerService
from lmts.tools.profile import load_system_profile


def default_model_downloader_registry() -> ModelDownloaderRegistry:
    return ModelDownloaderRegistry((OllamaModelDownloader(),))


class ModelDownloaderPage:
    def __init__(self, registry: ModelDownloaderRegistry | None = None, *, controller=None) -> None:
        self.registry = registry if registry is not None else default_model_downloader_registry()
        self.controller = controller
        self.queue = ModelDownloadQueue(self.registry)
        downloaders = self.registry.downloaders()
        self.module_id = downloaders[0].id if downloaders else None
        self._installed_cache = []
        self._status = ""
        self._catalog = OllamaCatalogScraper()
        self.variance_threshold = DEFAULT_VARIANCE_THRESHOLD
        self._explorer_thread: threading.Thread | None = None
        self._explorer_control: RunControl | None = None
        self._explorer_status = 'idle'
        self._explorer_results: list[str] = []
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
            "Model Explorer",
            "",
            "discover -> fit -> pull -> qualify -> keep/delete",
            "",
            f"Module    : {module}",
            f"Status    : {self._status or '-'}",
            f"Installed : {len(installed)}",
            f"Explorer  : {self._explorer_status}",
            f"Qualify   : {DEFAULT_EXPLORER_REPEATS}x / variance <= {self.variance_threshold:g}",
            "",
            "Explorer results",
            *(f"  {line}" for line in self._explorer_results[-12:]),
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

    @staticmethod
    def _disk_free_bytes(downloader) -> int | None:
        storage_path = getattr(downloader, 'storage_path', None)
        if not callable(storage_path):
            return None
        probe = storage_path().expanduser()
        while not probe.exists() and probe.parent != probe:
            probe = probe.parent
        try:
            return shutil.disk_usage(probe).free
        except OSError:
            return None

    def set_variance_threshold(self, host, stdscr) -> None:
        raw = host.input_multiline(
            stdscr,
            'Model Explorer variance threshold',
            initial=str(self.variance_threshold),
        )
        if raw is None:
            return
        try:
            value = float(raw.strip())
        except ValueError:
            host.message = 'variance threshold must be a number'
            return
        if not 0.0 <= value <= 0.25:
            host.message = 'variance threshold must be between 0 and 0.25'
            return
        self.variance_threshold = value
        host.message = f'Model Explorer variance threshold: {value:g}'

    def _resolve_executor(self, candidate):
        if self.controller is None:
            raise RuntimeError('Model Explorer controller is not configured')
        targets = self.controller.target_service.discover()
        for target in targets:
            if target.kind != 'model':
                continue
            metadata = target.metadata
            if (
                str(metadata.get('provider_ref') or '') == 'ollama-local'
                and str(metadata.get('model_ref') or '') == candidate.model_ref
            ):
                return target
        for target in targets:
            if target.kind == 'model' and str(target.metadata.get('model_ref') or '') == candidate.model_ref:
                return target
        raise RuntimeError(f'downloaded model was not discovered as a target: {candidate.model_ref}')

    def _explorer_provenance(self) -> dict[str, object]:
        if self.controller is None or self.controller.auth_service.local_mode:
            return {}
        identity = self.controller.auth_service.require_identity()
        return self.controller.system_service.build_run_provenance(identity.user_id).to_dict()

    def _run_candidates(self, candidates, downloader, profile, tests) -> None:
        if self.controller is None:
            self._explorer_status = 'error: controller unavailable'
            return
        service = ModelExplorerService(
            self.controller.evaluation_service,
            results_root=self.controller.results_root,
        )
        control = RunControl()
        self._explorer_control = control
        self._explorer_results = []
        try:
            provenance = self._explorer_provenance()
            for index, candidate in enumerate(candidates, start=1):
                if control.cancelled:
                    break
                self._explorer_status = f'{index}/{len(candidates)} {candidate.model_ref}: pull/qualify'

                def progress(event) -> None:
                    percent = event.percent
                    suffix = f' {percent:.1f}%' if percent is not None else ''
                    self._explorer_status = (
                        f'{index}/{len(candidates)} {candidate.model_ref}: {event.status}{suffix}'
                    )

                free_disk = self._disk_free_bytes(downloader)
                result = service.explore_one(
                    candidate,
                    downloader,
                    self._resolve_executor,
                    tests,
                    profile,
                    free_disk_bytes=free_disk,
                    repeats=DEFAULT_EXPLORER_REPEATS,
                    variance_threshold=self.variance_threshold,
                    provenance=provenance,
                    on_download_progress=progress,
                    control=control,
                )
                if result.accepted:
                    line = f'ACCEPT {candidate.model_ref}'
                elif result.deleted:
                    line = f'REJECT+DELETE {candidate.model_ref}'
                else:
                    line = f'SKIP {candidate.model_ref}'
                if result.tests:
                    worst_n = min(item.aggregate.sample_count for item in result.tests)
                    max_variance = max(item.aggregate.variance for item in result.tests)
                    line += f' / N>={worst_n} / variance={max_variance:.6f}'
                if result.error:
                    line += f' / {result.error}'
                self._explorer_results.append(line)
                self.refresh()
        finally:
            self._explorer_status = 'cancelled' if control.cancelled else 'idle'
            self._explorer_control = None
            self.refresh()

    def explore_catalog(self, host, stdscr) -> None:
        downloader = self.downloader
        if downloader is None:
            host.message = 'select a downloader module'
            return
        if self._explorer_thread is not None and self._explorer_thread.is_alive():
            host.message = 'Model Explorer is already running'
            return
        if self.controller is None:
            host.message = 'Model Explorer controller is not configured'
            return
        if downloader.id != 'ollama':
            host.message = f'catalog discovery not implemented for module: {downloader.id}'
            return
        try:
            families = self._catalog.list_families()
        except Exception as exc:
            host.message = f'catalog discovery failed: {exc}'
            return
        if not families:
            host.message = 'Ollama catalogue returned no model families'
            return
        family_index = host.choose(stdscr, 'Ollama model family', list(families), 0)
        if family_index is None:
            return
        family = families[family_index]
        try:
            candidates = self._catalog.list_tags(family)
        except Exception as exc:
            host.message = f'catalog tag discovery failed: {exc}'
            return
        if not candidates:
            host.message = f'no tags found for {family}'
            return

        profile_payload = load_system_profile()
        profile = (
            profile_payload.get('profile')
            if isinstance(profile_payload, dict) and isinstance(profile_payload.get('profile'), dict)
            else {}
        )
        free_disk = self._disk_free_bytes(downloader)
        assessments = [
            assess_candidate_fit(candidate, profile, free_disk_bytes=free_disk)
            for candidate in candidates
        ]
        options = []
        for candidate, assessment in zip(candidates, assessments):
            size = (
                f'{candidate.size_bytes / (1000 ** 3):.1f} GB'
                if isinstance(candidate.size_bytes, int)
                else '? GB'
            )
            options.append(f'{assessment.status.upper():9} {size:>9}  {candidate.model_ref}')
        chosen = host.choose_many(
            stdscr,
            f'Model Explorer: {family}',
            options,
            set(),
            include_all=False,
        )
        if chosen is None:
            return
        blocked = [
            candidates[index].model_ref
            for index in chosen
            if assessments[index].status == 'too_large'
        ]
        if blocked:
            host.message = 'blocked by hardware/disk fit: ' + ', '.join(blocked)
            return
        selected = [candidates[index] for index in sorted(chosen)]
        if not selected:
            return
        tests = list(self.controller.state.selected_tests)
        if not tests:
            host.message = 'select a qualification test suite first'
            return
        self._explorer_thread = threading.Thread(
            target=self._run_candidates,
            args=(selected, downloader, profile, tests),
            name='lmts-model-explorer',
            daemon=True,
        )
        self._explorer_thread.start()
        host.message = f'Model Explorer started: {len(selected)} candidate(s)'

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
        try:
            items = self.queue.enqueue_many(downloader.id, refs)
        except (KeyError, ValueError, RuntimeError) as exc:
            host.message = f"cannot queue model download: {exc}"
            return
        host.message = f"queued {len(items)} model download(s)"

    def show_progress(self, host, stdscr) -> None:
        host.text_viewer(stdscr, "Model download queue", self.queue.lines(self.module_id))
        host.message = "download queue viewed"

    def cancel(self, host, stdscr) -> None:
        if self._explorer_control is not None:
            self._explorer_control.request_cancel()
            host.message = 'Model Explorer cancellation requested'
            return
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
        live = {
            item.model_ref
            for item in self.queue.items()
            if item.module_id == downloader.id and item.state in {"queued", "downloading"}
        }
        if model_ref in live:
            host.message = f"cannot delete model while download is queued or active: {model_ref}"
            return
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
