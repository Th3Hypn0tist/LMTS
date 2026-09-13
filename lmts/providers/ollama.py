from __future__ import annotations

import json
import time
from urllib import request

from lmts.core.models import ModelDescriptor, NormalizedResponse, NormalizedTiming, NormalizedUsage


class OllamaProvider:
    def __init__(self, base_url: str = "http://127.0.0.1:11434", provider_id: str = "ollama-local") -> None:
        self.base_url = base_url.rstrip("/")
        self._id = provider_id

    @property
    def id(self) -> str:
        return self._id

    def _json(self, path: str, payload: dict | None = None) -> dict:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        req = request.Request(f"{self.base_url}{path}", data=data, headers={"Content-Type": "application/json"}, method="GET" if data is None else "POST")
        with request.urlopen(req, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))

    def discover_models(self) -> list[ModelDescriptor]:
        payload = self._json("/api/tags")
        descriptors: list[ModelDescriptor] = []
        for item in payload.get("models", []):
            name = item.get("name") or item.get("model")
            if not name:
                continue
            descriptors.append(ModelDescriptor(id=f"{self.id}:{name}", provider_ref=self.id, model_ref=name, location="local", metadata={"size": item.get("size"), "digest": item.get("digest"), "modified_at": item.get("modified_at"), "details": item.get("details") or {}}))
        return sorted(descriptors, key=lambda item: item.model_ref)

    def generate(self, model: ModelDescriptor, prompt: str) -> NormalizedResponse:
        started = time.perf_counter()
        raw = self._json("/api/generate", {"model": model.model_ref, "prompt": prompt, "stream": False})
        total_ms = (time.perf_counter() - started) * 1000.0
        eval_count = raw.get("eval_count")
        prompt_eval_count = raw.get("prompt_eval_count")
        return NormalizedResponse(text=raw.get("response", ""), finish_reason=raw.get("done_reason"), usage=NormalizedUsage(input_tokens=prompt_eval_count if isinstance(prompt_eval_count, int) else None, output_tokens=eval_count if isinstance(eval_count, int) else None), timing=NormalizedTiming(total_ms=total_ms), raw=raw)
