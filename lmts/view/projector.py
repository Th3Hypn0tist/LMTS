from __future__ import annotations

from dataclasses import dataclass, field

from lmts.core.models import ModelDescriptor
from lmts.lib.view import ViewFrame, ViewItem
from lmts.tests.base import TestModule, test_ref


@dataclass(slots=True)
class LMTSViewState:
    models: list[ModelDescriptor] = field(default_factory=list)
    tests: list[TestModule] = field(default_factory=list)
    selected_model_ids: set[str] = field(default_factory=set)
    selected_test_refs: set[str] = field(default_factory=set)
    message: str = ""
    last_result: dict[str, object] | None = None

    profile_required: bool = False
    profiled_at: str = ""
    running: bool = False
    cancel_requested: bool = False
    progress_completed: int = 0
    progress_total: int = 0
    progress_passed: int = 0
    progress_failed: int = 0
    progress_errors: int = 0
    progress_cancelled: int = 0
    progress_model_id: str = ""
    progress_test_ref: str = ""
    progress_phase: str = "idle"

    @property
    def selected_models(self) -> list[ModelDescriptor]:
        return [model for model in self.models if model.id in self.selected_model_ids]

    @property
    def selected_tests(self) -> list[TestModule]:
        return [test for test in self.tests if test_ref(test) in self.selected_test_refs]

    @property
    def models_are_all(self) -> bool:
        return bool(self.models) and len(self.selected_models) == len(self.models)

    @property
    def tests_are_all(self) -> bool:
        return bool(self.tests) and len(self.selected_tests) == len(self.tests)

    def progress_lines(self) -> tuple[str, ...]:
        if not self.running and self.progress_phase == "idle":
            return ()
        current = (
            f"{self.progress_model_id} x {self.progress_test_ref}"
            if self.progress_model_id or self.progress_test_ref
            else "-"
        )
        state = "CANCEL REQUESTED" if self.cancel_requested and self.running else (
            "RUNNING" if self.running else self.progress_phase.upper()
        )
        return (
            f"state    : {state}",
            f"progress : {self.progress_completed} / {self.progress_total}",
            f"current  : {current}",
            f"passed   : {self.progress_passed}",
            f"failed   : {self.progress_failed}",
            f"errors   : {self.progress_errors}",
            f"cancelled: {self.progress_cancelled}",
        )


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
            test_text = f"all configured ({len(selected_tests)})"
        elif len(selected_tests) == 1:
            test_text = test_ref(selected_tests[0])
        else:
            test_text = f"{len(selected_tests)} configured selected"

        run_count = len(selected_models) * len(selected_tests)
        profile_text = "REQUIRED" if self.state.profile_required else "ready"
        status = (
            f"profile={profile_text}  models={len(selected_models)}/{len(self.state.models)}  "
            f"tests={len(selected_tests)}/{len(self.state.tests)}  runs={run_count}"
        )
        if self.state.running:
            status += f"  RUNNING {self.state.progress_completed}/{self.state.progress_total}"

        lines = [
            "LMTS model laboratory",
            "",
            f"Profile: {profile_text}",
            f"Models : {model_text}",
            f"Tests  : {test_text}",
            f"Matrix : {len(selected_models)} x {len(selected_tests)} = {run_count} run(s)",
        ]

        if self.state.progress_lines():
            lines.extend(["", "Test progress", *self.state.progress_lines()])

        if selected_models:
            lines.extend(["", "Selected models"])
            for model in selected_models:
                lines.append(f"  {model.id}")

        if self.state.tests:
            lines.extend(["", "Configured test matrix"])
            for test in self.state.tests:
                marker = "x" if test_ref(test) in self.state.selected_test_refs else " "
                title = getattr(test, "title", test.id)
                params = getattr(test, "params", {})
                suffix = f"  params={params}" if params else ""
                lines.append(f"  [{marker}] {test_ref(test)}  {title}{suffix}")

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
                ViewItem("profile", "Profile", profile_text),
                ViewItem("models", "Models", model_text),
                ViewItem("tests", "Configured tests", test_text),
                ViewItem("runs", "Runs", str(run_count)),
                ViewItem("running", "Running", str(self.state.running).lower()),
                ViewItem(
                    "progress",
                    "Progress",
                    f"{self.state.progress_completed}/{self.state.progress_total}",
                ),
            ),
        )
