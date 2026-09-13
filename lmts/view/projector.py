from __future__ import annotations

from dataclasses import dataclass, field

from lmts.core.models import ModelDescriptor
from lmts.lib.view import ViewFrame, ViewItem
from lmts.tests.base import TestModule


def _test_ref(test: TestModule) -> str:
    return f"{test.id}@{test.version}"


@dataclass(slots=True)
class LMTSViewState:
    models: list[ModelDescriptor] = field(default_factory=list)
    tests: list[TestModule] = field(default_factory=list)
    selected_model_ids: set[str] = field(default_factory=set)
    selected_test_refs: set[str] = field(default_factory=set)
    message: str = ""
    last_result: dict[str, object] | None = None

    @property
    def selected_models(self) -> list[ModelDescriptor]:
        return [model for model in self.models if model.id in self.selected_model_ids]

    @property
    def selected_tests(self) -> list[TestModule]:
        return [test for test in self.tests if _test_ref(test) in self.selected_test_refs]

    @property
    def model(self) -> ModelDescriptor | None:
        selected = self.selected_models
        return selected[0] if len(selected) == 1 else None

    @property
    def test(self) -> TestModule | None:
        selected = self.selected_tests
        return selected[0] if len(selected) == 1 else None

    @property
    def models_are_all(self) -> bool:
        return bool(self.models) and len(self.selected_models) == len(self.models)

    @property
    def tests_are_all(self) -> bool:
        return bool(self.tests) and len(self.selected_tests) == len(self.tests)


class LMTSViewProjector:
    def __init__(self, state: LMTSViewState) -> None:
        self.state = state

    def project(self) -> ViewFrame:
        selected_models = self.state.selected_models
        selected_tests = self.state.selected_tests

        if not selected_models:
            model_text = "<none>"
        elif self.state.models_are_all:
            model_text = f"all ({len(selected_models)})"
        elif len(selected_models) == 1:
            model_text = selected_models[0].id
        else:
            model_text = f"{len(selected_models)} selected"

        if not selected_tests:
            test_text = "<none>"
        elif self.state.tests_are_all:
            test_text = f"all ({len(selected_tests)})"
        elif len(selected_tests) == 1:
            test_text = _test_ref(selected_tests[0])
        else:
            test_text = f"{len(selected_tests)} selected"

        run_count = len(selected_models) * len(selected_tests)
        status = (
            f"models={len(selected_models)}/{len(self.state.models)}  "
            f"tests={len(selected_tests)}/{len(self.state.tests)}  "
            f"runs={run_count}"
        )
        lines = [
            "LMTS model laboratory",
            "",
            f"Models : {model_text}",
            f"Tests  : {test_text}",
            f"Matrix : {len(selected_models)} x {len(selected_tests)} = {run_count} run(s)",
        ]

        if selected_models:
            lines.extend(["", "Selected models"])
            for model in selected_models:
                lines.append(f"  {model.id}")

        if selected_tests:
            lines.extend(["", "Selected tests"])
            for test in selected_tests:
                lines.append(f"  {_test_ref(test)}")

        if len(selected_models) == 1:
            model = selected_models[0]
            details = model.metadata.get("details") if isinstance(model.metadata, dict) else None
            if isinstance(details, dict):
                lines.extend([
                    "",
                    f"Family       : {details.get('family') or '-'}",
                    f"Parameters   : {details.get('parameter_size') or '-'}",
                    f"Quantization : {details.get('quantization_level') or '-'}",
                    f"Context      : {details.get('context_length') or '-'}",
                ])

        if self.state.last_result:
            lines.extend(["", "Last result"])
            for key, value in self.state.last_result.items():
                lines.append(f"  {key}: {value}")
        if self.state.message:
            lines.extend(["", self.state.message])

        return ViewFrame(
            title="LMTS",
            status=status,
            lines=tuple(lines),
            items=(
                ViewItem("models", "Models", model_text),
                ViewItem("tests", "Tests", test_text),
                ViewItem("runs", "Runs", str(run_count)),
            ),
        )
