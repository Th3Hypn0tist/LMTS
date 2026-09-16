from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from lmts.core.paths import (
    FTP_PROFILES_PATH,
    REPORT_PROFILES_PATH,
    RUNTIME_TARGETS_PATH,
    SETTINGS_PATH,
    SHORTCUT_SETTINGS_PATH,
    lmts_home,
)
from lmts.core.runtime_targets import RuntimeTargetDefinition, load_runtime_targets, save_runtime_targets
from lmts.core.settings import LMTSSettings, load_settings, save_settings
from lmts.core.shortcut_settings import load_shortcut_overrides, save_shortcut_overrides
from lmts.tools.ftp_profiles import FTPProfiles, load_ftp_profiles, save_ftp_profiles
from lmts.tools.report_profiles import ReportProfiles, load_report_profiles, save_report_profiles


@dataclass(frozen=True, slots=True)
class SettingsStoreDescriptor:
    id: str
    path: Path
    contains_secret_values: bool = False


@dataclass(frozen=True, slots=True)
class SettingsSnapshot:
    core: LMTSSettings
    shortcuts: dict[str, tuple[str, ...]]
    runtime_targets: tuple[RuntimeTargetDefinition, ...]
    ftp_profiles: FTPProfiles
    report_profiles: ReportProfiles


class SettingsService:
    """Single ownership boundary for LMTS persistent configuration stores.

    Stores retain independent schemas and files. The service centralizes their
    root, discovery, loading and saving so callers do not construct paths or
    persistence contracts ad hoc.
    """

    def __init__(self, root: Path | None = None) -> None:
        self.root = (lmts_home() if root is None else root.expanduser().resolve())
        self._stores = (
            SettingsStoreDescriptor('core', self.root / SETTINGS_PATH.name, contains_secret_values=True),
            SettingsStoreDescriptor('shortcuts', self.root / SHORTCUT_SETTINGS_PATH.name),
            SettingsStoreDescriptor('runtime_targets', self.root / RUNTIME_TARGETS_PATH.name),
            SettingsStoreDescriptor('ftp_profiles', self.root / FTP_PROFILES_PATH.name),
            SettingsStoreDescriptor('report_profiles', self.root / REPORT_PROFILES_PATH.name, contains_secret_values=True),
        )
        paths = [store.path for store in self._stores]
        if len(paths) != len(set(paths)):
            raise ValueError('settings stores must use unique paths')
        if any(path.parent != self.root for path in paths):
            raise ValueError('all settings stores must live directly under the LMTS settings root')

    def stores(self) -> tuple[SettingsStoreDescriptor, ...]:
        return self._stores

    def path(self, store_id: str) -> Path:
        for store in self._stores:
            if store.id == store_id:
                return store.path
        raise KeyError(f'unknown settings store: {store_id}')

    def load_core(self) -> LMTSSettings:
        return load_settings(self.path('core'))

    def load_shortcuts(self) -> dict[str, tuple[str, ...]]:
        return load_shortcut_overrides(self.path('shortcuts'))

    def load_runtime_targets(self) -> tuple[RuntimeTargetDefinition, ...]:
        return load_runtime_targets(self.path('runtime_targets'))

    def load_ftp_profiles(self) -> FTPProfiles:
        return load_ftp_profiles(self.path('ftp_profiles'))

    def load_report_profiles(self) -> ReportProfiles:
        return load_report_profiles(self.path('report_profiles'))

    def load(self) -> SettingsSnapshot:
        return SettingsSnapshot(
            core=self.load_core(),
            shortcuts=self.load_shortcuts(),
            runtime_targets=self.load_runtime_targets(),
            ftp_profiles=self.load_ftp_profiles(),
            report_profiles=self.load_report_profiles(),
        )

    def save_core(self, settings: LMTSSettings) -> Path:
        return save_settings(settings, self.path('core'))

    def save_shortcuts(self, bindings: dict[str, tuple[str, ...]]) -> Path:
        return save_shortcut_overrides(bindings, self.path('shortcuts'))

    def save_runtime_targets(self, definitions: tuple[RuntimeTargetDefinition, ...]) -> Path:
        return save_runtime_targets(definitions, self.path('runtime_targets'))

    def save_ftp_profiles(self, profiles: FTPProfiles) -> Path:
        return save_ftp_profiles(profiles, self.path('ftp_profiles'))

    def save_report_profiles(self, profiles: ReportProfiles) -> Path:
        return save_report_profiles(profiles, self.path('report_profiles'))
