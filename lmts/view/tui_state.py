from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from lmts.core.settings import LMTSSettings
from lmts.lib.view import UIEventBus
from lmts.services.settings import SettingsService

from .controller import LMTSViewController
from .cw_bench_page import CWBenchPage
from .projector import LMTSViewProjector


@dataclass(slots=True)
class TUIState:
    controller: LMTSViewController
    projector: LMTSViewProjector
    cw_bench_page: CWBenchPage
    settings: LMTSSettings
    settings_service: SettingsService
    shortcut_overrides: dict[str, tuple[str, ...]]
    shortcuts: Any
    events: UIEventBus
    active_tab: str = 'benchmark'
    profile_console: list[str] = field(default_factory=list)
