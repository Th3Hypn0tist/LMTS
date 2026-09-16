from __future__ import annotations

import curses
import shlex
from dataclasses import replace

from lmts.core.models import ModelCapabilities
from lmts.core.runtime_targets import (
    DEFAULT_RUNTIME_TARGETS_PATH,
    RuntimeTargetDefinition,
    delete_runtime_key,
    load_runtime_secrets,
    load_runtime_targets,
    save_runtime_targets,
    set_runtime_key,
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


def _optional_line(host: CursesViewHost, stdscr: curses.window, title: str, initial: str = '') -> str | None:
    value = host.input_multiline(stdscr, title, initial=initial)
    if value is None:
        return None
    value = value.strip()
    if '\n' in value or '\r' in value:
        host.message = f'{title}: enter one line'
        return None
    return value


def _members(text: str) -> tuple[SubjectMember, ...]:
    output: list[SubjectMember] = []
    for raw in text.split(','):
        token = raw.strip()
        if not token:
            continue
        ref, sep, role = token.partition(':')
        output.append(SubjectMember(ref.strip(), role=role.strip() if sep and role.strip() else None))
    return tuple(output)


def _capabilities_dialog(
    host: CursesViewHost,
    stdscr: curses.window,
    current: ModelCapabilities | None = None,
) -> ModelCapabilities | None:
    capability_names = ['vision', 'tools', 'structured_output', 'workspace_read', 'workspace_write', 'multi_file_output']
    selected = set()
    if current is not None:
        selected = {
            index
            for index, name in enumerate(capability_names)
            if getattr(current, name) is True
        }
    chosen = host.choose_many(stdscr, 'Additional capabilities', capability_names, selected)
    if chosen is None:
        return None
    enabled = {capability_names[index] for index in chosen}
    return ModelCapabilities(
        text=True,
        vision='vision' in enabled,
        tools='tools' in enabled,
        structured_output='structured_output' in enabled,
        workspace_read='workspace_read' in enabled,
        workspace_write='workspace_write' in enabled,
        multi_file_output='multi_file_output' in enabled,
    )


def _http_auth_dialog(
    host: CursesViewHost,
    stdscr: curses.window,
    *,
    target_id: str,
    current_header: str = '',
    current_prefix: str = '',
) -> tuple[str, str, str | None] | None:
    current_has_key = target_id in load_runtime_secrets()
    action = host.choose(
        stdscr,
        'HTTP authentication',
        [
            'No authentication',
            'Authorization: Bearer <key>',
            'Custom header + key',
        ],
        1 if current_header else 0,
    )
    if action is None:
        return None
    if action == 0:
        return '', '', None

    if action == 1:
        header = 'Authorization'
        prefix = 'Bearer '
    else:
        header = _line(host, stdscr, 'Authentication header', current_header or 'X-API-Key')
        if header is None:
            return None
        prefix_value = _optional_line(host, stdscr, 'Value prefix (optional)', current_prefix)
        if prefix_value is None:
            return None
        prefix = prefix_value

    key_title = 'API key (leave empty to keep current)' if current_has_key else 'API key'
    key_value = host.input_multiline(stdscr, key_title, initial='')
    if key_value is None:
        return None
    key = key_value.strip()
    if not key and not current_has_key:
        host.message = 'API key is required for authenticated HTTP target'
        return None
    return header, prefix, key or None


def _save_definition(definition: RuntimeTargetDefinition) -> None:
    existing = load_runtime_targets(DEFAULT_RUNTIME_TARGETS_PATH)
    updated = tuple(item for item in existing if item.id != definition.id) + (definition,)
    save_runtime_targets(tuple(sorted(updated, key=lambda item: item.id.casefold())))


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
    auth_header = ''
    auth_prefix = ''
    key: str | None = None
    if transport == 'http':
        value = _line(host, stdscr, 'Bot address / LMTS Runtime Protocol endpoint', 'http://127.0.0.1:8000/lmts')
        if value is None:
            return None
        endpoint = value
        auth = _http_auth_dialog(host, stdscr, target_id=target_id)
        if auth is None:
            return None
        auth_header, auth_prefix, key = auth
    else:
        value = _line(host, stdscr, 'Runtime command')
        if value is None:
            return None
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

    capabilities = _capabilities_dialog(host, stdscr)
    if capabilities is None:
        return None

    definition = RuntimeTargetDefinition(
        id=target_id,
        kind=kind,
        transport=transport,
        label=str(label).strip(),
        endpoint=endpoint,
        command=command,
        members=members,
        auth_header=auth_header,
        auth_prefix=auth_prefix,
        capabilities=capabilities,
    )
    _save_definition(definition)
    if key is not None:
        set_runtime_key(definition.id, key)
    elif not auth_header:
        delete_runtime_key(definition.id)
    host.message = f'runtime target saved: {definition.id}'
    return definition


def edit_runtime_target(
    host: CursesViewHost,
    stdscr: curses.window,
    definition: RuntimeTargetDefinition,
) -> RuntimeTargetDefinition | None:
    label = host.input_multiline(stdscr, 'Target label (optional)', initial=definition.label or definition.id)
    if label is None:
        return None

    endpoint = definition.endpoint
    command = definition.command
    auth_header = definition.auth_header
    auth_prefix = definition.auth_prefix
    key: str | None = None

    if definition.transport == 'http':
        value = _line(host, stdscr, 'Bot address / LMTS Runtime Protocol endpoint', definition.endpoint)
        if value is None:
            return None
        endpoint = value
        auth = _http_auth_dialog(
            host,
            stdscr,
            target_id=definition.id,
            current_header=definition.auth_header,
            current_prefix=definition.auth_prefix,
        )
        if auth is None:
            return None
        auth_header, auth_prefix, key = auth
    else:
        value = _line(host, stdscr, 'Runtime command', shlex.join(definition.command))
        if value is None:
            return None
        command = tuple(shlex.split(value))

    members = definition.members
    if definition.kind == 'composition':
        initial = ', '.join(
            f'{member.ref}:{member.role}' if member.role else member.ref
            for member in definition.members
        )
        value = _line(host, stdscr, 'Members: ref:role, ref:role', initial)
        if value is None:
            return None
        members = _members(value)
        if not members:
            host.message = 'composition requires at least one member'
            return None

    capabilities = _capabilities_dialog(host, stdscr, definition.capabilities)
    if capabilities is None:
        return None

    updated = replace(
        definition,
        label=str(label).strip(),
        endpoint=endpoint,
        command=command,
        members=members,
        auth_header=auth_header,
        auth_prefix=auth_prefix,
        capabilities=capabilities,
    )
    _save_definition(updated)
    if key is not None:
        set_runtime_key(updated.id, key)
    elif not auth_header:
        delete_runtime_key(updated.id)
    host.message = f'runtime target updated: {updated.id}'
    return updated


def manage_runtime_targets(host: CursesViewHost, stdscr: curses.window) -> None:
    while True:
        targets = load_runtime_targets(DEFAULT_RUNTIME_TARGETS_PATH)
        secrets = load_runtime_secrets()
        options = ['New runtime target']
        for item in targets:
            auth = ' key' if item.id in secrets else ''
            address = item.endpoint if item.transport == 'http' else shlex.join(item.command)
            options.append(f'Edit  {item.kind}:{item.id}{auth}  {address}')
        options.extend(f'Delete  {item.kind}:{item.id}' for item in targets)

        chosen = host.choose(stdscr, 'Runtime targets / bots', options)
        if chosen is None:
            return
        if chosen == 0:
            create_runtime_target(host, stdscr)
            continue

        edit_count = len(targets)
        if 1 <= chosen <= edit_count:
            edit_runtime_target(host, stdscr, targets[chosen - 1])
            continue

        target = targets[chosen - 1 - edit_count]
        confirm = host.choose(stdscr, f'Delete runtime target {target.id}?', ['No', 'Yes'], 0)
        if confirm == 1:
            save_runtime_targets(tuple(item for item in targets if item.id != target.id))
            delete_runtime_key(target.id)
            host.message = f'runtime target deleted: {target.id}'
