from __future__ import annotations

import json
import threading
from urllib import error, request

from lmts.core.model_downloader import (
    DownloadCancelled,
    DownloadedModel,
    ModelDownloadProgress,
    ProgressSink,
)


class OllamaModelDownloader:
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        *,
        module_id: str = "ollama",
        request_timeout: float = 900.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._id = module_id
        self.request_timeout = request_timeout

    @property
    def id(self) -> str:
        return self._id

    @property
    def label(self) -> str:
        return "Ollama"

    def _open(self, req: request.Request, *, timeout: float | None = None):
        return request.urlopen(req, timeout=self.request_timeout if timeout is None else timeout)

    def available(self) -> bool:
        req = request.Request(f"{self.base_url}/api/tags", method="GET")
        try:
            with self._open(req, timeout=3.0) as response:
                return 200 <= int(getattr(response, "status", 200)) < 300
        except (OSError, error.URLError):
            return False

    def list_installed(self) -> list[DownloadedModel]:
        req = request.Request(f"{self.base_url}/api/tags", method="GET")
        try:
            with self._open(req, timeout=10.0) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (OSError, error.URLError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Ollama model discovery failed: {exc}") from exc

        models: list[DownloadedModel] = []
        raw_models = payload.get("models") if isinstance(payload, dict) else None
        if not isinstance(raw_models, list):
            raise RuntimeError("Ollama /api/tags response does not contain a models list")
        for item in raw_models:
            if not isinstance(item, dict):
                continue
            model_ref = str(item.get("name") or item.get("model") or "").strip()
            if not model_ref:
                continue
            size = item.get("size")
            models.append(
                DownloadedModel(
                    module_id=self.id,
                    model_ref=model_ref,
                    size_bytes=size if isinstance(size, int) else None,
                    metadata={
                        "digest": item.get("digest"),
                        "modified_at": item.get("modified_at"),
                        "details": item.get("details") if isinstance(item.get("details"), dict) else {},
                    },
                )
            )
        return sorted(models, key=lambda item: item.model_ref.casefold())

    def download(
        self,
        model_ref: str,
        progress: ProgressSink,
        cancel_event: threading.Event,
    ) -> None:
        model_ref = model_ref.strip()
        if not model_ref:
            raise ValueError("Ollama model reference must be non-empty")

        body = json.dumps({"model": model_ref, "stream": True}).encode("utf-8")
        req = request.Request(
            f"{self.base_url}/api/pull",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with self._open(req) as response:
                for raw_line in response:
                    if cancel_event.is_set():
                        raise DownloadCancelled(f"Ollama pull cancelled: {model_ref}")
                    if not raw_line.strip():
                        continue
                    try:
                        payload = json.loads(raw_line.decode("utf-8"))
                    except json.JSONDecodeError as exc:
                        raise RuntimeError(f"Ollama pull returned invalid NDJSON: {exc}") from exc
                    if not isinstance(payload, dict):
                        raise RuntimeError("Ollama pull response item must be a JSON object")
                    if payload.get("error"):
                        raise RuntimeError(str(payload["error"]))
                    status = str(payload.get("status") or "pulling")
                    total = payload.get("total")
                    completed = payload.get("completed")
                    progress(
                        ModelDownloadProgress(
                            module_id=self.id,
                            model_ref=model_ref,
                            status=status,
                            digest=str(payload.get("digest")) if payload.get("digest") else None,
                            total_bytes=total if isinstance(total, int) else None,
                            completed_bytes=completed if isinstance(completed, int) else None,
                        )
                    )
        except DownloadCancelled:
            raise
        except (OSError, error.URLError) as exc:
            raise RuntimeError(f"Ollama pull failed: {exc}") from exc

        if cancel_event.is_set():
            raise DownloadCancelled(f"Ollama pull cancelled: {model_ref}")

    def delete(self, model_ref: str) -> None:
        model_ref = model_ref.strip()
        if not model_ref:
            raise ValueError("Ollama model reference must be non-empty")

        body = json.dumps({"model": model_ref}).encode("utf-8")
        req = request.Request(
            f"{self.base_url}/api/delete",
            data=body,
            headers={"Content-Type": "application/json"},
            method="DELETE",
        )
        try:
            with self._open(req, timeout=30.0) as response:
                status = int(getattr(response, "status", 200))
                if not 200 <= status < 300:
                    raise RuntimeError(f"Ollama delete failed with HTTP {status}")
                raw = response.read()
        except error.HTTPError as exc:
            try:
                payload = json.loads(exc.read().decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                payload = None
            message = payload.get("error") if isinstance(payload, dict) else None
            raise RuntimeError(f"Ollama delete failed: {message or f'HTTP {exc.code}'}") from exc
        except (OSError, error.URLError) as exc:
            raise RuntimeError(f"Ollama delete failed: {exc}") from exc

        if not raw.strip():
            return
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise RuntimeError(f"Ollama delete returned invalid JSON: {exc}") from exc
        if isinstance(payload, dict) and payload.get("error"):
            raise RuntimeError(f"Ollama delete failed: {payload['error']}")
