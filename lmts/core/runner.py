from __future__ import annotations

import traceback
import uuid
from pathlib import Path
from typing import Callable

from lmts.lib.workspace import Workspace
from lmts.tests.base import TestContext, TestModule
from lmts.tools.profile import SystemProfile, scan_system_profile

from .models import ModelDescriptor
from .registry import ProviderRegistry
from .run import RunResult, utc_now
from .store import RunStore


class TestRunner:
    __test__ = False

    def __init__(
        self,
        providers: ProviderRegistry,
        store: RunStore,
        *,
        profile_scan: Callable[[], SystemProfile] = scan_system_profile,
    ) -> None:
        self.providers = providers
        self.store = store
        self.profile_scan = profile_scan

    def run(
        self,
        test: TestModule,
        model: ModelDescriptor,
        workspace_root: Path,
    ) -> tuple[RunResult, Path]:
        provider = self.providers.provider(model.provider_ref)
        run_id = uuid.uuid4().hex
        started_at = utc_now()
        workspace = Workspace(workspace_root / run_id)
        context = TestContext(provider=provider, model=model, workspace=workspace)
        test_ref = f"{test.id}@{test.version}"

        try:
            result = test.run(context)
            run = RunResult(
                run_id=run_id,
                test_ref=test_ref,
                model_id=model.id,
                model_ref=model.model_ref,
                provider_ref=model.provider_ref,
                started_at=started_at,
                completed_at=utc_now(),
                status="completed",
                passed=result.passed,
                metrics=result.metrics,
                artifacts=result.artifacts,
                responses=list(context.responses),
                workspace_trace=list(workspace.trace.operations),
                system_profile=self.profile_scan().to_dict(),
                model_metadata=dict(model.metadata),
            )
        except Exception as exc:
            run = RunResult(
                run_id=run_id,
                test_ref=test_ref,
                model_id=model.id,
                model_ref=model.model_ref,
                provider_ref=model.provider_ref,
                started_at=started_at,
                completed_at=utc_now(),
                status="failed",
                passed=False,
                responses=list(context.responses),
                workspace_trace=list(workspace.trace.operations),
                system_profile=self.profile_scan().to_dict(),
                model_metadata=dict(model.metadata),
                error={
                    "type": type(exc).__name__,
                    "message": str(exc),
                    "traceback": traceback.format_exc(),
                },
            )

        path = self.store.append(run)
        return run, path
