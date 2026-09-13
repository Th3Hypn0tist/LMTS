from __future__ import annotations

import curses

from lmts.core.models import ModelCapabilities
from lmts.core.runtime_targets import (
    DEFAULT_RUNTIME_TARGETS_PATH,
    RuntimeTargetDefinition,
    load_runtime_targets,
    save_runtime_targets,
)
from lmts.core.subject import SubjectMember
from lmts.lib.view import CursesViewHost


def _line(host: CursesViewHost, stdscr: curses.window, title: str, initial: str = '') -> str | None:
    while True:
        value = host.input_multiline(stdscr, title, initial=initial)
        if value is None:
            return None
        value = value.strip()
        if value and '\n' not in value and '\r' not in value:
            return value
        host.message = f'{title}: enter one non-empty line'


def _members(text: str) -> tuple[SubjectMember, ...]:
    output: list[SubjectMember] = []
    for raw in text.split(','):
        token = raw.strip()
        if not token:
            continue
        ref, sep, role = token.partition(':')
        output.append(SubjectMember(ref.strip(), role=role.strip() if sep and role.strip() else None))
    return tuple(output)


def create_runtime_target(host: CursesViewHost, stdscr: curses.window) -> RuntimeTargetDefinition | None:
    kind_index = host.choose(stdscr, 'Runtime target kind', ['bot', 'composition'])
    if kind_index is None:
        return None
    kind = ('bot', 'composition')[kind_index]
    target_id = _line(host, stdscr, 'Target id')
    if target_id is None:
        return None
    label = host.input_multiline(stdscr, 'Target label (optional)', initial=target_id)
    if label is None:
        return None
    transport_index = host.choose(stdscr, 'Runtime transport', ['http', 'subprocess'])
    if transport_index is None:
        return None
    transport = ('http', 'subprocess')[transport_index]
    endpoint = ''
    command: tuple[str, ...] = ()
    if transport == 'http':
        value = _line(host, stdscr, 'LMTS Runtime Protocol endpoint', 'http://127.0.0.1:8000/lmts')
        if value is None:
            return None
        endpoint = value
    else:
        value = _line(host, stdscr, 'Runtime command')
        if value is None:
            return None
        import shlex
        command = tuple(shlex.split(value))

    members: tuple[SubjectMember, ...] = ()
    if kind == 'composition':
        value = _line(host, stdscr, 'Members: ref:role, ref:role')
        if value is None:
            return None
        members = _members(value)
        if not members:
            host.message = 'composition requires at least one member'
            return None

    capability_names = ['vision', 'tools', 'structured_output', 'workspace_read', 'workspace_write', 'multi_file_output']
    selected = host.choose_many(stdscr, 'Additional capabilities', capability_names, set())
    if selected is None:
        return None
    enabled = {capability_names[index] for index in selected}
    capabilities = ModelCapabilities(
        text=True,
        vision='vision' in enabled,
        tools='tools' in enabled,
        structured_output='structured_output' in enabled,
        workspace_read='workspace_read' in enabled,
        workspace_write='workspace_write' in enabled,
        multi_file_output='multi_file_output' in enabled,
    )

    definition = RuntimeTargetDefinition(
        id=target_id,
        kind=kind,
        transport=transport,
        label=str(label).strip(),
        endpoint=endpoint,
        command=command,
        members=members,
        capabilities=capabilities,
    )
    existing = load_runtime_targets(DEFAULT_RUNTIME_TARGETS_PATH)
    updated = tuple(item for item in existing if item.id != definition.id) + (definition,)
    save_runtime_targets(tuple(sorted(updated, key=lambda item: item.id.casefold())))
    host.message = f'runtime target saved: {definition.id}'
    return definition


def manage_runtime_targets(host: CursesViewHost, stdscr: curses.window) -> None:
    while True:
        targets = load_runtime_targets(DEFAULT_RUNTIME_TARGETS_PATH)
        options = ['New runtime target', *(f'Delete  {item.kind}:{item.id}' for item in targets)]
        chosen = host.choose(stdscr, 'Runtime targets', options)
        if chosen is None:
            return
        if chosen == 0:
            create_runtime_target(host, stdscr)
            continue
        target = targets[chosen - 1]
        confirm = host.choose(stdscr, f'Delete runtime target {target.id}?', ['No', 'Yes'], 0)
        if confirm == 1:
            save_runtime_targets(tuple(item for item in targets if item.id != target.id))
            host.message = f'runtime target deleted: {target.id}'
