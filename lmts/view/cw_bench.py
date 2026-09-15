from __future__ import annotations

from pathlib import Path

from lmts.core.cw_bench import CICAdapter, CWSource
from lmts.tests.modules.cw_deep import CWDeepTest


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

    test = CWDeepTest(
        source=source,
        output_language=output_language,
        cic_root=cic_root,
    )
    started = controller._start_run(targets, [test])
    if started:
        controller.state.message = (
            f"CW Bench started: {source.ref} / {output_language} / {len(targets)} model(s)"
        )
    return started
