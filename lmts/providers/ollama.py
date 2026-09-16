from __future__ import annotations

import json
import time
from collections.abc import Callable
from urllib import request

from lmts.core.models import (
    ModelDescriptor,
    NormalizedPerformance,
    NormalizedResponse,
    NormalizedTiming,
    NormalizedUsage,
    ResponseStreamChunk,
)


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
        self._capabilities_cache: dict[str, frozenset[str]] = {}

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

    def _model_capabilities(self, model_ref: str) -> frozenset[str]:
        cached = self._capabilities_cache.get(model_ref)
        if cached is not None:
            return cached
        payload = self._json(
            "/api/show",
            {"model": model_ref},
            timeout=self.discovery_timeout,
        )
        raw = payload.get("capabilities")
        capabilities = frozenset(str(value) for value in raw) if isinstance(raw, list) else frozenset()
        self._capabilities_cache[model_ref] = capabilities
        return capabilities

    @staticmethod
    def _generation_payload(
        model: ModelDescriptor,
        prompt: str,
        *,
        stream: bool,
        capabilities: frozenset[str],
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "model": model.model_ref,
            "prompt": prompt,
            "stream": stream,
        }
        if "thinking" in capabilities:
            payload["think"] = True
        return payload

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

    @staticmethod
    def _duration_ms(raw: dict, key: str) -> float | None:
        value = raw.get(key)
        if isinstance(value, int) and value >= 0:
            return value / 1_000_000.0
        return None

    @staticmethod
    def _rate(count: object, duration_ns: object) -> float | None:
        if isinstance(count, int) and isinstance(duration_ns, int) and duration_ns > 0:
            return count / (duration_ns / 1_000_000_000.0)
        return None

    @classmethod
    def _normalized_response(cls, raw: dict, text: str, total_ms: float, ttft_ms: float | None) -> NormalizedResponse:
        eval_count = raw.get("eval_count")
        prompt_eval_count = raw.get("prompt_eval_count")
        eval_duration = raw.get("eval_duration")
        prompt_eval_duration = raw.get("prompt_eval_duration")
        generation_rate = cls._rate(eval_count, eval_duration)
        prompt_rate = cls._rate(prompt_eval_count, prompt_eval_duration)
        return NormalizedResponse(
            text=text,
            finish_reason=raw.get("done_reason"),
            usage=NormalizedUsage(
                input_tokens=prompt_eval_count if isinstance(prompt_eval_count, int) else None,
                output_tokens=eval_count if isinstance(eval_count, int) else None,
            ),
            timing=NormalizedTiming(
                ttft_ms=ttft_ms,
                total_ms=total_ms,
                load_ms=cls._duration_ms(raw, "load_duration"),
                prompt_eval_ms=cls._duration_ms(raw, "prompt_eval_duration"),
                generation_ms=cls._duration_ms(raw, "eval_duration"),
            ),
            performance=NormalizedPerformance(
                prompt_tokens_per_second=prompt_rate,
                generation_tokens_per_second=generation_rate,
            ),
            raw=dict(raw),
        )

    def generate(self, model: ModelDescriptor, prompt: str) -> NormalizedResponse:
        capabilities = self._model_capabilities(model.model_ref)
        payload = self._generation_payload(model, prompt, stream=False, capabilities=capabilities)
        started = time.perf_counter()
        raw = self._json(
            "/api/generate",
            payload,
            timeout=self.generation_timeout,
        )
        total_ms = (time.perf_counter() - started) * 1000.0
        return self._normalized_response(raw, raw.get("response", ""), total_ms, None)

    def generate_stream(
        self,
        model: ModelDescriptor,
        prompt: str,
        sink: Callable[[ResponseStreamChunk], None],
    ) -> NormalizedResponse:
        """Generate through Ollama NDJSON and expose provider response channels."""
        capabilities = self._model_capabilities(model.model_ref)
        payload = self._generation_payload(model, prompt, stream=True, capabilities=capabilities)
        data = json.dumps(payload).encode("utf-8")
        req = request.Request(
            f"{self.base_url}/api/generate",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        text_parts: list[str] = []
        raw_chunks: list[dict] = []
        final: dict = {}
        first_thinking_at: float | None = None
        first_text_at: float | None = None
        started = time.perf_counter()

        with request.urlopen(req, timeout=self.generation_timeout) as response:
            for line in response:
                if not line.strip():
                    continue
                raw = json.loads(line.decode("utf-8"))
                raw_chunks.append(raw)
                final = raw

                thinking = raw.get("thinking")
                if isinstance(thinking, str) and thinking:
                    if first_thinking_at is None:
                        first_thinking_at = time.perf_counter()
                    sink(ResponseStreamChunk(source_id=model.id, channel="thinking", text=thinking))

                text = raw.get("response")
                if isinstance(text, str) and text:
                    if first_text_at is None:
                        first_text_at = time.perf_counter()
                    text_parts.append(text)
                    sink(ResponseStreamChunk(source_id=model.id, channel="text", text=text))

        total_ms = (time.perf_counter() - started) * 1000.0
        ttft_ms = None if first_text_at is None else (first_text_at - started) * 1000.0
        thinking_ttft_ms = None if first_thinking_at is None else (first_thinking_at - started) * 1000.0
        final = dict(final)
        final["lmts_stream_chunks"] = raw_chunks
        final["lmts_thinking_ttft_ms"] = thinking_ttft_ms
        normalized = self._normalized_response(final, "".join(text_parts), total_ms, ttft_ms)
        sink(
            ResponseStreamChunk(
                source_id=model.id,
                channel="meta",
                data={
                    "finish_reason": normalized.finish_reason,
                    "input_tokens": normalized.usage.input_tokens,
                    "output_tokens": normalized.usage.output_tokens,
                    "thinking_ttft_ms": thinking_ttft_ms,
                    "ttft_ms": normalized.timing.ttft_ms,
                    "total_ms": normalized.timing.total_ms,
                    "load_ms": normalized.timing.load_ms,
                    "prompt_eval_ms": normalized.timing.prompt_eval_ms,
                    "generation_ms": normalized.timing.generation_ms,
                    "prompt_tokens_per_second": normalized.performance.prompt_tokens_per_second,
                    "generation_tokens_per_second": normalized.performance.generation_tokens_per_second,
                },
            )
        )
        return normalized
