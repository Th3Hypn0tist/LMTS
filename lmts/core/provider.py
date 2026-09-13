from __future__ import annotations

from typing import Protocol

from .models import ModelDescriptor, NormalizedResponse


class ModelProvider(Protocol):
    @property
    def id(self) -> str: ...

    def discover_models(self) -> list[ModelDescriptor]: ...

    def generate(self, model: ModelDescriptor, prompt: str) -> NormalizedResponse: ...
