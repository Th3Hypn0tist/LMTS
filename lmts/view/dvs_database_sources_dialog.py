from __future__ import annotations

import curses

from lmts.dvs.database_sources import (
    DEFAULT_DVS_DATABASE_SOURCES_PATH,
    DVSDatabaseSource,
    load_dvs_database_sources,
    save_dvs_database_sources,
)


def _line(host, stdscr: curses.window, title: str, initial: str = '') -> str | None:
    while True:
        value = host.input_multiline(stdscr, title, initial=initial)
        if value is None:
            return None
        value = value.strip()
        if value and '\n' not in value and '\r' not in value:
            return value
        host.message = f'{title}: enter one non-empty line'


def _edit_source(host, stdscr: curses.window, current: DVSDatabaseSource | None = None) -> DVSDatabaseSource | None:
    source_id = _line(host, stdscr, 'Database source id', current.id if current else '')
    if source_id is None:
        return None
    label = _line(host, stdscr, 'Database source label', current.label if current else source_id)
    if label is None:
        return None
    host_value = _line(host, stdscr, 'MySQL/MariaDB host', current.host if current else '127.0.0.1')
    if host_value is None:
        return None
    port = host.input_integer(
        stdscr,
        'MySQL/MariaDB port',
        default=current.port if current else 3306,
        minimum=1,
        maximum=65535,
    )
    if port is None:
        return None
    database = _line(host, stdscr, 'Database name', current.database if current else 'lmts')
    if database is None:
        return None
    username = _line(host, stdscr, 'Database username', current.username if current else 'lmts')
    if username is None:
        return None

    password_initial = '' if current is None else current.password
    password = _line(host, stdscr, 'Database password', password_initial)
    if password is None:
        return None

    return DVSDatabaseSource(
        id=source_id,
        label=label,
        host=host_value,
        port=port,
        database=database,
        username=username,
        password=password,
    )


def manage_dvs_database_sources(host, stdscr: curses.window) -> None:
    while True:
        sources = load_dvs_database_sources(DEFAULT_DVS_DATABASE_SOURCES_PATH)
        options = ['New database source']
        options.extend(
            f'Edit  {item.id}  {item.username}@{item.host}:{item.port}/{item.database}'
            for item in sources
        )
        options.extend(f'Delete  {item.id}' for item in sources)
        chosen = host.choose(stdscr, 'DVS database sources', options)
        if chosen is None:
            return
        if chosen == 0:
            source = _edit_source(host, stdscr)
            if source is None:
                continue
            if any(item.id == source.id for item in sources):
                host.message = f'DVS database source already exists: {source.id}'
                continue
            save_dvs_database_sources((*sources, source))
            host.message = f'DVS database source saved: {source.id}'
            continue

        edit_start = 1
        delete_start = 1 + len(sources)
        if edit_start <= chosen < delete_start:
            current = sources[chosen - edit_start]
            updated = _edit_source(host, stdscr, current)
            if updated is None:
                continue
            if updated.id != current.id and any(item.id == updated.id for item in sources):
                host.message = f'DVS database source already exists: {updated.id}'
                continue
            values = tuple(item for item in sources if item.id != current.id) + (updated,)
            save_dvs_database_sources(values)
            host.message = f'DVS database source saved: {updated.id}'
            continue

        target = sources[chosen - delete_start]
        confirm = host.choose(stdscr, f'Delete DVS database source {target.id}?', ['No', 'Yes'], 0)
        if confirm == 1:
            save_dvs_database_sources(tuple(item for item in sources if item.id != target.id))
            host.message = f'DVS database source deleted: {target.id}'
