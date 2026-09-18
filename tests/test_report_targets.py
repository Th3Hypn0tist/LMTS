from __future__ import annotations

import pytest

from lmts.core.settings import LMTSSettings, PHPAPISettings
from lmts.tools.report_targets import configured_report_targets, resolve_report_target


def test_report_targets_are_destination_plus_transport() -> None:
    settings = LMTSSettings(
        dvstudio_php_api=PHPAPISettings(
            base_url='https://studio.example',
            publish_key='studio-key',
        ),
        dvisualizer_php_api=PHPAPISettings(
            base_url='https://visualizer.example',
            publish_key='visualizer-key',
        ),
    )
    targets = configured_report_targets(settings)

    assert [(item.destination, item.transport) for item in targets] == [
        ('dvstudio', 'mysql'),
        ('dvstudio', 'php_api'),
        ('dvisualizer', 'php_api'),
    ]
    assert [item.id for item in targets] == [
        'dvstudio.mysql',
        'dvstudio.php_api',
        'dvisualizer.php_api',
    ]
    assert targets[1].profile.endpoint == 'https://studio.example/api/report.php'
    assert targets[2].profile.endpoint == 'https://visualizer.example/api/report.php'


def test_unconfigured_php_apis_are_not_report_targets() -> None:
    targets = configured_report_targets(LMTSSettings())
    assert [item.id for item in targets] == ['dvstudio.mysql']


def test_resolve_report_target_fails_without_fallback() -> None:
    with pytest.raises(KeyError, match='not configured'):
        resolve_report_target(LMTSSettings(), 'dvisualizer.php_api')
