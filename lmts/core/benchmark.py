from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class BenchmarkDefinition:
    id: str
    version: str
    test_ref: str
    research_domain: str
    description: str = ""
    metric_refs: tuple[str, ...] = field(default_factory=tuple)

    @property
    def ref(self) -> str:
        return f"{self.id}@{self.version}"


class BenchmarkRegistry:
    def __init__(self, definitions: Iterable[BenchmarkDefinition] = ()) -> None:
        self._definitions: dict[str, BenchmarkDefinition] = {}
        for definition in definitions:
            self.register(definition)

    def register(self, definition: BenchmarkDefinition) -> None:
        if definition.ref in self._definitions:
            raise ValueError(f"benchmark already registered: {definition.ref}")
        self._definitions[definition.ref] = definition

    def get(self, ref: str) -> BenchmarkDefinition:
        try:
            return self._definitions[ref]
        except KeyError as exc:
            raise KeyError(f"unknown benchmark: {ref}") from exc

    def definitions(self) -> tuple[BenchmarkDefinition, ...]:
        return tuple(self._definitions[key] for key in sorted(self._definitions))
