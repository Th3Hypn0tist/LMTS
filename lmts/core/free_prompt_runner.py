from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from lmts.tests.modules.free_prompt import FreePromptTest

from .control import RunControl
from .models import ModelDescriptor
from .runner import TestRunner


@dataclass(frozen=True, slots=True)
class FreePromptProgress:
    completed: int
    total: int
    model_id: str
    trial: int
    repeats: int
    status: str


@dataclass(slots=True)
class ModelConsistency:
    model_id: str
    trials: int = 0
    unique_exact_outputs: int = 0
    largest_exact_group: int = 0
    exact_consistency: float = 0.0


@dataclass(slots=True)
class FreePromptSummary:
    prompt_sha256: str
    repeats: int
    model_ids: list[str] = field(default_factory=list)
    run_ids: list[str] = field(default_factory=list)
    completed: int = 0
    errors: int = 0
    cancelled: int = 0
    unique_outputs: int = 0
    models: list[ModelConsistency] = field(default_factory=list)


ProgressCallback = Callable[[FreePromptProgress], None]


def _consistency(model_id: str, outputs: list[str]) -> ModelConsistency:
    counts: dict[str, int] = defaultdict(int)
    for output in outputs:
        counts[output] += 1
    largest = max(counts.values(), default=0)
    trials = len(outputs)
    return ModelConsistency(
        model_id=model_id,
        trials=trials,
        unique_exact_outputs=len(counts),
        largest_exact_group=largest,
        exact_consistency=(largest / trials) if trials else 0.0,
    )


class FreePromptRunner:
    def __init__(self, runner: TestRunner) -> None:
        self.runner = runner

    def run(
        self,
        prompt: str,
        models: list[ModelDescriptor],
        repeats: int,
        workspace_root: Path,
        *,
        control: RunControl | None = None,
        progress: ProgressCallback | None = None,
    ) -> FreePromptSummary:
        if not prompt:
            raise ValueError("free prompt must not be empty")
        if repeats < 1:
            raise ValueError("repeats must be positive")

        import hashlib

        total = len(models) * repeats
        completed = 0
        errors = 0
        cancelled = 0
        run_ids: list[str] = []
        outputs_by_model: dict[str, list[str]] = {model.id: [] for model in models}
        all_outputs: list[str] = []

        for model in models:
            for trial in range(1, repeats + 1):
                if control is not None and control.cancelled:
                    break
                test = FreePromptTest(prompt=prompt, trial=trial)
                run, _ = self.runner.run(
                    test,
                    model,
                    workspace_root / "free-prompt",
                    control=control,
                )
                run_ids.append(run.run_id)
                completed += 1
                if run.status == "cancelled":
                    cancelled += 1
                elif run.status != "completed":
                    errors += 1
                else:
                    output = str(run.artifacts.get("response_text", ""))
                    outputs_by_model[model.id].append(output)
                    all_outputs.append(output)
                if progress is not None:
                    progress(
                        FreePromptProgress(
                            completed=completed,
                            total=total,
                            model_id=model.id,
                            trial=trial,
                            repeats=repeats,
                            status=run.status,
                        )
                    )
            if control is not None and control.cancelled:
                break

        return FreePromptSummary(
            prompt_sha256=hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            repeats=repeats,
            model_ids=[model.id for model in models],
            run_ids=run_ids,
            completed=completed,
            errors=errors,
            cancelled=cancelled,
            unique_outputs=len(set(all_outputs)),
            models=[_consistency(model.id, outputs_by_model[model.id]) for model in models],
        )
