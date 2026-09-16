from __future__ import annotations

from lmts.services.deployment import ServerDeployConfig, deploy_server

from ..output_dialog import choose_output_target


INSTALLER_PATH = 'lmts/install/install_server.sh'


def _required_line(host, stdscr, title: str) -> str | None:
    while True:
        value = host.input_multiline(stdscr, title, initial='')
        if value is None:
            return None
        value = value.strip()
        if value and '\n' not in value and '\r' not in value:
            return value
        host.message = f'{title}: enter one non-empty line'


def _collect_server_database(host, stdscr) -> ServerDeployConfig | None:
    values: list[str] = []
    for title in (
        'Server DB host',
        'Server DB database',
        'Server DB username',
        'Server DB password',
        'Server publish key',
    ):
        value = _required_line(host, stdscr, title)
        if value is None:
            return None
        values.append(value)
    return ServerDeployConfig(
        host=values[0],
        database=values[1],
        username=values[2],
        password=values[3],
        publish_key=values[4],
    )


def manage_server_setup(host, stdscr) -> str | None:
    action = host.choose(stdscr, 'Server setup', ['Deploy www-root', 'Show installer path'])
    if action is None:
        return None
    if action == 1:
        return f'installer: {INSTALLER_PATH}'

    server_config = _collect_server_database(host, stdscr)
    if server_config is None:
        return None
    target = choose_output_target(host, stdscr, disk_initial='.')
    if target is None:
        return None
    try:
        written = deploy_server(target, server_config)
    except (OSError, ValueError, RuntimeError) as exc:
        return f'server deploy failed: {exc}'
    return f'deployed {len(written)} server file(s)'
