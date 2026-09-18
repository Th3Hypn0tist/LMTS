from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from lmts.core.settings import LMTSSettings, MySQLSettings, mysql_target_id, php_api_target_id
from .report_profiles import ReportProfile

ReportTransport = Literal['mysql', 'php_api']

@dataclass(frozen=True, slots=True)
class ReportTarget:
    id: str
    label: str
    transport: ReportTransport
    profile: ReportProfile
    mysql: MySQLSettings | None = None

def configured_report_targets(settings: LMTSSettings) -> tuple[ReportTarget, ...]:
    targets: list[ReportTarget] = []
    for mysql in settings.mysql_connections:
        target_id = mysql_target_id(mysql.id)
        targets.append(ReportTarget(
            id=target_id,
            label=f'MySQL  {mysql.label}',
            transport='mysql',
            mysql=mysql,
            profile=ReportProfile(name=target_id, kind='mysql', endpoint='', publish_key=''),
        ))
    for api in settings.php_api_connections:
        target_id = php_api_target_id(api.id)
        targets.append(ReportTarget(
            id=target_id,
            label=f'PHP API  {api.label}',
            transport='php_api',
            profile=ReportProfile(name=target_id, kind='php_api', endpoint=api.report_endpoint, publish_key=api.publish_key),
        ))
    return tuple(targets)

def resolve_report_target(settings: LMTSSettings, target_id: str) -> ReportTarget:
    for target in configured_report_targets(settings):
        if target.id == target_id:
            return target
    raise KeyError(f'report target is not configured: {target_id}')
