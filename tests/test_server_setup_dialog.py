from __future__ import annotations

from lmts.view.dialogs import server_setup


class FakeHost:
    def __init__(self, values: list[str]) -> None:
        self.values = iter(values)
        self.message = ''
        self.events: list[str] = []

    def choose(self, _stdscr, title: str, _options):
        self.events.append(f'choose:{title}')
        return 0

    def input_multiline(self, _stdscr, title: str, *, initial: str = '') -> str:
        assert initial == ''
        self.events.append(f'input:{title}')
        return next(self.values)


def test_server_database_is_collected_before_output_target(monkeypatch) -> None:
    host = FakeHost(['db.host', 'lmts', 'server_user', 'server_password', 'publish_key'])
    captured = {}

    def choose_target(fake_host, _stdscr, *, disk_initial: str):
        assert fake_host is host
        assert disk_initial == '.'
        host.events.append('target')
        return object()

    def deploy(target, config):
        captured['target'] = target
        captured['config'] = config
        host.events.append('deploy')
        return ['index.html', 'config/db.php']

    monkeypatch.setattr(server_setup, 'choose_output_target', choose_target)
    monkeypatch.setattr(server_setup, 'deploy_server', deploy)

    message = server_setup.manage_server_setup(host, object())

    assert message == 'deployed 2 server file(s)'
    assert captured['config'].host == 'db.host'
    assert captured['config'].database == 'lmts'
    assert captured['config'].username == 'server_user'
    assert captured['config'].password == 'server_password'
    assert captured['config'].publish_key == 'publish_key'
    assert host.events == [
        'choose:Server setup',
        'input:Server DB host',
        'input:Server DB database',
        'input:Server DB username',
        'input:Server DB password',
        'input:Server publish key',
        'target',
        'deploy',
    ]


def test_server_setup_does_not_require_local_mysql_settings() -> None:
    text = open('lmts/view/dialogs/server_setup.py', encoding='utf-8').read()
    assert 'MySQLSettings' not in text
    assert 'settings.mysql' not in text
