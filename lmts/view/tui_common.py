from __future__ import annotations

from lmts.tests.types import TestTypeDefinition

from .controller import LMTSViewController


def next_instance_id(controller: LMTSViewController, definition: TestTypeDefinition) -> str:
    base = definition.id.rsplit('.', 1)[-1].replace('_', '-')
    used = {getattr(test, 'instance_id', '') for test in controller.state.tests}
    index = 1
    while f'{base}-{index}' in used:
        index += 1
    return f'{base}-{index}'


def short_test_label(ref: str) -> str:
    return (ref.split('#', 1)[-1] if '#' in ref else ref.rsplit('.', 1)[-1])[:18]


def single_line(host, stdscr, title: str, *, initial: str = '', allow_empty: bool = False) -> str | None:
    while True:
        value = host.input_multiline(stdscr, title, initial=initial)
        if value is None:
            return None
        value = value.strip()
        if '\n' not in value and '\r' not in value and (value or allow_empty):
            return value
        host.message = f"{title}: enter one {'line' if allow_empty else 'non-empty line'}"
