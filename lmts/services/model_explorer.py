from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from lmts.core.control import RunControl
from lmts.core.executor import TestExecutor
from lmts.core.model_downloader import DownloadCancelled, ModelDownloadProgress, ModelDownloader
from lmts.core.model_explorer import (
    DEFAULT_EXPLORER_REPEATS,
    DEFAULT_VARIANCE_THRESHOLD,
    FitAssessment,
    ModelCandidate,
    QualificationAggregate,
    assess_candidate_fit,
    qualification_aggregate,
)
from lmts.core.variance_store import VarianceStore
from lmts.tests.base import TestModule

from .evaluation import EvaluationOutcome, EvaluationService, RunCompletedCallback


ProgressSink = Callable[[ModelDownloadProgress], None]
ExecutorResolver = Callable[[ModelCandidate], TestExecutor]


@dataclass(frozen=True, slots=True)
class TestQualification:
    test_ref: str
    aggregate: QualificationAggregate
    accepted: bool


@dataclass(frozen=True, slots=True)
class CandidateQualification:
    candidate: ModelCandidate
    fit: FitAssessment
    accepted: bool
    deleted: bool
    tests: tuple[TestQualification, ...]
    evaluation: EvaluationOutcome | None
    error: str | None = None


class ModelExplorerService:
    """Sequential candidate qualification: fit -> pull -> benchmark -> keep/delete."""

    def __init__(
        self,
        evaluation_service: EvaluationService,
        *,
        results_root: Path,
    ) -> None:
        self.evaluation_service = evaluation_service
        self.variance_store = VarianceStore(results_root)

    def _aggregate_evaluation(
        self,
        outcome: EvaluationOutcome,
        *,
        repeats: int,
        variance_threshold: float,
    ) -> tuple[tuple[TestQualification, ...], bool]:
        qualifications: list[TestQualification] = []
        accepted = True
        for cell in outcome.cells:
            if not isinstance(cell.passed, bool):
                accepted = False
                continue
            extra = self.variance_store.samples_for_run(cell.run_id)
            samples = [cell.passed]
            for sample in extra:
                samples.append(sample['outcome'] == 'pass')
            aggregate = qualification_aggregate(samples)
            cell_accepted = (
                aggregate.sample_count == repeats
                and aggregate.accepts(variance_threshold)
            )
            qualifications.append(TestQualification(
                test_ref=cell.test_ref,
                aggregate=aggregate,
                accepted=cell_accepted,
            ))
            if not cell_accepted:
                accepted = False

        if not outcome.cells or outcome.errors or outcome.cancelled:
            accepted = False
        return tuple(qualifications), accepted

    def qualify_downloaded(
        self,
        candidate: ModelCandidate,
        fit: FitAssessment,
        executor: TestExecutor,
        tests: list[TestModule],
        *,
        repeats: int = DEFAULT_EXPLORER_REPEATS,
        variance_threshold: float = DEFAULT_VARIANCE_THRESHOLD,
        provenance: dict[str, object] | None = None,
        on_run_completed: RunCompletedCallback | None = None,
        control: RunControl | None = None,
    ) -> tuple[EvaluationOutcome, tuple[TestQualification, ...], bool]:
        if isinstance(repeats, bool) or not isinstance(repeats, int) or repeats < 1:
            raise ValueError('Model Explorer repeats must be a positive integer')
        if not tests:
            raise ValueError('Model Explorer requires a qualification suite')
        active_control = control or RunControl()
        outcome = self.evaluation_service.execute(
            [executor],
            tests,
            active_control,
            on_run_completed=on_run_completed,
            provenance=provenance,
            suite_repeats=repeats,
        )
        qualifications, accepted = self._aggregate_evaluation(
            outcome,
            repeats=repeats,
            variance_threshold=variance_threshold,
        )
        expected_tests = len(tests)
        if len(qualifications) != expected_tests:
            accepted = False
        return outcome, qualifications, accepted

    def explore_one(
        self,
        candidate: ModelCandidate,
        downloader: ModelDownloader,
        executor_resolver: ExecutorResolver,
        tests: list[TestModule],
        system_profile: dict[str, object],
        *,
        free_disk_bytes: int | None,
        repeats: int = DEFAULT_EXPLORER_REPEATS,
        variance_threshold: float = DEFAULT_VARIANCE_THRESHOLD,
        provenance: dict[str, object] | None = None,
        on_download_progress: ProgressSink | None = None,
        on_run_completed: RunCompletedCallback | None = None,
        control: RunControl | None = None,
        keep_rejected: bool = False,
    ) -> CandidateQualification:
        fit = assess_candidate_fit(
            candidate,
            system_profile,
            free_disk_bytes=free_disk_bytes,
        )
        if fit.status == 'too_large':
            return CandidateQualification(
                candidate=candidate,
                fit=fit,
                accepted=False,
                deleted=False,
                tests=(),
                evaluation=None,
                error=fit.reason,
            )

        cancel_event = threading.Event()
        if control is not None and control.cancelled:
            cancel_event.set()

        def progress(event: ModelDownloadProgress) -> None:
            if control is not None and control.cancelled:
                cancel_event.set()
            if on_download_progress is not None:
                on_download_progress(event)

        try:
            downloader.download(candidate.model_ref, progress, cancel_event)
            if cancel_event.is_set():
                raise DownloadCancelled(f'download cancelled: {candidate.model_ref}')
            executor = executor_resolver(candidate)
            outcome, qualifications, accepted = self.qualify_downloaded(
                candidate,
                fit,
                executor,
                tests,
                repeats=repeats,
                variance_threshold=variance_threshold,
                provenance=provenance,
                on_run_completed=on_run_completed,
                control=control,
            )
        except Exception as exc:
            try:
                downloader.delete(candidate.model_ref)
                deleted = True
            except Exception:
                deleted = False
            return CandidateQualification(
                candidate=candidate,
                fit=fit,
                accepted=False,
                deleted=deleted,
                tests=(),
                evaluation=None,
                error=f'{type(exc).__name__}: {exc}',
            )

        deleted = False
        if not accepted and not keep_rejected:
            unload = getattr(executor, 'unload', None)
            if callable(unload):
                try:
                    unload()
                except Exception:
                    pass
            downloader.delete(candidate.model_ref)
            deleted = True

        return CandidateQualification(
            candidate=candidate,
            fit=fit,
            accepted=accepted,
            deleted=deleted,
            tests=qualifications,
            evaluation=outcome,
            error=None,
        )
