from __future__ import annotations

from dataclasses import dataclass

from .controller import LMTSViewController
from .projector import LMTSViewProjector


@dataclass(slots=True)
class AIGMosViewAdapter:
    """AIGMos View-compatible LMTS adapter.

    LMTS does not own AIGMos rendering. It exposes a VIEW_TARGET payload and
    host-neutral actions. AIGMos remains the centralized layout renderer.
    """

    controller: LMTSViewController
    view_target: str = "|lmts:view"

    module_type: str = "view"

    @property
    def VIEW_TARGET(self) -> str:
        return self.view_target

    def value(self) -> str:
        return LMTSViewProjector(self.controller.state).project().text()

    def metadata(self) -> dict[str, object]:
        return {
            "module_type": self.module_type,
            "view_target": self.VIEW_TARGET,
            "render_owner": "aigmos-layout",
            "lmts_owns_render_logic": False,
        }

    def action(self, name: str, value: object | None = None) -> bool:
        if name == "refresh":
            self.controller.refresh()
            return True
        if name == "select_model" and isinstance(value, int):
            self.controller.select_model(value)
            return True
        if name == "select_test" and isinstance(value, int):
            self.controller.select_test(value)
            return True
        if name == "run":
            self.controller.run_selected()
            return True
        if name == "benchmark":
            self.controller.benchmark_all_local()
            return True
        if name == "profile":
            self.controller.profile()
            return True
        return False
