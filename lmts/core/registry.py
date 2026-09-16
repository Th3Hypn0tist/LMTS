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
        if not provider.id or provider.id != provider.id.strip():
            raise ValueError("provider id must be a non-empty canonical string")
        if ":" in provider.id:
            raise ValueError("provider id must not contain ':'")
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
        seen_ids: set[str] = set()
        for provider_id in sorted(self._providers):
            provider_models = self._providers[provider_id].discover_models()
            for model in provider_models:
                if model.provider_ref != provider_id:
                    raise ValueError(
                        f"provider {provider_id} returned model owned by {model.provider_ref}: {model.id}"
                    )
                if model.id in seen_ids:
                    raise ValueError(f"duplicate canonical model id discovered: {model.id}")
                seen_ids.add(model.id)
                models.append(model)
        return sorted(models, key=lambda item: (item.provider_ref, item.model_ref))
