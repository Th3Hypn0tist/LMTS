import pytest
from lmts.core.benchmark import BenchmarkDefinition, BenchmarkRegistry


def test_benchmark_registry_versions_are_explicit():
    one = BenchmarkDefinition("cw.reconstruction", "1.0.0", "cw.reconstruct@1.0.0", "cw")
    two = BenchmarkDefinition("cw.reconstruction", "1.1.0", "cw.reconstruct@1.1.0", "cw")
    registry = BenchmarkRegistry([one, two])
    assert [item.ref for item in registry.definitions()] == ["cw.reconstruction@1.0.0", "cw.reconstruction@1.1.0"]
    with pytest.raises(ValueError):
        registry.register(one)
