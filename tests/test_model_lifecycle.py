from __future__ import annotations

import pytest

from lmts.core.executor import ModelExecutor, WARMUP_EXPECTED, WARMUP_PROMPT
from lmts.core.models import ModelDescriptor, NormalizedResponse


class FakeProvider:
    id = 'fake'

    def __init__(self, *, warmup_text: str = 'OK', stays_loaded: bool = False) -> None:
        self.warmup_text = warmup_text
        self.loaded = False
        self.stays_loaded = stays_loaded
        self.prompts: list[str] = []

    def discover_models(self):
        return []

    def generate(self, model, prompt):
        self.prompts.append(prompt)
        self.loaded = True
        return NormalizedResponse(text=self.warmup_text)

    def is_loaded(self, model):
        return self.loaded

    def unload(self, model):
        if not self.stays_loaded:
            self.loaded = False


def _executor(provider: FakeProvider) -> ModelExecutor:
    return ModelExecutor(
        provider,
        ModelDescriptor(
            id='fake:test',
            provider_ref='fake',
            model_ref='test',
            location='local',
        ),
    )


def test_model_warmup_is_exact_unmeasured_readiness_prompt() -> None:
    provider = FakeProvider(warmup_text=WARMUP_EXPECTED)
    executor = _executor(provider)

    response = executor.warm_up()

    assert response.text == 'OK'
    assert provider.prompts == [WARMUP_PROMPT]
    assert executor.is_loaded() is True


def test_model_warmup_rejects_nonexact_response() -> None:
    executor = _executor(FakeProvider(warmup_text='OK.'))

    with pytest.raises(RuntimeError, match='warm-up readiness check failed'):
        executor.warm_up()


def test_model_unload_requires_verified_unloaded_state() -> None:
    provider = FakeProvider()
    executor = _executor(provider)
    executor.warm_up()

    executor.unload()

    assert executor.is_loaded() is False


def test_model_unload_fails_if_provider_reports_still_loaded() -> None:
    provider = FakeProvider(stays_loaded=True)
    executor = _executor(provider)
    executor.warm_up()

    with pytest.raises(RuntimeError, match='still loaded after unload'):
        executor.unload()
