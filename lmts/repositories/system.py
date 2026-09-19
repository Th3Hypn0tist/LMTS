from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from lmts.core.settings import MySQLSettings
from lmts.tools.mysql_reports import _hex_text, _run


@dataclass(frozen=True, slots=True)
class SystemRecord:
    system_id: str
    user_id: str
    label: str
    fingerprint: str
    profile_schema_version: int


def system_id_for(user_id: str, fingerprint: str) -> str:
    owner = str(user_id).strip()
    fp = str(fingerprint).strip()
    if not owner or not fp:
        raise ValueError('system identity requires user_id and fingerprint')
    digest = hashlib.sha256((owner + '\0' + fp).encode('utf-8')).hexdigest()
    return 'sys_' + digest[:40]


class SystemRepository:
    """Persistence boundary for user-owned probed systems."""

    def __init__(self, mysql: MySQLSettings) -> None:
        self.mysql = mysql

    def ensure_system(
        self,
        *,
        user_id: str,
        fingerprint: str,
        profile_schema_version: int,
        label: str | None = None,
    ) -> SystemRecord:
        system_id = system_id_for(user_id, fingerprint)
        resolved_label = (label or f'System {fingerprint[:12]}').strip()
        if not resolved_label:
            raise ValueError('system label must not be empty')
        probe_version = f'profile-v{int(profile_schema_version)}'
        query = f"""
INSERT INTO systems (
  system_id, user_id, label, system_class, probe_version, last_probed_at
) VALUES (
  {_hex_text(system_id)},
  {_hex_text(user_id)},
  {_hex_text(resolved_label)},
  'local',
  {_hex_text(probe_version)},
  CURRENT_TIMESTAMP(6)
)
ON DUPLICATE KEY UPDATE
  label = VALUES(label),
  probe_version = VALUES(probe_version),
  last_probed_at = CURRENT_TIMESTAMP(6);
SELECT JSON_OBJECT(
  'system_id', system_id,
  'user_id', user_id,
  'label', label
)
FROM systems
WHERE system_id = {_hex_text(system_id)}
  AND user_id = {_hex_text(user_id)}
LIMIT 1
""".strip()
        raw = _run(self.mysql, query).strip()
        lines = [line for line in raw.splitlines() if line.strip()]
        if not lines:
            raise RuntimeError('system persistence returned no row')
        payload = json.loads(lines[-1])
        if not isinstance(payload, dict):
            raise RuntimeError('system persistence returned invalid row')
        return SystemRecord(
            system_id=str(payload['system_id']),
            user_id=str(payload['user_id']),
            label=str(payload['label']),
            fingerprint=fingerprint,
            profile_schema_version=int(profile_schema_version),
        )
