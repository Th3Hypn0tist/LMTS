from __future__ import annotations

from collections.abc import Iterable

from .models import ModelDescriptor
from .provider import ModelProvider


class ProviderRegistry:
    def __init__(self, providers: Iterable[ModelProvider] = ()) -> None:
        self._providers: dict[str, ModelProvider] = {}
        for provider in providers:
            self.register(provider)

    def register(self, provider: ModelProvider) -> None:
        if provider.id in self._providers:
            raise ValueError(f"provider already registered: {provider.id}")
        self._providers[provider.id] = provider

    def provider(self, provider_id: str) -> ModelProvider:
        try:
            return self._providers[provider_id]
        except KeyError as exc:
            raise KeyError(f"unknown provider: {provider_id}") from exc

    def discover_models(self) -> list[ModelDescriptor]:
        models: list[ModelDescriptor] = []
        for provider_id in sorted(self._providers):
            models.extend(self._providers[provider_id].discover_models())
        return sorted(models, key=lambda item: (item.provider_ref, item.model_ref))
