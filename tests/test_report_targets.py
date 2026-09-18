import pytest
from lmts.core.settings import LMTSSettings, MySQLSettings, PHPAPISettings
from lmts.tools.report_targets import configured_report_targets, resolve_report_target

def test_report_targets_are_lmts_owned_connections() -> None:
    settings = LMTSSettings(
        mysql_connections=(MySQLSettings(id='local', label='Local'), MySQLSettings(id='archive', label='Archive')),
        php_api_connections=(PHPAPISettings(id='studio', label='Studio', base_url='https://studio.example', publish_key='k'),),
    )
    targets = configured_report_targets(settings)
    assert [item.id for item in targets] == ['mysql:local', 'mysql:archive', 'php_api:studio']
    assert [item.transport for item in targets] == ['mysql', 'mysql', 'php_api']
    assert targets[0].mysql == settings.mysql_connections[0]

def test_resolve_report_target_fails_without_fallback() -> None:
    with pytest.raises(KeyError, match='not configured'):
        resolve_report_target(LMTSSettings(), 'php_api:missing')
