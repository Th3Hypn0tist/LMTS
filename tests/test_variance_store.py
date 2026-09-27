from __future__ import annotations

from lmts.core.variance_store import VarianceStore


def test_variance_store_keeps_only_lightweight_outcomes(tmp_path) -> None:
    store = VarianceStore(tmp_path / 'results')

    path = store.append('run-1', True, observed_at='2026-09-27T12:00:00+00:00')
    store.append('run-1', False, observed_at='2026-09-27T12:00:01+00:00')

    assert path.exists()
    assert store.samples_for_run('run-1') == [
        {'outcome': 'pass', 'observed_at': '2026-09-27T12:00:00+00:00'},
        {'outcome': 'fail', 'observed_at': '2026-09-27T12:00:01+00:00'},
    ]
    text = path.read_text(encoding='utf-8')
    assert 'telemetry' not in text
    assert 'response' not in text
    assert 'metrics' not in text


def test_variance_store_rejects_non_boolean_outcomes(tmp_path) -> None:
    store = VarianceStore(tmp_path / 'results')

    try:
        store.append('run-1', None)  # type: ignore[arg-type]
    except ValueError as exc:
        assert 'PASS or FAIL' in str(exc)
    else:
        raise AssertionError('expected variance outcome validation')
