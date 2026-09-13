from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_fingerprint(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def runtime_configuration_payload(
    *,
    executor_id: str,
    executor_kind: str,
    subject_fingerprint: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    return {
        "executor_id": executor_id,
        "executor_kind": executor_kind,
        "subject_fingerprint": subject_fingerprint,
        "metadata": metadata,
    }


def runtime_configuration_fingerprint(
    *,
    executor_id: str,
    executor_kind: str,
    subject_fingerprint: str,
    metadata: dict[str, Any],
) -> str:
    return canonical_fingerprint(
        runtime_configuration_payload(
            executor_id=executor_id,
            executor_kind=executor_kind,
            subject_fingerprint=subject_fingerprint,
            metadata=metadata,
        )
    )
