from __future__ import annotations

from lmts.tools.reference_benchmark import ReferenceBenchmarkProgress


def format_reference_progress(event: ReferenceBenchmarkProgress) -> str:
    domain = event.domain.upper()
    label = event.label or event.benchmark_id or event.domain
    if event.phase == 'suite_started':
        return f'{domain} suite started'
    if event.phase == 'suite_completed':
        return f'{domain} suite completed'
    if event.phase == 'backend_started':
        return f'{domain} backend started: {label}'
    if event.phase == 'backend_completed':
        return f'{domain} backend completed: {label}'
    if event.phase == 'test_started':
        return f'{domain} test started: {label}'
    if event.phase == 'sample_completed':
        if event.sample_index is None or event.sample_total is None:
            raise ValueError('sample_completed progress requires sample_index and sample_total')
        return f'{domain} {label}: sample {event.sample_index}/{event.sample_total}'
    if event.phase == 'test_completed':
        return f'{domain} test completed: {label}'
    raise ValueError(f'unknown reference benchmark progress phase: {event.phase}')
