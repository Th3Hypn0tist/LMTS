from __future__ import annotations

import json
import time
from urllib import request

from lmts.core.models import ModelDescriptor, NormalizedResponse, NormalizedTiming, NormalizedUsage


class OllamaProvider:
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        provider_id: str = "ollama-local",
        *,
        discovery_timeout: float = 10.0,
        generation_timeout: float = 900.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._id = provider_id
        self.discovery_timeout = discovery_timeout
        self.generation_timeout = generation_timeout

    @property
    def id(self) -> str:
        return self._id

    def _json(self, path: str, payload: dict | None = None, *, timeout: float | None = None) -> dict:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        req = request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="GET" if data is None else "POST",
        )
        effective_timeout = self.discovery_timeout if timeout is None else timeout
        with request.urlopen(req, timeout=effective_timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def discover_models(self) -> list[ModelDescriptor]:
        payload = self._json("/api/tags", timeout=self.discovery_timeout)
        descriptors: list[ModelDescriptor] = []
        for item in payload.get("models", []):
            name = item.get("name") or item.get("model")
            if not name:
                continue
            descriptors.append(
                ModelDescriptor(
                    id=f"{self.id}:{name}",
                    provider_ref=self.id,
                    model_ref=name,
                    location="local",
                    metadata={
                        "size": item.get("size"),
                        "digest": item.get("digest"),
                        "modified_at": item.get("modified_at"),
                        "details": item.get("details") or {},
                    },
                )
            )
        return sorted(descriptors, key=lambda item: item.model_ref)

    def generate(self, model: ModelDescriptor, prompt: str) -> NormalizedResponse:
        started = time.perf_counter()
        raw = self._json(
            "/api/generate",
            {"model": model.model_ref, "prompt": prompt, "stream": False},
            timeout=self.generation_timeout,
        )
        total_ms = (time.perf_counter() - started) * 1000.0
        eval_count = raw.get("eval_count")
        prompt_eval_count = raw.get("prompt_eval_count")
        eval_duration = raw.get("eval_duration")
        tokens_per_second = None
        if isinstance(eval_count, int) and isinstance(eval_duration, int) and eval_duration > 0:
            tokens_per_second = eval_count / (eval_duration / 1_000_000_000)
        normalized_raw = dict(raw)
        if tokens_per_second is not None:
            normalized_raw["lmts_tokens_per_second"] = tokens_per_second
        return NormalizedResponse(
            text=raw.get("response", ""),
            finish_reason=raw.get("done_reason"),
            usage=NormalizedUsage(
                input_tokens=prompt_eval_count if isinstance(prompt_eval_count, int) else None,
                output_tokens=eval_count if isinstance(eval_count, int) else None,
            ),
            timing=NormalizedTiming(total_ms=total_ms),
            raw=normalized_raw,
        )
