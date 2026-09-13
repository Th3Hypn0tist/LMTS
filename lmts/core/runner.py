from __future__ import annotations

import traceback
import uuid
from collections.abc import Callable
from pathlib import Path

from lmts.lib.workspace import Workspace
from lmts.tests.base import TestContext, TestModule, test_ref
from lmts.tools.profile import DEFAULT_PROFILE_PATH, load_system_profile

from .control import RunCancelled, RunControl
from .executor import ModelExecutor, TestExecutor
from .models import ModelDescriptor, ResponseStreamChunk
from .registry import ProviderRegistry
from .run import RunResult, utc_now
from .store import RunStore
from .subject import EvaluationSubject


def _default_system_context() -> dict[str, object]:
    payload = load_system_profile(DEFAULT_PROFILE_PATH)
    if payload is None:
        raise ValueError("valid canonical system profile required before testing")
    return payload


class TestRunner:
    __test__ = False

    def __init__(
        self,
        providers: ProviderRegistry,
        store: RunStore,
        *,
        system_context_loader: Callable[[], dict[str, object]] = _default_system_context,
        response_sink: Callable[[ResponseStreamChunk], None] | None = None,
    ) -> None:
        self.providers = providers
        self.store = store
        self.system_context_loader = system_context_loader
        self.response_sink = response_sink

    def run(
        self,
        test: TestModule,
        model: ModelDescriptor,
        workspace_root: Path,
        *,
        control: RunControl | None = None,
        subject: EvaluationSubject | None = None,
    ) -> tuple[RunResult, Path]:
        provider = self.providers.provider(model.provider_ref)
        executor = ModelExecutor(provider, model)
        if subject is not None and subject.kind != "model":
            raise ValueError("non-model subject requires run_executor with a bot/composition executor")
        return self.run_executor(
            test,
            executor,
            workspace_root,
            control=control,
            subject=subject,
        )

    def run_executor(
        self,
        test: TestModule,
        executor: TestExecutor,
        workspace_root: Path,
        *,
        control: RunControl | None = None,
        subject: EvaluationSubject | None = None,
    ) -> tuple[RunResult, Path]:
        evaluation_subject = subject or executor.subject
        if evaluation_subject.kind != executor.kind:
            raise ValueError("evaluation subject kind must match executor kind")

        system_context = self.system_context_loader()
        run_id = uuid.uuid4().hex
        started_at = utc_now()
        workspace = Workspace(workspace_root / run_id)
        context = TestContext(
            executor=executor,
            workspace=workspace,
            control=control,
            response_sink=self.response_sink,
        )
        resolved_test_ref = test_ref(test)
        execution_metadata = dict(executor.metadata)

        common: dict[str, object] = {
            "run_id": run_id,
            "test_ref": resolved_test_ref,
            "executor_id": executor.id,
            "executor_kind": executor.kind,
            "started_at": started_at,
            "evaluation_subject": evaluation_subject.to_dict(),
            "execution_metadata": execution_metadata,
            "system_context": system_context,
        }
        if executor.kind == "model":
            common.update(
                {
                    "model_id": executor.id,
                    "model_ref": execution_metadata.get("model_ref"),
                    "provider_ref": execution_metadata.get("provider_ref"),
                    "model_metadata": execution_metadata.get("model_metadata") or {},
                }
            )

        try:
            context.checkpoint()
            result = test.run(context)
            context.checkpoint()
            run = RunResult(
                **common,
                completed_at=utc_now(),
                status="completed",
                passed=result.passed,
                score=None if result.score is None else result.score.to_dict(),
                metrics=result.metrics,
                artifacts=result.artifacts,
                responses=list(context.responses),
                workspace_trace=list(workspace.trace.operations),
            )
        except RunCancelled:
            run = RunResult(
                **common,
                completed_at=utc_now(),
                status="cancelled",
                passed=None,
                responses=list(context.responses),
                workspace_trace=list(workspace.trace.operations),
            )
        except Exception as exc:
            run = RunResult(
                **common,
                completed_at=utc_now(),
                status="failed",
                passed=False,
                responses=list(context.responses),
                workspace_trace=list(workspace.trace.operations),
                error={
                    "type": type(exc).__name__,
                    "message": str(exc),
                    "traceback": traceback.format_exc(),
                },
            )

        path = self.store.append(run)
        return run, path
