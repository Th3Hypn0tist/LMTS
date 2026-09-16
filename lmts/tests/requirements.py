from __future__ import annotations

from lmts.core.models import ModelCapabilities
from lmts.tests.base import TestRequirements, TestSubjectKind


_REQUIREMENT_TO_CAPABILITY = {
    "text_generation": "text",
    "vision": "vision",
    "tools": "tools",
    "structured_output": "structured_output",
    "workspace_read": "workspace_read",
    "workspace_write": "workspace_write",
    "multi_file_output": "multi_file_output",
}


def missing_requirements(
    requirements: TestRequirements,
    capabilities: ModelCapabilities,
) -> tuple[str, ...]:
    missing: list[str] = []
    for requirement_name, capability_name in _REQUIREMENT_TO_CAPABILITY.items():
        required = bool(getattr(requirements, requirement_name))
        if not required:
            continue
        supported = getattr(capabilities, capability_name)
        if supported is not True:
            missing.append(requirement_name)
    return tuple(missing)


def validate_requirements(
    requirements: TestRequirements,
    capabilities: ModelCapabilities,
    *,
    subject_kind: TestSubjectKind | None = None,
) -> None:
    if subject_kind is not None and subject_kind not in requirements.subject_kinds:
        allowed = ", ".join(requirements.subject_kinds)
        raise ValueError(
            f"test does not apply to subject kind {subject_kind!r}; allowed: {allowed}"
        )
    missing = missing_requirements(requirements, capabilities)
    if missing:
        raise ValueError(
            "executor does not satisfy test requirements: " + ", ".join(missing)
        )
