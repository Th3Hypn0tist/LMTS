from __future__ import annotations

from dataclasses import replace

from lmts.core.settings import MySQLSettings, PHPAPISettings, mysql_target_id, php_api_target_id
from lmts.core.shortcut_settings import normalise_sequence_text
from lmts.tools.mysql_reports import test_mysql_connection
from lmts.tools.mysql_schema import install_mysql_schema
from lmts.tools.report_targets import configured_report_targets

from ..dialogs.server_setup import manage_server_setup
from ..output_dialog import manage_ftp_profiles
from ..registries import build_shortcut_registry
from ..runtime_target_dialog import manage_runtime_targets
from ..tui_common import single_line
from .base import TUIActions


class SettingsActions(TUIActions):
    @property
    def settings_service(self):
        return self.state.settings_service

    def _save_core(self) -> None:
        self.settings_service.save_core(self.state.settings)

    def edit_output_folder(self, _stdscr) -> None:
        selected = self.host.choose_directory(self.stdscr, 'Output folder', initial=self.state.settings.output_folder)
        if selected is None:
            return
        self.state.settings = replace(self.state.settings, output_folder=str(selected))
        self._save_core()
        self.set_message(f'output folder saved: {self.state.settings.output_folder}')

    def _replace_auto_target(self, old_id: str, new_id: str | None) -> tuple[str, ...]:
        values = []
        for target_id in self.state.settings.auto_publish_targets:
            if target_id != old_id:
                values.append(target_id)
            elif new_id is not None:
                values.append(new_id)
        return tuple(values)

    def _edit_mysql_connection(self, current: MySQLSettings | None = None) -> MySQLSettings | None:
        connection_id = single_line(self.host, self.stdscr, 'MySQL connection id', initial=current.id if current else '')
        if connection_id is None:
            return None
        label = single_line(self.host, self.stdscr, 'MySQL connection label', initial=current.label if current else connection_id)
        if label is None:
            return None
        host = single_line(self.host, self.stdscr, 'MySQL host', initial=current.host if current else 'localhost')
        if host is None:
            return None
        port = self.host.input_integer(self.stdscr, 'MySQL port', default=current.port if current else 3306, minimum=1, maximum=65535)
        if port is None:
            return None
        database = single_line(self.host, self.stdscr, 'MySQL database', initial=current.database if current else 'lmts')
        if database is None:
            return None
        username = single_line(self.host, self.stdscr, 'MySQL username', initial=current.username if current else 'lmts')
        if username is None:
            return None
        password = single_line(self.host, self.stdscr, 'MySQL password', initial=current.password if current else '')
        if password is None:
            return None
        publish_key = single_line(self.host, self.stdscr, 'Publish key', initial=current.publish_key if current else 'lmts')
        if publish_key is None:
            return None
        return MySQLSettings(id=connection_id, label=label, host=host, port=port, database=database, username=username, password=password, publish_key=publish_key)

    def manage_mysql_connections(self) -> None:
        while True:
            connections = self.state.settings.mysql_connections
            options = ['New MySQL connection', *(f'{item.label}  {item.username}@{item.host}:{item.port}/{item.database}' for item in connections)]
            chosen = self.host.choose(self.stdscr, 'MySQL connections', options)
            if chosen is None:
                return
            if chosen == 0:
                created = self._edit_mysql_connection()
                if created is None:
                    continue
                if any(item.id == created.id for item in connections):
                    self.set_message(f'MySQL connection id already exists: {created.id}')
                    continue
                self.state.settings = replace(self.state.settings, mysql_connections=tuple(sorted((*connections, created), key=lambda item: item.id.casefold())))
                self._save_core()
                continue

            current = connections[chosen - 1]
            action = self.host.choose(self.stdscr, current.label, ['Edit connection', 'Test connection', 'Install LMTS schema', 'Delete'])
            if action is None:
                continue
            if action == 0:
                updated = self._edit_mysql_connection(current)
                if updated is None:
                    continue
                if updated.id != current.id and any(item.id == updated.id for item in connections):
                    self.set_message(f'MySQL connection id already exists: {updated.id}')
                    continue
                old_ref = mysql_target_id(current.id)
                new_ref = mysql_target_id(updated.id)
                values = tuple(item for item in connections if item.id != current.id) + (updated,)
                self.state.settings = replace(
                    self.state.settings,
                    mysql_connections=tuple(sorted(values, key=lambda item: item.id.casefold())),
                    auto_publish_targets=self._replace_auto_target(old_ref, new_ref),
                )
                self._save_core()
                continue
            if action == 1:
                try:
                    test_mysql_connection(current)
                    self.set_message(f'MySQL connection OK: {current.username}@{current.host}:{current.port}/{current.database}')
                except RuntimeError as exc:
                    self.set_message(f'MySQL connection failed: {exc}')
                continue
            if action == 2:
                confirm = self.host.choose(self.stdscr, 'Install LMTS schema', ['Cancel', f'Install into {current.username}@{current.host}:{current.port}/{current.database}'], 0)
                if confirm == 1:
                    try:
                        install_mysql_schema(current)
                        self.set_message(f'LMTS schema installed: {current.host}:{current.port}/{current.database}')
                    except (RuntimeError, ValueError) as exc:
                        self.set_message(f'MySQL schema install failed: {exc}')
                continue
            if len(connections) == 1:
                self.set_message('at least one MySQL connection is required')
                continue
            confirm = self.host.choose(self.stdscr, f'Delete MySQL connection {current.label}?', ['No', 'Yes'], 0)
            if confirm == 1:
                ref = mysql_target_id(current.id)
                self.state.settings = replace(
                    self.state.settings,
                    mysql_connections=tuple(item for item in connections if item.id != current.id),
                    auto_publish_targets=self._replace_auto_target(ref, None),
                )
                self._save_core()

    def _edit_php_api_connection(self, current: PHPAPISettings | None = None) -> PHPAPISettings | None:
        connection_id = single_line(self.host, self.stdscr, 'PHP API connection id', initial=current.id if current else '')
        if connection_id is None:
            return None
        label = single_line(self.host, self.stdscr, 'PHP API connection label', initial=current.label if current else connection_id)
        if label is None:
            return None
        base_url = single_line(self.host, self.stdscr, 'PHP API report endpoint', initial=current.base_url if current else '')
        if base_url is None:
            return None
        publish_key = single_line(self.host, self.stdscr, 'PHP API publish key', initial=current.publish_key if current else '')
        if publish_key is None:
            return None
        return PHPAPISettings(id=connection_id, label=label, base_url=base_url, publish_key=publish_key)

    def manage_php_api_connections(self) -> None:
        while True:
            connections = self.state.settings.php_api_connections
            options = ['New PHP API connection', *(f'{item.label}  {item.base_url}' for item in connections)]
            chosen = self.host.choose(self.stdscr, 'PHP API connections', options)
            if chosen is None:
                return
            if chosen == 0:
                created = self._edit_php_api_connection()
                if created is None:
                    continue
                if any(item.id == created.id for item in connections):
                    self.set_message(f'PHP API connection id already exists: {created.id}')
                    continue
                self.state.settings = replace(self.state.settings, php_api_connections=tuple(sorted((*connections, created), key=lambda item: item.id.casefold())))
                self._save_core()
                continue
            current = connections[chosen - 1]
            action = self.host.choose(self.stdscr, current.label, ['Edit connection', 'Delete'])
            if action is None:
                continue
            if action == 0:
                updated = self._edit_php_api_connection(current)
                if updated is None:
                    continue
                if updated.id != current.id and any(item.id == updated.id for item in connections):
                    self.set_message(f'PHP API connection id already exists: {updated.id}')
                    continue
                old_ref = php_api_target_id(current.id)
                new_ref = php_api_target_id(updated.id)
                values = tuple(item for item in connections if item.id != current.id) + (updated,)
                self.state.settings = replace(
                    self.state.settings,
                    php_api_connections=tuple(sorted(values, key=lambda item: item.id.casefold())),
                    auto_publish_targets=self._replace_auto_target(old_ref, new_ref),
                )
                self._save_core()
                continue
            confirm = self.host.choose(self.stdscr, f'Delete PHP API connection {current.label}?', ['No', 'Yes'], 0)
            if confirm == 1:
                ref = php_api_target_id(current.id)
                self.state.settings = replace(
                    self.state.settings,
                    php_api_connections=tuple(item for item in connections if item.id != current.id),
                    auto_publish_targets=self._replace_auto_target(ref, None),
                )
                self._save_core()

    def edit_auto_publish_targets(self) -> None:
        targets = configured_report_targets(self.state.settings)
        selected = {index for index, target in enumerate(targets) if target.id in self.state.settings.auto_publish_targets}
        chosen = self.host.choose_many(
            self.stdscr,
            'Auto-publish outputs',
            [target.label for target in targets],
            selected,
            include_all=True,
            all_label='All report outputs',
        )
        if chosen is None:
            return
        auto_publish_targets = tuple(targets[index].id for index in sorted(chosen))
        self.state.settings = replace(self.state.settings, auto_publish_targets=auto_publish_targets)
        self._save_core()
        self.set_message(f'auto-publish outputs: {len(auto_publish_targets)}')

    def ftp_settings(self, _stdscr) -> None:
        manage_ftp_profiles(self.host, self.stdscr, store_path=self.settings_service.path('ftp_profiles'))
        self.set_message('FTP profiles updated')

    def report_output_settings(self, _stdscr) -> None:
        while True:
            settings = self.state.settings
            options = [
                'Server setup',
                f'MySQL connections  {len(settings.mysql_connections)}',
                f'PHP API connections  {len(settings.php_api_connections)}',
                f'Auto-publish outputs  {len(settings.auto_publish_targets)}',
                'FTP',
            ]
            chosen = self.host.choose(self.stdscr, 'Report output', options)
            if chosen is None:
                return
            if chosen == 0:
                self.server_setup(self.stdscr)
            elif chosen == 1:
                self.manage_mysql_connections()
            elif chosen == 2:
                self.manage_php_api_connections()
            elif chosen == 3:
                self.edit_auto_publish_targets()
            else:
                self.ftp_settings(self.stdscr)

    def runtime_target_settings(self, _stdscr) -> None:
        manage_runtime_targets(self.host, self.stdscr)
        self.controller.refresh()
        self.set_message(self.controller.state.message)

    def server_setup(self, _stdscr) -> None:
        message = manage_server_setup(self.host, self.stdscr)
        if message:
            self.set_message(message)

    def shortcut_editor(self, _stdscr) -> None:
        definitions = list(self.state.shortcuts.definitions(('profile', 'benchmark', 'deep', 'cw_bench', 'downloader', 'settings')))
        options = ['Reset all to defaults', *[f'[{item.topic}] {item.sequence_label}  {item.label}' for item in definitions]]
        chosen = self.host.choose(self.stdscr, 'Shortcut editor', options)
        if chosen is None:
            return
        if chosen == 0:
            self.state.shortcut_overrides.clear()
            self.settings_service.save_shortcuts(self.state.shortcut_overrides)
            self.state.shortcuts = build_shortcut_registry()
            self.host.shortcuts = self.state.shortcuts
            self.set_message('shortcuts reset to defaults')
            return
        definition = definitions[chosen - 1]
        value = single_line(self.host, self.stdscr, f"{definition.label} shortcut (space-separated; 'default' resets)", initial=definition.sequence_label)
        if value is None:
            return
        candidate = dict(self.state.shortcut_overrides)
        if value.casefold() == 'default':
            candidate.pop(definition.action, None)
        else:
            candidate[definition.action] = normalise_sequence_text(value)
        try:
            registry = build_shortcut_registry(candidate)
        except ValueError as exc:
            self.set_message(f'shortcut conflict: {exc}')
            return
        self.state.shortcut_overrides.clear()
        self.state.shortcut_overrides.update(candidate)
        self.settings_service.save_shortcuts(self.state.shortcut_overrides)
        self.state.shortcuts = registry
        self.host.shortcuts = registry
        self.set_message(f'shortcut saved: {definition.label}')
