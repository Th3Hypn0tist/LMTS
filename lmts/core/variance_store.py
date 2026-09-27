from __future__ import annotations

import json
import os
from pathlib import Path

from .run import utc_now
from .store import safe_component


class VarianceStore:
    """Append-only lightweight PASS/FAIL observations keyed to one full run."""

    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()

    def path_for_run(self, run_id: str) -> Path:
        value = str(run_id).strip()
        if not value:
            raise ValueError('variance sample requires source run_id')
        return self.root / 'variance' / f'{safe_component(value)}.jsonl'

    def append(self, run_id: str, passed: bool, *, observed_at: str | None = None) -> Path:
        if not isinstance(passed, bool):
            raise ValueError('variance sample outcome must be PASS or FAIL')
        path = self.path_for_run(run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            'outcome': 'pass' if passed else 'fail',
            'observed_at': observed_at or utc_now(),
        }
        line = json.dumps(payload, ensure_ascii=False, separators=(',', ':')) + '\n'
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(fd, line.encode('utf-8'))
        finally:
            os.close(fd)
        return path

    def samples_for_run(self, run_id: str) -> list[dict[str, str]]:
        path = self.path_for_run(run_id)
        if not path.is_file():
            return []
        samples: list[dict[str, str]] = []
        for line in path.read_text(encoding='utf-8').splitlines():
            if not line.strip():
                continue
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise RuntimeError(f'invalid variance sample row: {path}')
            outcome = str(payload.get('outcome') or '').strip()
            observed_at = str(payload.get('observed_at') or '').strip()
            if outcome not in {'pass', 'fail'} or not observed_at:
                raise RuntimeError(f'invalid variance sample row: {path}')
            samples.append({'outcome': outcome, 'observed_at': observed_at})
        return samples
