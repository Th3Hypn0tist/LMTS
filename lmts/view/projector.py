from __future__ import annotations

from dataclasses import dataclass, field

from lmts.core.executor import TestExecutor
from lmts.lib.view import ViewFrame, ViewItem
from lmts.tests.base import TestModule, test_ref

from .live_matrix import LiveResultsMatrixView


@dataclass(slots=True)
class LMTSViewState:
    targets: list[TestExecutor] = field(default_factory=list)
    tests: list[TestModule] = field(default_factory=list)
    selected_target_ids: set[str] = field(default_factory=set)
    selected_test_refs: set[str] = field(default_factory=set)
    suite_level: str = "moderate"
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
    progress_target_id: str = ""
    progress_test_ref: str = ""
    progress_phase: str = "idle"

    live_target_ids: tuple[str, ...] = ()
    live_target_kinds: dict[str, str] = field(default_factory=dict)
    live_test_refs: tuple[str, ...] = ()
    live_cells: dict[tuple[str, str], str] = field(default_factory=dict)

    @property
    def selected_targets(self) -> list[TestExecutor]:
        return [target for target in self.targets if target.id in self.selected_target_ids]

    @property
    def selected_tests(self) -> list[TestModule]:
        return [test for test in self.tests if test_ref(test) in self.selected_test_refs]

    @property
    def targets_are_all(self) -> bool:
        return bool(self.targets) and len(self.selected_targets) == len(self.targets)

    @property
    def tests_are_all(self) -> bool:
        return bool(self.tests) and len(self.selected_tests) == len(self.tests)

    def progress_lines(self) -> tuple[str, ...]:
        if not self.running and self.progress_phase == "idle":
            return ()
        current = (
            f"{self.progress_target_id} x {self.progress_test_ref}"
            if self.progress_target_id or self.progress_test_ref
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

    def live_matrix_lines(self) -> tuple[str, ...]:
        if not self.live_target_ids or not self.live_test_refs:
            return ()
        return LiveResultsMatrixView(
            target_ids=self.live_target_ids,
            target_kinds=self.live_target_kinds,
            test_refs=self.live_test_refs,
            cells=self.live_cells,
            current_test_ref=self.progress_test_ref,
        ).lines()


class LMTSViewProjector:
    def __init__(self, state: LMTSViewState) -> None:
        self.state = state

    def project(self) -> ViewFrame:
        selected_targets = self.state.selected_targets
        selected_tests = self.state.selected_tests

        if not selected_targets:
            target_text = "<none>"
        elif self.state.targets_are_all:
            target_text = f"all ({len(selected_targets)})"
        elif len(selected_targets) == 1:
            target_text = f"{selected_targets[0].kind}:{selected_targets[0].id}"
        else:
            target_text = f"{len(selected_targets)} selected"

        if not selected_tests:
            test_text = "<none>"
        elif self.state.tests_are_all:
            test_text = f"all configured ({len(selected_tests)})"
        elif len(selected_tests) == 1:
            test_text = test_ref(selected_tests[0])
        else:
            test_text = f"{len(selected_tests)} configured selected"

        run_count = len(selected_targets) * len(selected_tests)
        profile_text = "REQUIRED" if self.state.profile_required else "ready"
        status = (
            f"profile={profile_text}  suite={self.state.suite_level.upper()}  "
            f"targets={len(selected_targets)}/{len(self.state.targets)}  "
            f"tests={len(selected_tests)}/{len(self.state.tests)}  runs={run_count}"
        )
        if self.state.running:
            status += f"  RUNNING {self.state.progress_completed}/{self.state.progress_total}"

        lines = [
            "LMTS evaluation laboratory",
            "",
            f"Profile: {profile_text}",
            f"Suite  : {self.state.suite_level.upper()} cumulative",
            f"Targets: {target_text}",
            f"Tests  : {test_text}",
            f"Matrix : {len(selected_targets)} x {len(selected_tests)} = {run_count} run(s)",
        ]

        if self.state.progress_lines():
            lines.extend(["", "Test progress", *self.state.progress_lines()])

        if selected_targets:
            lines.extend(["", "Selected targets"])
            for target in selected_targets:
                lines.append(f"  {target.kind.upper():11} {target.id}")

        live_matrix = self.state.live_matrix_lines()
        if live_matrix:
            lines.extend(["", *live_matrix])
        elif self.state.tests:
            lines.extend(["", "Configured test matrix"])
            level_marker = {"quick": "Q", "moderate": "M", "deep": "D"}
            for test in self.state.tests:
                marker = "x" if test_ref(test) in self.state.selected_test_refs else " "
                minimum_level = getattr(test, "minimum_level", None)
                if minimum_level not in level_marker:
                    raise ValueError(f"configured test missing canonical minimum_level: {test_ref(test)}")
                tier = level_marker[minimum_level]
                title = getattr(test, "title", test.id)
                params = getattr(test, "params", {})
                suffix = f"  params={params}" if params else ""
                mandatory = " !" if bool(getattr(test, "mandatory", False)) else ""
                lines.append(f"  [{marker}] [{tier}]{mandatory} {test_ref(test)}  {title}{suffix}")

        if len(selected_targets) == 1:
            target = selected_targets[0]
            metadata = target.metadata
            if target.kind == "model":
                model_metadata = metadata.get("model_metadata") if isinstance(metadata.get("model_metadata"), dict) else {}
                details = model_metadata.get("details") if isinstance(model_metadata.get("details"), dict) else None
                if isinstance(details, dict):
                    lines.extend([
                        "",
                        f"Family       : {details.get('family') or '-'}",
                        f"Parameters   : {details.get('parameter_size') or '-'}",
                        f"Quantization : {details.get('quantization_level') or '-'}",
                        f"Context      : {details.get('context_length') or '-'}",
                    ])
            else:
                lines.extend([
                    "",
                    f"Target kind  : {target.kind}",
                    f"Executor     : {target.id}",
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
                ViewItem("suite", "Suite", self.state.suite_level),
                ViewItem("targets", "Targets", target_text),
                ViewItem("tests", "Configured tests", test_text),
                ViewItem("runs", "Runs", str(run_count)),
                ViewItem("running", "Running", str(self.state.running).lower()),
                ViewItem("progress", "Progress", f"{self.state.progress_completed}/{self.state.progress_total}"),
            ),
        )
