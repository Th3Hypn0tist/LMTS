from __future__ import annotations

from dataclasses import dataclass

from .controller import LMTSViewController
from .projector import LMTSViewProjector


@dataclass(slots=True)
class AIGMosViewAdapter:
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
        if name == "select_models" and isinstance(value, (list, tuple, set)):
            self.controller.select_model_ids({str(item) for item in value})
            return True
        if name == "select_all_models":
            self.controller.select_all_models()
            return True
        if name == "select_tests" and isinstance(value, (list, tuple, set)):
            self.controller.select_test_refs({str(item) for item in value})
            return True
        if name == "select_all_tests":
            self.controller.select_all_tests()
            return True
        if name == "run":
            self.controller.run_selected()
            return True
        if name == "test_all":
            self.controller.test_all()
            return True
        if name == "export_errors":
            task = str(value) if isinstance(value, str) and value.strip() else "task"
            self.controller.export_errors(task)
            return True
        if name == "profile":
            self.controller.profile()
            return True
        return False
