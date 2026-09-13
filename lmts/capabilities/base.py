from __future__ import annotations

from typing import Protocol

from lmts.tests.base import TestModule


class CapabilityScenario(Protocol):
    id: str
    version: str
    axis: str
    unit: str
    default_low: float
    default_high: float
    default_tolerance: float

    @property
    def ref(self) -> str: ...

    def build_test(self, complexity: float) -> TestModule: ...
