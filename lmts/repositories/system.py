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
    configuration_id: str
    profile_schema_version: int


def hardware_configuration_id_for(fingerprint: str) -> str:
    fp = str(fingerprint).strip()
    if not fp:
        raise ValueError('hardware configuration identity requires fingerprint')
    return 'cfg_' + fp[:40]


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
        identity: dict[str, object],
        profile: dict[str, object],
        label: str | None = None,
    ) -> SystemRecord:
        system_id = system_id_for(user_id, fingerprint)
        configuration_id = hardware_configuration_id_for(fingerprint)
        resolved_label = (label or f'System {fingerprint[:12]}').strip()
        if not resolved_label:
            raise ValueError('system label must not be empty')
        probe_version = f'profile-v{int(profile_schema_version)}'
        identity_json = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        calculated_fingerprint = hashlib.sha256(identity_json.encode('utf-8')).hexdigest()
        if calculated_fingerprint != fingerprint:
            raise ValueError('hardware configuration fingerprint does not match canonical identity')
        hardware_profile = {
            key: profile[key]
            for key in ('cpu', 'memory', 'gpu', 'npu')
            if key in profile
        }
        profile_json = json.dumps(hardware_profile, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        configuration_label = f'Configuration {fingerprint[:12]}'
        query = f"""
INSERT INTO LMTS_hardware_configurations (
  configuration_id, fingerprint, label, identity_json, profile_json
) VALUES (
  {_hex_text(configuration_id)},
  {_hex_text(fingerprint)},
  {_hex_text(configuration_label)},
  {_hex_text(identity_json)},
  {_hex_text(profile_json)}
)
ON DUPLICATE KEY UPDATE
  label = VALUES(label),
  identity_json = VALUES(identity_json),
  profile_json = VALUES(profile_json);

INSERT INTO LMTS_systems (
  system_id, user_id, label, system_class, configuration_id, probe_version, last_probed_at
)
SELECT
  {_hex_text(system_id)},
  {_hex_text(user_id)},
  {_hex_text(resolved_label)},
  'local',
  {_hex_text(configuration_id)},
  {_hex_text(probe_version)},
  CURRENT_TIMESTAMP(6)
WHERE NOT EXISTS (
  SELECT 1 FROM LMTS_systems WHERE system_id = {_hex_text(system_id)}
);
SELECT JSON_OBJECT(
  'system_id', system_id,
  'user_id', user_id,
  'label', label,
  'configuration_id', configuration_id
)
FROM LMTS_systems
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
            configuration_id=str(payload['configuration_id']),
            profile_schema_version=int(profile_schema_version),
        )
