from lmts.core.models import ModelDescriptor
from lmts.core.registry import ProviderRegistry


class FakeProvider:
    id = "fake"

    def discover_models(self):
        return [ModelDescriptor(id="fake:m", provider_ref="fake", model_ref="m", location="local")]

    def generate(self, model, prompt):
        raise NotImplementedError


def test_registry_discovers_models() -> None:
    registry = ProviderRegistry([FakeProvider()])
    models = registry.discover_models()
    assert [model.id for model in models] == ["fake:m"]
