from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from lmts.core.settings import LMTSSettings
from lmts.lib.view import UIEventBus
from lmts.services.settings import SettingsService

from .controller import LMTSViewController
from .cw_bench_page import CWBenchPage
from .projector import LMTSViewProjector
from .model_downloader_page import ModelDownloaderPage


@dataclass(slots=True)
class TUIState:
    controller: LMTSViewController
    projector: LMTSViewProjector
    cw_bench_page: CWBenchPage
    model_explorer_page: ModelDownloaderPage
    settings: LMTSSettings
    settings_service: SettingsService
    shortcut_overrides: dict[str, tuple[str, ...]]
    shortcuts: Any
    events: UIEventBus
    active_tab: str = 'benchmark'
    ui_state_scope: str | None = None
    profile_console: list[str] = field(default_factory=list)
