from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from lmts.core.settings import LMTSSettings
from lmts.lib.view import UIEventBus

from .controller import LMTSViewController
from .cw_bench_page import CWBenchPage
from .projector import LMTSViewProjector


@dataclass(slots=True)
class TUIState:
    controller: LMTSViewController
    projector: LMTSViewProjector
    cw_bench_page: CWBenchPage
    settings: LMTSSettings
    dvs_service_state: Any
    shortcut_overrides: dict[str, str]
    shortcuts: Any
    events: UIEventBus
    active_tab: str = 'profile'
    profile_console: list[str] = field(default_factory=list)
