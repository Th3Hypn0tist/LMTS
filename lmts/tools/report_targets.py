from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from lmts.core.settings import LMTSSettings, MySQLSettings, mysql_target_id
from .report_profiles import ReportProfile

ReportTransport = Literal['mysql', 'php_api']

PUBLIC_REPORT_TARGET_ID = 'php_api:public'
PUBLIC_REPORT_LABEL = 'PHP API  AIGM.fi public'
PUBLIC_REPORT_ENDPOINT = 'https://aigm.fi/lmts-report/report.php'


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

    targets.append(ReportTarget(
        id=PUBLIC_REPORT_TARGET_ID,
        label=PUBLIC_REPORT_LABEL,
        transport='php_api',
        profile=ReportProfile(
            name=PUBLIC_REPORT_TARGET_ID,
            kind='php_api',
            endpoint=PUBLIC_REPORT_ENDPOINT,
            publish_key='',
        ),
    ))
    return tuple(targets)


def resolve_report_target(settings: LMTSSettings, target_id: str) -> ReportTarget:
    for target in configured_report_targets(settings):
        if target.id == target_id:
            return target
    raise KeyError(f'report target is not configured: {target_id}')
