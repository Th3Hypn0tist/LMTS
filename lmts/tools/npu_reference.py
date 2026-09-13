from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class NPUUnavailable(RuntimeError):
    pass


class NPUReferenceAdapter(Protocol):
    id: str

    def available(self) -> bool: ...

    def benchmark(self) -> tuple[list[dict[str, Any]], dict[str, Any]]: ...


@dataclass(slots=True)
class NPUReferenceRegistry:
    adapters: tuple[NPUReferenceAdapter, ...] = ()

    def available_adapters(self) -> tuple[NPUReferenceAdapter, ...]:
        return tuple(adapter for adapter in self.adapters if adapter.available())

    def benchmark(self) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        available = self.available_adapters()
        if not available:
            raise NPUUnavailable("no supported NPU reference backend is available")
        tests: list[dict[str, Any]] = []
        backends: list[str] = []
        for adapter in available:
            adapter_tests, environment = adapter.benchmark()
            tests.extend(adapter_tests)
            backends.append(adapter.id)
            if environment:
                for test in adapter_tests:
                    test.setdefault("environment", environment)
        return tests, {"backends": backends}


DEFAULT_NPU_REFERENCE_REGISTRY = NPUReferenceRegistry()
