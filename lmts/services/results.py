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

    def export_errors(self, task: str, errors: list[dict[str, object]]) -> Path:
        if not errors:
            raise ValueError('no errors to export')
        return export_error_log(task, errors, root=self.logs_root)
