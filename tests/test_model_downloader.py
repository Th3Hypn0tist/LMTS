from __future__ import annotations

import json
import threading
import time

import pytest

from lmts.core.model_downloader import (
    DownloadCancelled,
    DownloadedModel,
    ModelDownloadProgress,
    ModelDownloadQueue,
    ModelDownloaderRegistry,
)
from lmts.tools.ollama_downloader import OllamaModelDownloader
from lmts.view.model_downloader_page import ModelDownloaderPage


def _wait_for(predicate, *, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError('condition did not become true before timeout')


class ControlledDownloader:
    def __init__(self, module_id: str = 'fake') -> None:
        self._id = module_id
        self.release: dict[str, threading.Event] = {}
        self.started: list[str] = []
        self.deleted: list[str] = []
        self.installed = [DownloadedModel(module_id, 'installed:1b', 123)]
        self.active_count = 0
        self.max_active = 0
        self._lock = threading.Lock()

    @property
    def id(self) -> str:
        return self._id

    @property
    def label(self) -> str:
        return 'Fake'

    def available(self) -> bool:
        return True

    def list_installed(self) -> list[DownloadedModel]:
        return list(self.installed)

    def download(self, model_ref, progress, cancel_event) -> None:
        with self._lock:
            self.started.append(model_ref)
            self.active_count += 1
            self.max_active = max(self.max_active, self.active_count)
        try:
            progress(ModelDownloadProgress(self.id, model_ref, 'pulling', total_bytes=100, completed_bytes=50))
            release = self.release.setdefault(model_ref, threading.Event())
            while not release.wait(0.005):
                if cancel_event.is_set():
                    raise DownloadCancelled(model_ref)
            if cancel_event.is_set():
                raise DownloadCancelled(model_ref)
            progress(ModelDownloadProgress(self.id, model_ref, 'success', total_bytes=100, completed_bytes=100))
        finally:
            with self._lock:
                self.active_count -= 1

    def delete(self, model_ref: str) -> None:
        self.deleted.append(model_ref)


def test_registry_rejects_duplicate_module_ids() -> None:
    left = ControlledDownloader('same')
    right = ControlledDownloader('same')
    with pytest.raises(ValueError, match='duplicate model downloader id'):
        ModelDownloaderRegistry((left, right))


def test_queue_is_fifo_and_serial_per_module() -> None:
    downloader = ControlledDownloader()
    queue = ModelDownloadQueue(ModelDownloaderRegistry((downloader,)))

    first = queue.enqueue('fake', 'model-a')
    second = queue.enqueue('fake', 'model-b')

    _wait_for(lambda: first.state == 'downloading')
    _wait_for(lambda: first.progress is not None and first.progress.percent == 50.0)
    assert second.state == 'queued'
    assert downloader.started == ['model-a']
    assert downloader.max_active == 1
    assert first.progress is not None
    assert first.progress.percent == 50.0

    downloader.release['model-a'].set()
    _wait_for(lambda: first.state == 'completed')
    _wait_for(lambda: second.state == 'downloading')
    assert downloader.started == ['model-a', 'model-b']
    assert downloader.max_active == 1

    downloader.release['model-b'].set()
    _wait_for(lambda: second.state == 'completed')
    assert second.progress is not None
    assert second.progress.percent == 100.0
    assert downloader.max_active == 1


def test_enqueue_many_adds_all_items_before_worker_runs() -> None:
    downloader = ControlledDownloader()
    queue = ModelDownloadQueue(ModelDownloaderRegistry((downloader,)))

    items = queue.enqueue_many('fake', ['model-a', 'model-b', 'model-c'])

    assert [item.model_ref for item in items] == ['model-a', 'model-b', 'model-c']
    assert [item.model_ref for item in queue.items()] == ['model-a', 'model-b', 'model-c']
    _wait_for(lambda: items[0].state == 'downloading')
    assert items[1].state == 'queued'
    assert items[2].state == 'queued'

    for item in items:
        downloader.release[item.model_ref].set()
        _wait_for(lambda item=item: item.state == 'completed')


def test_enqueue_many_is_atomic_when_one_ref_conflicts() -> None:
    downloader = ControlledDownloader()
    queue = ModelDownloadQueue(ModelDownloaderRegistry((downloader,)))
    existing = queue.enqueue('fake', 'model-b')
    _wait_for(lambda: existing.state == 'downloading')
    before_ids = tuple(item.id for item in queue.items())

    with pytest.raises(ValueError, match='already queued or active'):
        queue.enqueue_many('fake', ['model-a', 'model-b', 'model-c'])

    assert tuple(item.id for item in queue.items()) == before_ids
    assert {item.model_ref for item in queue.items()} == {'model-b'}
    downloader.release['model-b'].set()
    _wait_for(lambda: existing.state == 'completed')


def test_enqueue_many_rejects_input_duplicates_without_side_effects() -> None:
    downloader = ControlledDownloader()
    queue = ModelDownloadQueue(ModelDownloaderRegistry((downloader,)))

    with pytest.raises(ValueError, match='contains duplicates'):
        queue.enqueue_many('fake', ['model-a', 'model-a'])

    assert queue.items() == ()


def test_queue_rejects_duplicate_live_model_ref() -> None:
    downloader = ControlledDownloader()
    queue = ModelDownloadQueue(ModelDownloaderRegistry((downloader,)))

    first = queue.enqueue('fake', 'model-a')
    _wait_for(lambda: first.state == 'downloading')

    with pytest.raises(ValueError, match='already queued or active'):
        queue.enqueue('fake', 'model-a')

    downloader.release['model-a'].set()
    _wait_for(lambda: first.state == 'completed')


def test_queue_allows_same_model_ref_after_previous_run_finishes() -> None:
    downloader = ControlledDownloader()
    queue = ModelDownloadQueue(ModelDownloaderRegistry((downloader,)))

    first = queue.enqueue('fake', 'model-a')
    _wait_for(lambda: first.state == 'downloading')
    downloader.release['model-a'].set()
    _wait_for(lambda: first.state == 'completed')

    downloader.release['model-a'] = threading.Event()
    second = queue.enqueue('fake', 'model-a')
    _wait_for(lambda: second.state == 'downloading')
    assert second.id != first.id
    downloader.release['model-a'].set()
    _wait_for(lambda: second.state == 'completed')


def test_queue_cancel_queued_item_never_starts_it() -> None:
    downloader = ControlledDownloader()
    queue = ModelDownloadQueue(ModelDownloaderRegistry((downloader,)))

    first = queue.enqueue('fake', 'model-a')
    second = queue.enqueue('fake', 'model-b')
    _wait_for(lambda: first.state == 'downloading')

    queue.cancel(second.id)
    assert second.state == 'cancelled'
    downloader.release['model-a'].set()
    _wait_for(lambda: first.state == 'completed')
    _wait_for(lambda: not queue.active() and not queue.queued())
    assert downloader.started == ['model-a']


def test_queue_cancel_active_item_propagates_cancel_event() -> None:
    downloader = ControlledDownloader()
    queue = ModelDownloadQueue(ModelDownloaderRegistry((downloader,)))

    item = queue.enqueue('fake', 'model-a')
    _wait_for(lambda: item.state == 'downloading')
    queue.cancel(item.id)
    _wait_for(lambda: item.state == 'cancelled')
    assert not queue.active()


def test_queue_rejects_progress_identity_drift() -> None:
    class BadDownloader(ControlledDownloader):
        def download(self, model_ref, progress, cancel_event) -> None:
            progress(ModelDownloadProgress(self.id, 'wrong-model', 'pulling'))

    downloader = BadDownloader()
    queue = ModelDownloadQueue(ModelDownloaderRegistry((downloader,)))
    item = queue.enqueue('fake', 'model-a')
    _wait_for(lambda: item.state == 'error')
    assert item.error == 'model download progress identity mismatch'


def test_queue_clear_finished_keeps_only_live_items() -> None:
    downloader = ControlledDownloader()
    queue = ModelDownloadQueue(ModelDownloaderRegistry((downloader,)))
    first = queue.enqueue('fake', 'model-a')
    second = queue.enqueue('fake', 'model-b')
    _wait_for(lambda: first.state == 'downloading')
    queue.cancel(second.id)
    downloader.release['model-a'].set()
    _wait_for(lambda: first.state == 'completed')
    assert queue.clear_finished() == 2
    assert queue.items() == ()


def test_page_accepts_injected_downloader_registry() -> None:
    downloader = ControlledDownloader('custom')
    page = ModelDownloaderPage(ModelDownloaderRegistry((downloader,)))
    assert page.module_id == 'custom'
    lines = page.lines()
    assert 'Module    : Fake (custom)' in lines
    assert '  installed:1b' in lines


class _Response:
    def __init__(self, *, status: int = 200, body: bytes = b'{}') -> None:
        self.status = status
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self) -> bytes:
        return self.body


def test_ollama_delete_uses_strict_delete_endpoint() -> None:
    downloader = OllamaModelDownloader('http://ollama.invalid')
    seen = {}

    def fake_open(req, *, timeout=None):
        seen['url'] = req.full_url
        seen['method'] = req.get_method()
        seen['body'] = json.loads(req.data.decode('utf-8'))
        seen['timeout'] = timeout
        return _Response(status=200, body=b'{}')

    downloader._open = fake_open
    downloader.delete('qwen3:4b')

    assert seen == {
        'url': 'http://ollama.invalid/api/delete',
        'method': 'DELETE',
        'body': {'model': 'qwen3:4b'},
        'timeout': 30.0,
    }


def test_ollama_delete_rejects_empty_model_ref() -> None:
    downloader = OllamaModelDownloader()
    with pytest.raises(ValueError, match='non-empty'):
        downloader.delete('   ')
