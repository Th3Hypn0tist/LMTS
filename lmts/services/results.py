from __future__ import annotations

from pathlib import Path

from lmts.core.matrix_store import MatrixRunStore
from lmts.core.store import RunStore
from lmts.lib.errorlog import export_error_log


class ResultService:
    def __init__(self, *, results_root: Path, logs_root: Path) -> None:
        self.results_root = results_root
        self.logs_root = logs_root

    def recent_results(self, *, limit: int = 200) -> list[tuple[Path, dict]]:
        store = RunStore(self.results_root)
        paths = store.iter_run_paths()
        paths.sort(key=lambda path: path.stat().st_mtime if path.exists() else 0.0, reverse=True)
        output: list[tuple[Path, dict]] = []
        for path in paths[:limit]:
            try:
                output.append((path, store.load(path)))
            except (OSError, ValueError):
                continue
        return output

    def recent_matrices(self, *, limit: int = 100) -> list[tuple[Path, dict]]:
        store = MatrixRunStore(self.results_root)
        paths = store.iter_paths()
        paths.sort(key=lambda path: path.stat().st_mtime if path.exists() else 0.0, reverse=True)
        output: list[tuple[Path, dict]] = []
        for path in paths[:limit]:
            try:
                output.append((path, store.load(path)))
            except (OSError, ValueError):
                continue
        return output

    def activity_summary(self) -> dict[str, int]:
        run_store = RunStore(self.results_root)
        matrix_store = MatrixRunStore(self.results_root)
        run_paths = run_store.iter_run_paths()
        matrix_paths = matrix_store.iter_paths()
        targets: set[str] = set()
        tests: set[str] = set()
        target_kinds: dict[str, set[str]] = {'model': set(), 'bot': set(), 'composition': set()}
        outcomes = {'pass': 0, 'fail': 0, 'error': 0, 'cancelled': 0, 'unknown': 0}
        loaded_runs = 0
        for path in run_paths:
            try:
                run = run_store.load(path)
            except (OSError, ValueError):
                continue
            loaded_runs += 1
            subject = run.get('evaluation_subject') if isinstance(run.get('evaluation_subject'), dict) else {}
            target_id = str(run.get('executor_id') or subject.get('id') or '').strip()
            target_kind = str(run.get('executor_kind') or subject.get('kind') or '').strip()
            test_ref = str(run.get('test_ref') or '').strip()
            if target_id:
                targets.add(target_id)
                if target_kind in target_kinds:
                    target_kinds[target_kind].add(target_id)
            if test_ref:
                tests.add(test_ref)
            status = str(run.get('status') or '').strip().casefold()
            if status == 'cancelled':
                outcomes['cancelled'] += 1
            elif run.get('error') is not None:
                outcomes['error'] += 1
            elif run.get('passed') is True:
                outcomes['pass'] += 1
            elif run.get('passed') is False:
                outcomes['fail'] += 1
            else:
                outcomes['unknown'] += 1
        return {
            'runs': loaded_runs, 'matrices': len(matrix_paths), 'targets': len(targets), 'tests': len(tests),
            'models': len(target_kinds['model']), 'bots': len(target_kinds['bot']),
            'compositions': len(target_kinds['composition']), **outcomes,
        }

    def export_errors(self, task: str, errors: list[dict[str, object]]) -> Path:
        if not errors:
            raise ValueError('no errors to export')
        return export_error_log(task, errors, root=self.logs_root)
