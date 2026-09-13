from __future__ import annotations

import curses
from pathlib import Path

from .curses_host import CursesViewHost


def _existing_start(path: Path) -> Path:
    candidate = path.expanduser()
    if candidate.is_dir():
        return candidate.resolve()
    parent = candidate.parent
    while parent != parent.parent and not parent.is_dir():
        parent = parent.parent
    if parent.is_dir():
        return parent.resolve()
    return Path.cwd().resolve()


def choose_directory(
    host: CursesViewHost,
    stdscr: curses.window,
    title: str,
    *,
    initial: Path | str = Path('.'),
) -> Path | None:
    """Generic directory picker with an explicit path-entry escape hatch."""
    requested = Path(initial)
    current = _existing_start(requested)

    while True:
        try:
            directories = sorted(
                (entry for entry in current.iterdir() if entry.is_dir()),
                key=lambda entry: entry.name.casefold(),
            )
        except OSError as exc:
            host.message = f'cannot read directory: {exc}'
            current = current.parent if current.parent != current else Path.cwd().resolve()
            continue

        options = ['[Use this directory]', '[Enter path]']
        has_parent = current.parent != current
        if has_parent:
            options.append('../')
        options.extend(f'{entry.name}/' for entry in directories)

        chosen = host.choose(stdscr, f'{title}: {current}', options)
        if chosen is None:
            return None
        if chosen == 0:
            return current
        if chosen == 1:
            entered = host.input_multiline(stdscr, title, initial=str(requested))
            if entered is None:
                continue
            entered = entered.strip()
            if not entered or '\n' in entered or '\r' in entered:
                host.message = 'path must be one non-empty line'
                continue
            return Path(entered).expanduser()

        offset = 2
        if has_parent:
            if chosen == 2:
                current = current.parent
                continue
            offset = 3
        directory_index = chosen - offset
        if 0 <= directory_index < len(directories):
            current = directories[directory_index]
