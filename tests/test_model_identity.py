from __future__ import annotations

import pytest

from lmts.core.models import ModelDescriptor, canonical_model_id
from lmts.core.registry import ProviderRegistry
from lmts.providers.ollama import OllamaProvider


class StaticProvider:
    def __init__(self, provider_id: str, models: list[ModelDescriptor]) -> None:
        self._id = provider_id
        self._models = models

    @property
    def id(self) -> str:
        return self._id

    def discover_models(self) -> list[ModelDescriptor]:
        return list(self._models)

    def generate(self, model, prompt):  # pragma: no cover - discovery-only test provider
        raise NotImplementedError


def descriptor(provider: str, model: str) -> ModelDescriptor:
    return ModelDescriptor(
        id=canonical_model_id(provider, model),
        provider_ref=provider,
        model_ref=model,
        location="local",
    )


def test_canonical_model_id_preserves_provider_native_model_ref() -> None:
    assert canonical_model_id("ollama-local", "llama3.2:3b") == "ollama-local:llama3.2:3b"


def test_model_descriptor_rejects_unqualified_or_mismatched_id() -> None:
    with pytest.raises(ValueError, match="canonical provider-qualified identity"):
        ModelDescriptor(
            id="llama3.2:3b",
            provider_ref="ollama-local",
            model_ref="llama3.2:3b",
            location="local",
        )


def test_provider_ref_cannot_make_identity_boundary_ambiguous() -> None:
    with pytest.raises(ValueError, match="must not contain ':'"):
        canonical_model_id("ollama:local", "llama3.2:3b")


def test_registry_rejects_provider_returning_foreign_model_identity() -> None:
    foreign = descriptor("provider-b", "same-name")
    registry = ProviderRegistry([StaticProvider("provider-a", [foreign])])
    with pytest.raises(ValueError, match="returned model owned by provider-b"):
        registry.discover_models()


def test_same_native_model_name_is_distinct_across_providers() -> None:
    registry = ProviderRegistry(
        [
            StaticProvider("provider-a", [descriptor("provider-a", "same-name")]),
            StaticProvider("provider-b", [descriptor("provider-b", "same-name")]),
        ]
    )
    assert [model.id for model in registry.discover_models()] == [
        "provider-a:same-name",
        "provider-b:same-name",
    ]


def test_ollama_discovery_uses_canonical_identity() -> None:
    provider = OllamaProvider(provider_id="ollama-local")
    provider._json = lambda *args, **kwargs: {  # type: ignore[method-assign]
        "models": [{"name": "llama3.2:3b", "size": 123, "digest": "abc"}]
    }
    models = provider.discover_models()
    assert len(models) == 1
    assert models[0].id == "ollama-local:llama3.2:3b"
    assert models[0].provider_ref == "ollama-local"
    assert models[0].model_ref == "llama3.2:3b"
