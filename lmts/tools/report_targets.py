from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from lmts.core.settings import LMTSSettings

from .report_profiles import ReportProfile


ReportDestination = Literal['dvstudio', 'dvisualizer']
ReportTransport = Literal['mysql', 'php_api']


@dataclass(frozen=True, slots=True)
class ReportTarget:
    id: str
    label: str
    destination: ReportDestination
    transport: ReportTransport
    profile: ReportProfile


def configured_report_targets(settings: LMTSSettings) -> tuple[ReportTarget, ...]:
    targets = [
        ReportTarget(
            id='dvstudio.mysql',
            label='DVStudio / MySQL',
            destination='dvstudio',
            transport='mysql',
            profile=ReportProfile(
                name='dvstudio.mysql',
                kind='mysql',
                endpoint='',
                publish_key='',
            ),
        ),
    ]
    if settings.dvstudio_php_api.configured:
        targets.append(
            ReportTarget(
                id='dvstudio.php_api',
                label='DVStudio / PHP API',
                destination='dvstudio',
                transport='php_api',
                profile=ReportProfile(
                    name='dvstudio.php_api',
                    kind='php_api',
                    endpoint=settings.dvstudio_php_api.report_endpoint,
                    publish_key=settings.dvstudio_php_api.publish_key,
                ),
            )
        )
    if settings.dvisualizer_php_api.configured:
        targets.append(
            ReportTarget(
                id='dvisualizer.php_api',
                label='DVisualizer / PHP API',
                destination='dvisualizer',
                transport='php_api',
                profile=ReportProfile(
                    name='dvisualizer.php_api',
                    kind='php_api',
                    endpoint=settings.dvisualizer_php_api.report_endpoint,
                    publish_key=settings.dvisualizer_php_api.publish_key,
                ),
            )
        )
    return tuple(targets)


def resolve_report_target(settings: LMTSSettings, target_id: str) -> ReportTarget:
    for target in configured_report_targets(settings):
        if target.id == target_id:
            return target
    raise KeyError(f'report target is not configured: {target_id}')
