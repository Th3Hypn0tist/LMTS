from __future__ import annotations

from .model import SweepPoint


def derive_boundary(points: list[SweepPoint], required: float):
    ordered = sorted(points, key=lambda p: p.complexity)
    if not ordered:
        raise ValueError("boundary requires points")
    states = [point.qualifies(required) for point in ordered]
    seen_failure = False
    non_monotonic = False
    for state in states:
        if not state:
            seen_failure = True
        elif seen_failure:
            non_monotonic = True
    if not states[0]:
        return "unstable" if non_monotonic else "below_range", None, None, ordered[0].complexity, non_monotonic
    first_failure = next((index for index, state in enumerate(states) if not state), None)
    if first_failure is None:
        limit = ordered[-1].complexity
        return "unstable" if non_monotonic else "unbounded", limit, limit, None, non_monotonic
    limit = ordered[first_failure - 1].complexity
    return "unstable" if non_monotonic else "bounded", limit, limit, ordered[first_failure].complexity, non_monotonic
