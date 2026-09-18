from lmts.core.settings import LMTSSettings, MySQLSettings, PHPAPISettings
from lmts.tools.report_targets import configured_report_targets
import lmts.view.report_export_runtime as runtime

def test_publish_many_attempts_every_selected_output(monkeypatch) -> None:
    settings = LMTSSettings(
        mysql_connections=(MySQLSettings(id='a', label='A'), MySQLSettings(id='b', label='B')),
        php_api_connections=(PHPAPISettings(id='api', label='API', base_url='https://api.example', publish_key='k'),),
    )
    targets = configured_report_targets(settings)
    seen = []
    def fake_publish(report, target):
        seen.append(target.id)
        if target.id == 'mysql:a':
            raise RuntimeError('a failed')
        return 'report-1'
    monkeypatch.setattr(runtime, '_publish_one', fake_publish)
    try:
        runtime._publish_many({'report': {'id': 'report-1'}}, targets)
    except RuntimeError as exc:
        assert 'a failed' in str(exc)
    else:
        raise AssertionError('expected aggregate publish error')
    assert seen == ['mysql:a', 'mysql:b', 'php_api:api']
