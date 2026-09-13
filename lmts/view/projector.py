from __future__ import annotations

from dataclasses import dataclass, field

from lmts.core.models import ModelDescriptor
from lmts.tests.base import TestModule

from .model import ViewFrame, ViewItem


@dataclass(slots=True)
class LMTSViewState:
    models: list[ModelDescriptor] = field(default_factory=list)
    tests: list[TestModule] = field(default_factory=list)
    selected_model: int = 0
    selected_test: int = 0
    message: str = ""
    last_result: dict[str, object] | None = None

    @property
    def model(self) -> ModelDescriptor | None:
        if not self.models:
            return None
        self.selected_model = min(max(0, self.selected_model), len(self.models) - 1)
        return self.models[self.selected_model]

    @property
    def test(self) -> TestModule | None:
        if not self.tests:
            return None
        self.selected_test = min(max(0, self.selected_test), len(self.tests) - 1)
        return self.tests[self.selected_test]


class LMTSViewProjector:
    def __init__(self, state: LMTSViewState) -> None:
        self.state = state

    def project(self) -> ViewFrame:
        model = self.state.model
        test = self.state.test
        model_text = model.id if model else "<none>"
        test_text = f"{test.id}@{test.version}" if test else "<none>"
        status = f"model={model_text}  test={test_text}"
        lines = [
            "LMTS model laboratory",
            "",
            f"Model : {model_text}",
            f"Test  : {test_text}",
            f"Models: {len(self.state.models)}",
            f"Tests : {len(self.state.tests)}",
        ]
        if model is not None:
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
                ViewItem("model", "Model", model_text),
                ViewItem("test", "Test", test_text),
            ),
        )
