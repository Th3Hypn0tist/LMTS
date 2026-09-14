from __future__ import annotations

import threading
from pathlib import Path

from lmts.core.control import RunControl
from lmts.core.cw_bench import CICAdapter, CWSource
from lmts.tests.modules.cw_challenge import CWChallengeTest


def available_cw_languages(cic_root: Path) -> tuple[str, ...]:
    return CICAdapter(cic_root).identity().output_languages


def start_cw_bench(
    controller,
    *,
    source: CWSource,
    output_language: str,
    target_ids: set[str],
    cic_root: Path,
) -> bool:
    if controller.state.running:
        controller.state.message = "test matrix already running"
        return False
    if controller.state.profile_required:
        controller.state.message = "system profile required before testing"
        return False

    targets = [
        target
        for target in controller.state.targets
        if target.kind == "model" and target.id in target_ids
    ]
    if not targets:
        controller.state.message = "select at least one model for CW Bench"
        return False

    test = CWChallengeTest(
        source=source,
        output_language=output_language,
        cic_root=cic_root,
    )
    controller._run_control = RunControl()
    controller.response_monitor.reset()
    controller.state.running = True
    controller.state.cancel_requested = False
    controller.state.progress_completed = 0
    controller.state.progress_total = len(targets)
    controller.state.progress_passed = 0
    controller.state.progress_failed = 0
    controller.state.progress_errors = 0
    controller.state.progress_cancelled = 0
    controller.state.progress_target_id = ""
    controller.state.progress_test_ref = ""
    controller.state.progress_phase = "starting"
    controller.state.last_result = None
    controller.state.message = (
        f"CW Bench started: {source.ref} / {output_language} / {len(targets)} model(s)"
    )
    controller.last_errors = []
    controller._run_thread = threading.Thread(
        target=controller._run_matrix,
        args=(targets, [test], controller._run_control),
        name="lmts-cw-bench",
        daemon=True,
    )
    controller._run_thread.start()
    return True
