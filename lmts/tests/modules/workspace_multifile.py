from __future__ import annotations

from dataclasses import dataclass

from lmts.lib.workspace import WorkspaceProtocolSession
from lmts.tests.base import TestContext, TestRequirements, TestResult


@dataclass(frozen=True, slots=True)
class WorkspaceMultiFileTest:
    id: str = "core.workspace_multifile"
    version: str = "1.0.0"
    requirements: TestRequirements = TestRequirements(
        text_generation=True,
        workspace_read=True,
        workspace_write=True,
        multi_file_output=True,
    )

    def run(self, context: TestContext) -> TestResult:
        context.workspace.stage_input(
            "task.txt",
            "Create exactly two output text files.\n"
            "1. output/alpha.txt must contain exactly ALPHA_OK\\n\n"
            "2. output/nested/beta.txt must contain exactly BETA_OK\\n\n"
            "Read this file before writing the outputs.\n",
        )
        session = WorkspaceProtocolSession(max_steps=24)
        protocol = session.run(
            context,
            "Inspect the input workspace, read the task, complete it exactly, then finish.",
        )
        alpha = context.workspace.output_root / "alpha.txt"
        beta = context.workspace.output_root / "nested" / "beta.txt"
        alpha_text = alpha.read_text(encoding="utf-8") if alpha.is_file() else None
        beta_text = beta.read_text(encoding="utf-8") if beta.is_file() else None
        output_files = [
            str(path.relative_to(context.workspace.output_root))
            for path in sorted(context.workspace.output_root.rglob("*"))
            if path.is_file()
        ]
        passed = (
            protocol.finished
            and alpha_text == "ALPHA_OK\n"
            and beta_text == "BETA_OK\n"
            and output_files == ["alpha.txt", "nested/beta.txt"]
        )
        return TestResult(
            passed=passed,
            metrics={
                "workspace_protocol_steps": protocol.steps,
                "output_file_count": len(output_files),
                "exact_output_match": passed,
            },
            artifacts={
                "output_files": output_files,
                "protocol_summary": protocol.summary,
            },
        )
