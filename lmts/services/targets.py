from __future__ import annotations

from lmts.core.executor import ModelExecutor, TestExecutor
from lmts.core.registry import ProviderRegistry
from lmts.core.runtime_targets import executor_from_definition, load_runtime_targets


class TargetDiscoveryService:
    def __init__(self, providers: ProviderRegistry) -> None:
        self.providers = providers

    def discover(self) -> list[TestExecutor]:
        targets: list[TestExecutor] = []
        for model in self.providers.discover_models():
            targets.append(ModelExecutor(self.providers.provider(model.provider_ref), model))
        for definition in load_runtime_targets():
            targets.append(executor_from_definition(definition))
        ids = [target.id for target in targets]
        if len(ids) != len(set(ids)):
            raise ValueError('evaluation target ids must be unique across models, bots and compositions')
        return sorted(targets, key=lambda item: (item.kind, item.id.casefold()))
