from __future__ import annotations

from dataclasses import replace

from lmts.core.settings import MySQLSettings
from lmts.core.shortcut_settings import normalise_sequence_text
from lmts.tools.mysql_reports import test_mysql_connection
from lmts.tools.mysql_schema import install_mysql_schema

from ..dialogs.server_setup import manage_server_setup
from ..dvs_settings_dialog import manage_dvs
from ..output_dialog import manage_ftp_profiles, manage_report_profiles
from ..registries import build_shortcut_registry
from ..runtime_target_dialog import manage_runtime_targets
from ..tui_common import single_line
from .base import TUIActions


class SettingsActions(TUIActions):
    @property
    def settings_service(self):
        return self.state.settings_service

    def edit_output_folder(self, _stdscr) -> None:
        selected = self.host.choose_directory(
            self.stdscr,
            'Output folder',
            initial=self.state.settings.output_folder,
        )
        if selected is None:
            return
        self.state.settings = replace(self.state.settings, output_folder=str(selected))
        self.settings_service.save_core(self.state.settings)
        self.set_message(f'output folder saved: {self.state.settings.output_folder}')

    def edit_mysql(self, _stdscr) -> None:
        action = self.host.choose(
            self.stdscr,
            'MySQL',
            ['Edit connection', 'Test connection', 'Install LMTS schema'],
        )
        if action is None:
            return
        if action == 1:
            mysql = self.state.settings.mysql
            try:
                test_mysql_connection(mysql)
                self.set_message(
                    f'MySQL connection OK: {mysql.username}@{mysql.host}/{mysql.database}'
                )
            except RuntimeError as exc:
                self.set_message(f'MySQL connection failed: {exc}')
            return

        if action == 2:
            mysql = self.state.settings.mysql
            confirm = self.host.choose(
                self.stdscr,
                'Install LMTS schema',
                ['Cancel', f'Install into {mysql.username}@{mysql.host}/{mysql.database}'],
                0,
            )
            if confirm != 1:
                return
            try:
                install_mysql_schema(mysql)
                self.set_message(f'LMTS schema installed: {mysql.host}/{mysql.database}')
            except (RuntimeError, ValueError) as exc:
                self.set_message(f'MySQL schema install failed: {exc}')
            return

        mysql = self.state.settings.mysql
        values: list[str] = []
        for title, initial in (
            ('MySQL host', mysql.host),
            ('MySQL database', mysql.database),
            ('MySQL username', mysql.username),
            ('MySQL password', mysql.password),
            ('Publish key', mysql.publish_key),
        ):
            value = single_line(self.host, self.stdscr, title, initial=initial)
            if value is None:
                return
            values.append(value)
        self.state.settings = replace(
            self.state.settings,
            mysql=MySQLSettings(
                host=values[0],
                database=values[1],
                username=values[2],
                password=values[3],
                publish_key=values[4],
            ),
        )
        self.settings_service.save_core(self.state.settings)
        self.set_message('MySQL settings saved')

    def edit_dvs(self, _stdscr) -> None:
        updated, status, message = manage_dvs(self.host, self.stdscr, self.state.settings.dvs)
        if updated != self.state.settings.dvs:
            self.state.settings = replace(self.state.settings, dvs=updated)
            self.settings_service.save_core(self.state.settings)
        self.state.dvs_service_state = status
        self.set_message(message or f'DVS status: {status.state}')

    def ftp_settings(self, _stdscr) -> None:
        manage_ftp_profiles(
            self.host,
            self.stdscr,
            store_path=self.settings_service.path('ftp_profiles'),
        )
        self.set_message('FTP profiles updated')

    def report_settings(self, _stdscr) -> None:
        manage_report_profiles(
            self.host,
            self.stdscr,
            store_path=self.settings_service.path('report_profiles'),
        )
        self.set_message('report targets updated')

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
        value = single_line(
            self.host,
            self.stdscr,
            f"{definition.label} shortcut (space-separated; 'default' resets)",
            initial=definition.sequence_label,
        )
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
